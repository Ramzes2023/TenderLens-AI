"""Opt-in Windows synthetic lifecycle candidate; no application integration.

Not a security sandbox or whole-request CPU/RSS/auth/DB resource guarantee.
Only a fixed child image and three synthetic modes; no caller-supplied code.
"""
import asyncio
import ctypes as C
from ctypes import wintypes as W
import math
from pathlib import Path
import subprocess
import sys
import time
import uuid


def win_kernel():
    from app.analytics.process_isolation import kernel
    k = kernel()
    signatures = {
        'CreateEventW': ([C.c_void_p, W.BOOL, W.BOOL, W.LPCWSTR], W.HANDLE),
        'OpenEventW': ([W.DWORD, W.BOOL, W.LPCWSTR], W.HANDLE),
        'SetEvent': ([W.HANDLE], W.BOOL),
        'ResumeThread': ([W.HANDLE], W.DWORD),
        'SuspendThread': ([W.HANDLE], W.DWORD),
        'TerminateProcess': ([W.HANDLE, W.UINT], W.BOOL),
        'IsProcessInJob': ([W.HANDLE, W.HANDLE, C.POINTER(W.BOOL)], W.BOOL),
        'GetWindowsDirectoryW': ([W.LPWSTR, W.UINT], W.UINT),
    }
    for name, (args, result) in signatures.items():
        getattr(k, name).argtypes, getattr(k, name).restype = args, result
    return k


class SuspendedChild:
    """Single-owner lifecycle: start suspended, assign, resume, wait, close.

    Explicit enabled=True is required. close() never awaits; cancellation cannot
    interrupt termination/reap. On cleanup failure ownership remains for retry.
    """
    def __init__(self, *, enabled=False):
        from app.analytics.process_isolation import IsolationError
        if enabled is not True:
            raise IsolationError('candidate_disabled')
        self.k = win_kernel()
        self.process = self.thread = self.job = self.event = None
        self.assigned = self.resumed = self.reaped = False
        self.pid = self.exitcode = None

    def start(self, mode='complete'):
        from app.analytics.process_isolation import Extended, MEMORY_LIMIT, checked, IsolationError
        if type(mode) is not str or mode not in {'complete', 'hang', 'malformed'}:
            raise IsolationError('invalid_mode')
        if any((self.process, self.thread, self.job, self.event)) or self.reaped:
            raise IsolationError('single_use')
        import _winapi
        k = self.k
        try:
            self.job = k.CreateJobObjectW(None, None)
            checked(self.job, 'create_job')
            limits = Extended()
            limits.basic.flags = 0x2000 | 0x100 | 0x8
            limits.basic.active = 1
            limits.process_memory = MEMORY_LIMIT
            checked(k.SetInformationJobObject(self.job, 9, C.byref(limits), C.sizeof(limits)), 'set_job')
            readback = Extended()
            checked(k.QueryInformationJobObject(self.job, 9, C.byref(readback), C.sizeof(readback), None), 'query_job')
            if (readback.basic.flags, readback.basic.active, readback.process_memory) != (limits.basic.flags, 1, MEMORY_LIMIT):
                raise IsolationError('job_limits_mismatch')
            name = 'Local\\VALYQON-P39R2-' + uuid.uuid4().hex
            self.event = k.CreateEventW(None, True, False, name)
            checked(self.event, 'create_event')
            root = C.create_unicode_buffer(32768)
            size = k.GetWindowsDirectoryW(root, len(root))
            if not 0 < size < len(root):
                raise IsolationError('windows_directory')
            executable = str(Path(sys._base_executable).resolve(strict=True))
            command = subprocess.list2cmdline([executable, '-I', '-S', str(Path(__file__).resolve()), '--child', name, mode])
            # bInheritHandles=False; no pipe/stdio or other parent handles inherited.
            self.process, self.thread, self.pid, _ = _winapi.CreateProcess(
                executable, command, None, None, False,
                0x4 | 0x08000000 | 0x400,  # SUSPENDED, NO_WINDOW, UNICODE_ENVIRONMENT
                {'SystemRoot': root.value}, root.value, subprocess.STARTUPINFO())
            return self
        except OSError:
            self.close()
            raise IsolationError('process_start_failure') from None
        except BaseException:
            self.close()
            raise

    def assign(self):
        from app.analytics.process_isolation import checked, IsolationError
        if not self.process or self.assigned or self.resumed:
            raise IsolationError('invalid_assignment_state')
        checked(self.k.AssignProcessToJobObject(self.job, self.process), 'assign_job')
        inside = W.BOOL()
        checked(self.k.IsProcessInJob(self.process, self.job, C.byref(inside)), 'verify_job')
        if not inside.value:
            raise IsolationError('assignment_not_verified')
        self.assigned = True

    def resume(self):
        from app.analytics.process_isolation import IsolationError
        if not self.assigned or self.resumed:
            raise IsolationError('resume_requires_verified_job')
        if self.k.ResumeThread(self.thread) != 1:
            raise IsolationError('unexpected_suspend_count')
        self.resumed = True

    async def run(self, mode='complete', *, seconds=2, started=None):
        from app.analytics.process_isolation import IsolationError
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or not .05 <= seconds <= 5:
            raise IsolationError('invalid_deadline')
        deadline = time.monotonic() + seconds
        try:
            self.start(mode)
            self.assign()
            self.resume()
            while True:
                if self.k.WaitForSingleObject(self.event, 0) == 0 and started is not None:
                    started.set()
                status = self.k.WaitForSingleObject(self.process, 0)
                if status == 0:
                    import _winapi
                    self.exitcode = _winapi.GetExitCodeProcess(self.process)
                    if self.k.WaitForSingleObject(self.event, 0) != 0 or self.exitcode != 7:
                        raise IsolationError('invalid_completion')
                    return 7
                if status != 258:
                    raise IsolationError('process_wait_failed')
                if time.monotonic() >= deadline:
                    raise IsolationError('deadline')
                await asyncio.sleep(.005)
        finally:
            self.close()

    def close(self):
        from app.analytics.process_isolation import checked, IsolationError
        k = self.k
        if self.process:
            deadline = time.monotonic() + 3
            def wait(milliseconds):
                status = k.WaitForSingleObject(self.process, milliseconds)
                if status not in (0, 258):
                    checked(False, 'reap_wait')
                return status

            status = wait(0)
            if status != 0:
                # Job termination is asynchronous. Give it time to signal the
                # owned process before attempting the process-handle fallback.
                if self.assigned:
                    checked(k.TerminateJobObject(self.job, 1), 'terminate_job')
                    status = wait(1000)
                if status != 0:
                    terminated = k.TerminateProcess(self.process, 1)
                    error = C.get_last_error() if not terminated else None
                    if not terminated and error != 5:
                        raise IsolationError('terminate_owned_winerror_' + str(error))
                    remaining = max(0, int((deadline - time.monotonic()) * 1000))
                    status = wait(remaining)
                    if status != 0:
                        if error is not None:
                            raise IsolationError('terminate_owned_winerror_' + str(error))
                        raise IsolationError('reap_timeout')
                    # ERROR_ACCESS_DENIED is accepted ONLY after this exact
                    # owned handle signals, including an in-flight job kill.
            if status != 0:
                raise IsolationError('reap_timeout')
            import _winapi
            self.exitcode = _winapi.GetExitCodeProcess(self.process)
            self.reaped = True
        for attribute in ('thread', 'process', 'job', 'event'):
            handle = getattr(self, attribute)
            if handle:
                checked(k.CloseHandle(handle), 'close_' + attribute)
                setattr(self, attribute, None)


def _child():
    # Fixed synthetic child: stdlib only, no app imports, files, sockets or DB.
    k = C.WinDLL('kernel32', use_last_error=True)
    k.OpenEventW.argtypes, k.OpenEventW.restype = [W.DWORD, W.BOOL, W.LPCWSTR], W.HANDLE
    k.SetEvent.argtypes, k.SetEvent.restype = [W.HANDLE], W.BOOL
    k.CloseHandle.argtypes, k.CloseHandle.restype = [W.HANDLE], W.BOOL
    if len(sys.argv) != 4 or sys.argv[1] != '--child' or sys.argv[3] not in {'complete', 'hang', 'malformed'}:
        return 21
    event = k.OpenEventW(2, False, sys.argv[2])
    if not event:
        return 22
    try:
        if sys.argv[3] == 'malformed':
            return 23
        if not k.SetEvent(event):
            return 24
        if sys.argv[3] == 'hang':
            time.sleep(10)  # Failsafe synthetic bound; parent must terminate first.
        return 7
    finally:
        k.CloseHandle(event)


if __name__ == '__main__':
    raise SystemExit(_child() if sys.platform == 'win32' else 21)
