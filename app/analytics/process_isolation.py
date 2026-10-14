"""Windows-only synthetic proof. Never imported by routes; not a security sandbox.

Fixed child image, JSON pipes, no inherited environment or application imports.
Job assignment precedes input (interpreter startup itself is outside the job).
Committed-memory cap is NOT RSS or CPU enforcement. One event-loop owner only.
"""
import asyncio
import ctypes as C
from ctypes import wintypes as W
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

INPUT_LIMIT = 2048
OUTPUT_LIMIT = 1024
MEMORY_LIMIT = 64 * 1024 * 1024
MODES = {'sum', 'hang', 'exception', 'crash', 'malformed', 'overlong', 'wrong', 'memory'}


class IsolationError(RuntimeError):
    pass


class Basic(C.Structure):
    _fields_ = [('process_time', C.c_int64), ('job_time', C.c_int64),
                ('flags', W.DWORD), ('min_ws', C.c_size_t), ('max_ws', C.c_size_t),
                ('active', W.DWORD), ('affinity', C.c_size_t),
                ('priority', W.DWORD), ('scheduling', W.DWORD)]


class IO(C.Structure):
    _fields_ = [(name, C.c_uint64) for name in ('ro', 'wo', 'oo', 'rb', 'wb', 'ob')]


class Extended(C.Structure):
    _fields_ = [('basic', Basic), ('io', IO), ('process_memory', C.c_size_t),
                ('job_memory', C.c_size_t), ('peak_process', C.c_size_t), ('peak_job', C.c_size_t)]


def kernel():
    if sys.platform != 'win32':
        raise IsolationError('windows_required')
    k = C.WinDLL('kernel32', use_last_error=True)
    signatures = {
        'CreateJobObjectW': ([C.c_void_p, W.LPCWSTR], W.HANDLE),
        'SetInformationJobObject': ([W.HANDLE, C.c_int, C.c_void_p, W.DWORD], W.BOOL),
        'QueryInformationJobObject': ([W.HANDLE, C.c_int, C.c_void_p, W.DWORD, C.c_void_p], W.BOOL),
        'AssignProcessToJobObject': ([W.HANDLE, W.HANDLE], W.BOOL),
        'TerminateJobObject': ([W.HANDLE, W.UINT], W.BOOL),
        'CloseHandle': ([W.HANDLE], W.BOOL),
        'PeekNamedPipe': ([W.HANDLE, C.c_void_p, W.DWORD, C.c_void_p, C.c_void_p, C.c_void_p], W.BOOL),
        'WaitForSingleObject': ([W.HANDLE, W.DWORD], W.DWORD),
    }
    for name, (args, result) in signatures.items():
        fn = getattr(k, name)
        fn.argtypes, fn.restype = args, result
    return k


def checked(ok, action):
    if not ok:
        raise IsolationError(action + '_winerror_' + str(C.get_last_error()))


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('constant')))


def validate(mode, values):
    if (type(mode) is not str or mode not in MODES or type(values) is not list
            or len(values) > 128 or any(type(v) is not int or abs(v) > 10000 for v in values)):
        raise IsolationError('invalid_input')
    raw = json.dumps({'v': 1, 'mode': mode, 'values': values}, separators=(',', ':')).encode()
    if len(raw) > INPUT_LIMIT:
        raise IsolationError('input_limit')
    return raw


class Prototype:
    def __init__(self, limit=2):
        if type(limit) is not int or not 1 <= limit <= 2:
            raise IsolationError('invalid_capacity')
        self.limit, self.closing = limit, False
        self.tasks = set()
        self.active = {}
        self.receipts = []  # Synthetic PID/exit evidence only; bounded below.
        self.loop = None

    def _owner(self):
        loop = asyncio.get_running_loop()
        if self.loop is None:
            self.loop = loop
        if loop is not self.loop:
            raise IsolationError('wrong_event_loop')

    async def shutdown(self):
        self._owner()
        self.closing = True
        tasks = tuple(self.tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def run(self, values, *, mode='sum', seconds=2, started=None):
        self._owner()
        raw = validate(mode, values)
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or not .02 <= seconds <= 5:
            raise IsolationError('invalid_deadline')
        if self.closing or len(self.tasks) >= self.limit:
            raise IsolationError('capacity')
        task = asyncio.current_task()
        if task in self.tasks:
            raise IsolationError('duplicate_owner')
        self.tasks.add(task)
        p = job = None
        k = None
        deadline = time.monotonic() + seconds
        reason = 'failed'
        cleaned = False
        try:
            k = kernel()
            job = k.CreateJobObjectW(None, None)
            checked(job, 'create_job')
            limits = Extended()
            limits.basic.flags = 0x2000 | 0x100 | 0x8  # kill-on-close, process memory, active count
            limits.basic.active = 1
            limits.process_memory = MEMORY_LIMIT
            checked(k.SetInformationJobObject(job, 9, C.byref(limits), C.sizeof(limits)), 'set_job')
            verified = Extended()
            checked(k.QueryInformationJobObject(job, 9, C.byref(verified), C.sizeof(verified), None), 'query_job')
            if verified.basic.flags != limits.basic.flags or verified.process_memory != MEMORY_LIMIT or verified.basic.active != 1:
                raise IsolationError('job_limits_mismatch')
            # Windows venv redirector spawns another process: use its own base runtime.
            p = subprocess.Popen([sys._base_executable, '-I', '-S', str(Path(__file__).resolve()), '--synthetic-child'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                env={'SystemRoot': 'C:\\Windows'}, close_fds=True,
                creationflags=subprocess.CREATE_NO_WINDOW, bufsize=0)
            checked(k.AssignProcessToJobObject(job, int(p._handle)), 'assign_job')
            self.active[p.pid] = p
            p.stdin.write(raw)
            p.stdin.close()
            import msvcrt
            pipe = msvcrt.get_osfhandle(p.stdout.fileno())
            output = bytearray()
            ready = False
            exited = False
            while True:
                if time.monotonic() >= deadline:
                    raise IsolationError('deadline')
                available = W.DWORD()
                ok = k.PeekNamedPipe(pipe, None, 0, None, C.byref(available), None)
                if not ok and C.get_last_error() != 109:
                    checked(ok, 'pipe')
                if available.value:
                    output.extend(os.read(p.stdout.fileno(), min(available.value, OUTPUT_LIMIT + 3 - len(output))))
                    if not ready and len(output) >= 2:
                        if output[:2] != b'R\n':
                            raise IsolationError('invalid_startup')
                        del output[:2]
                        ready = True
                        if started is not None:
                            started.set()
                    if len(output) > OUTPUT_LIMIT:
                        raise IsolationError('output_limit')
                    continue
                if p.poll() is not None:
                    if exited:
                        break
                    exited = True
                    continue  # Drain once more after observing exit (peek/exit race).
                await asyncio.sleep(.005)
            if p.returncode != 0:
                raise IsolationError('child_exit')
            if not ready:
                raise IsolationError('invalid_startup')
            try:
                result = decode(output)
            except (ValueError, UnicodeError, RecursionError):
                raise IsolationError('invalid_output') from None
            expected = {'v': 1, 'pid': p.pid, 'count': len(values), 'sum': sum(values)}
            if mode == 'memory':
                expected = {'v': 1, 'pid': p.pid, 'allocation_denied': True}
            if result != expected or any(type(result.get(key)) is not type(value) for key, value in expected.items()):
                raise IsolationError('result_mismatch')
            reason = 'normal'
            return result
        except OSError:
            raise IsolationError('process_io_failure') from None
        finally:
            # No await: repeated task cancellation cannot interrupt kill/wait/slot ownership.
            try:
                if p is not None:
                    if p.poll() is None:
                        if job and k:
                            checked(k.TerminateJobObject(job, 1), 'terminate_job')
                        p.kill()  # Own Popen handle only; also covers failed assignment.
                    p.wait(timeout=5)
                    checked(k.WaitForSingleObject(int(p._handle), 5000) == 0, 'reap')
                    self.receipts.append((p.pid, p.returncode, reason))
                    self.receipts[:] = self.receipts[-32:]
                    for stream in (p.stdin, p.stdout):
                        stream.close()
                    p._handle.Close()
                    self.active.pop(p.pid, None)
                    cleaned = True
            finally:
                if job and k:
                    checked(k.CloseHandle(job), 'close_job')
                # If cleanup fails, keep ownership fail-closed.
                if p is None or cleaned:
                    self.tasks.discard(task)


def child():
    # No application, DB, credentials, or site-packages imports.
    def guard(event, args):
        if event.startswith(('socket.', 'subprocess.')) or event in ('os.system', 'os.spawn'):
            raise RuntimeError('forbidden')
        if event == 'open' and isinstance(args[0], (str, bytes)):
            name = os.fsdecode(args[0]).replace('\\', '/').rsplit('/', 1)[-1].casefold().rstrip(' .')
            if name == '.env' or name.startswith(('.env.', '.env:')):
                raise RuntimeError('forbidden')
    sys.addaudithook(guard)
    try:
        raw = sys.stdin.buffer.read(INPUT_LIMIT + 1)
        data = decode(raw)
        if len(raw) > INPUT_LIMIT or type(data) is not dict or set(data) != {'v', 'mode', 'values'} or type(data['v']) is not int or data['v'] != 1:
            raise ValueError()
        validate(data['mode'], data['values'])
        mode, values = data['mode'], data['values']
        sys.stdout.buffer.write(b'R\n')
        sys.stdout.buffer.flush()
        if mode == 'hang':
            time.sleep(30)
        if mode == 'exception':
            raise ValueError('private synthetic error')
        if mode == 'crash':
            os._exit(17)
        if mode in {'malformed', 'overlong'}:
            sys.stdout.buffer.write(b'{' if mode == 'malformed' else b'x' * (OUTPUT_LIMIT + 1))
            return
        result = {'v': 1, 'pid': os.getpid(), 'count': len(values), 'sum': sum(values)}
        if mode == 'wrong':
            result['pid'] += 1
        if mode == 'memory':
            k = kernel()
            k.VirtualAlloc.argtypes = [C.c_void_p, C.c_size_t, W.DWORD, W.DWORD]
            k.VirtualAlloc.restype = C.c_void_p
            # Commit charge request beyond 64MiB, never touch pages, never exhaust host.
            allocation = k.VirtualAlloc(None, MEMORY_LIMIT + 4096, 0x3000, 4)
            result = {'v': 1, 'pid': os.getpid(), 'allocation_denied': allocation is None}
            if allocation:
                k.VirtualFree.argtypes = [C.c_void_p, C.c_size_t, W.DWORD]
                k.VirtualFree(allocation, 0, 0x8000)
        sys.stdout.buffer.write(json.dumps(result, separators=(',', ':')).encode())
    except Exception:
        os._exit(20)


if __name__ == '__main__':
    if sys.argv[1:] != ['--synthetic-child'] or sys.platform != 'win32':
        raise SystemExit(21)
    child()
