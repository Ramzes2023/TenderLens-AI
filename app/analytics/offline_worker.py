"""Fixed isolated-interpreter entry point for offline fixture tests only.

Audit restrictions precede dependency/application imports. Ordinary user token,
not a restricted token/AppContainer. No claim of hostile-code security isolation.
"""
import ctypes as C
from ctypes import wintypes as W
import os
from pathlib import Path
import sys
import time


def guard(event, args):
    if event.startswith(('socket.', 'subprocess.')) or event in ('os.system', 'os.spawn'):
        raise RuntimeError('forbidden')
    if event == 'open' and isinstance(args[0], (str, bytes)):
        name = os.fsdecode(args[0]).replace('\\', '/').rsplit('/', 1)[-1].casefold().rstrip(' .')
        if name == '.env' or name.startswith(('.env.', '.env:')):
            raise RuntimeError('forbidden')


def peak_working_set():
    class Counters(C.Structure):
        _fields_ = [('cb', W.DWORD), ('faults', W.DWORD)] + [
            (name, C.c_size_t) for name in ('peak_ws', 'ws', 'peak_paged',
                'paged', 'peak_nonpaged', 'nonpaged', 'pagefile', 'peak_pagefile', 'private')]
    kernel = C.WinDLL('kernel32', use_last_error=True)
    kernel.GetCurrentProcess.restype = W.HANDLE
    psapi = C.WinDLL('psapi', use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [W.HANDLE, C.c_void_p, W.DWORD]
    psapi.GetProcessMemoryInfo.restype = W.BOOL
    counters = Counters()
    counters.cb = C.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), C.byref(counters), counters.cb):
        raise RuntimeError('memory_probe')
    return counters.peak_ws


def main():
    if sys.platform != 'win32' or len(sys.argv) not in (2, 3) or (
            len(sys.argv) == 3 and sys.argv[2] != '--hold'):
        raise SystemExit(21)
    sys.addaudithook(guard)
    # Audit-event proof without reading secrets or attempting external traffic.
    probes = [('dotenv', 'open', ('.env', 'r', 0)),
              ('socket', 'socket.__new__', (None, 2, 1, 0)),
              ('dns', 'socket.getaddrinfo', ('example.invalid', 443, 0, 0, 0)),
              ('subprocess', 'subprocess.Popen', ('forbidden', [], None, {}))]
    blocked = []
    for name, event, args in probes:
        try:
            sys.audit(event, *args)
        except RuntimeError:
            blocked.append(name)
        else:
            raise RuntimeError('guard_missing')
    dependency = Path(sys.argv[1])
    if not dependency.is_absolute() or not (dependency / 'pydantic/__init__.py').is_file():
        raise RuntimeError('dependency_setup')
    # Explicit trusted local installation, -S skips site/.pth/startup hooks.
    sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(dependency)]
    from app.analytics.offline_fixture import INPUT_LIMIT, OUTPUT_LIMIT, validate_payload, calculate, stable
    data = validate_payload(sys.stdin.buffer.read(INPUT_LIMIT + 1))
    sys.stdout.buffer.write(b'R\n')
    sys.stdout.buffer.flush()
    if len(sys.argv) == 3:
        time.sleep(30)  # Fixed diagnostic barrier, parent always kills/waits.
    result = calculate(data)
    output = stable({'v': 1, 'pid': os.getpid(), 'result': result,
                     'guards': blocked, 'peak_working_set': peak_working_set()})
    if len(output) > OUTPUT_LIMIT:
        raise RuntimeError('output_limit')
    sys.stdout.buffer.write(output)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        os._exit(20)  # No raw source/setup/validation error leaves the worker.
