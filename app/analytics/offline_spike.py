"""One-child fixed offline H spike. Never imported by routes. NOT a sandbox.

Shares tested Win32 primitives, retaining P39B's unsuspended startup gap.
128 MiB committed-memory development ceiling; no CPU quota or RSS guarantee.
Fixed fixture only, one event-loop owner, no pending child queue.
"""
import asyncio
import ctypes as C
from ctypes import wintypes as W
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from .process_isolation import IsolationError, kernel, checked, Extended, decode
from .offline_fixture import (fixture_payload, validate_payload, calculate, stable, OUTPUT_LIMIT)

MEMORY_LIMIT = 128 * 1024 * 1024


def _dependency_directory():
    # Trusted installed runtime path, never from JSON/request/environment.
    import pydantic
    return Path(pydantic.__file__).resolve().parents[1]


class FixtureSpike:
    def __init__(self, limit=1):
        if type(limit) is not int or limit != 1:
            raise IsolationError('invalid_capacity')
        self.limit, self.closing = limit, False
        self.tasks = set()
        self.active = {}
        self.receipts = []  # Owned fixture-worker PID/exit evidence, bounded below.
        self.loop = None
        self.peaks = []

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

    async def run(self, case='normal', *, seconds=5, started=None, hold=False):
        self._owner()
        if type(hold) is not bool:
            raise IsolationError('invalid_diagnostic')
        payload = fixture_payload(case)
        raw = stable(payload)
        validate_payload(raw)
        expected_result = calculate(payload)
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
            p = subprocess.Popen([sys._base_executable, '-I', '-S', str(Path(__file__).with_name('offline_worker.py')), str(_dependency_directory())] + (['--hold'] if hold else []),
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
            if (type(result) is not dict or set(result) != {'v', 'pid', 'result', 'guards', 'peak_working_set'}
                    or type(result['v']) is not int or result['v'] != 1
                    or type(result['pid']) is not int or result['pid'] != p.pid
                    or result['guards'] != ['dotenv', 'socket', 'dns', 'subprocess']
                    or type(result['peak_working_set']) is not int
                    or not 0 < result['peak_working_set'] < MEMORY_LIMIT
                    or stable(result['result']) != stable(expected_result)):
                raise IsolationError('result_mismatch')
            peak = Extended()
            checked(k.QueryInformationJobObject(job, 9, C.byref(peak), C.sizeof(peak), None), 'query_peak')
            if not 0 < peak.peak_process < MEMORY_LIMIT:
                raise IsolationError('memory_evidence')
            self.peaks.append({'pid': p.pid, 'peak_commit': peak.peak_process,
                               'peak_working_set': result['peak_working_set']})
            self.peaks[:] = self.peaks[-32:]
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

