"""Independent real Windows process proofs, synthetic data and owned cleanup only."""
import asyncio
import sys
import ctypes as C
from ctypes import wintypes as W
from pathlib import Path
import subprocess
import time
from unittest.mock import patch

import pytest

from app.analytics.process_isolation import (Prototype, IsolationError, decode, validate,
    kernel, checked, Extended)

pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='Windows proof only')


def clean(gate, count):
    assert not gate.active and not gate.tasks
    assert len(gate.receipts) == count
    assert all(type(pid) is int and type(code) is int for pid, code, _ in gate.receipts)


@pytest.mark.parametrize('mode,error', [('sum', None), ('exception', 'child_exit'),
    ('crash', 'child_exit'), ('malformed', 'invalid_output'), ('wrong', 'result_mismatch'),
    ('overlong', 'output_limit'), ('hang', 'deadline'), ('memory', None)])
def test_real_process_states(mode, error):
    async def exercise():
        gate = Prototype()
        try:
            if error:
                with pytest.raises(IsolationError, match='^' + error + '$'):
                    ready = asyncio.Event()
                    await gate.run([1, 2, -3], mode=mode, seconds=2 if mode == 'hang' else 3, started=ready)
                if mode == 'hang':
                    assert ready.is_set(), 'deadline must terminate an initialized hung worker'
            else:
                result = await gate.run([1, 2, -3], mode=mode, seconds=3)
                if mode == 'sum':
                    assert result['sum'] == 0 and result['count'] == 3
                else:
                    assert result['allocation_denied'] is True
        finally:
            await gate.shutdown()
        clean(gate, 1)
        if mode == 'crash':
            assert gate.receipts[0][1] == 17
        if mode == 'exception':
            assert gate.receipts[0][1] == 20
        if mode == 'hang':
            assert gate.receipts[0][1] != 0
    asyncio.run(exercise())


@pytest.mark.parametrize('values', [[True], [1.0], [10001], [0] * 129, 'private', {'x': 1}])
def test_invalid_input_never_spawns(values):
    async def exercise():
        gate = Prototype()
        try:
            with patch('app.analytics.process_isolation.subprocess.Popen', side_effect=AssertionError('spawned')):
                with pytest.raises(IsolationError, match='invalid_input'):
                    await gate.run(values)
        finally:
            await gate.shutdown()
        clean(gate, 0)
    asyncio.run(exercise())


def test_protocol_rejects_duplicates_nonfinite_and_executable_data():
    for raw in (b'{"v":1,"v":1}', b'{"x":NaN}', b'{'):
        with pytest.raises(ValueError):
            decode(raw)
    with pytest.raises(IsolationError):
        validate('print(1)', [])


def test_cancel_before_start():
    async def exercise():
        gate = Prototype()
        task = asyncio.create_task(gate.run([]))
        try:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            await gate.shutdown()
        clean(gate, 0)
    asyncio.run(exercise())


def test_cancel_after_start_concurrency_and_shutdown():
    async def exercise():
        gate = Prototype(2)
        events = [asyncio.Event(), asyncio.Event()]
        tasks = [asyncio.create_task(gate.run([], mode='hang', seconds=5, started=e)) for e in events]
        try:
            for e in events:
                await asyncio.wait_for(e.wait(), 3)
            assert len(gate.active) == 2 and len(gate.tasks) == 2
            processes = tuple(gate.active.values())
            with pytest.raises(IsolationError, match='capacity'):
                await gate.run([])
            tasks[0].cancel()
            tasks[0].cancel()  # repeated cancellation cannot interrupt synchronous reap
            with pytest.raises(asyncio.CancelledError):
                await tasks[0]
            assert processes[0].returncode is not None
            assert len(gate.active) == 1
            assert (await gate.run([7]))['sum'] == 7
        finally:
            await gate.shutdown()
            await asyncio.gather(*tasks, return_exceptions=True)
        clean(gate, 3)
        assert all(p.returncode is not None for p in processes)
        with pytest.raises(IsolationError, match='capacity'):
            await gate.run([])
    asyncio.run(exercise())


def test_start_failure_is_redacted_and_releases():
    async def exercise():
        gate = Prototype()
        try:
            with patch('app.analytics.process_isolation.subprocess.Popen', side_effect=OSError('synthetic')):
                with pytest.raises(IsolationError, match='^process_io_failure$'):
                    await gate.run([])
        finally:
            await gate.shutdown()
        clean(gate, 0)
    asyncio.run(exercise())


def test_assignment_failure_kills_owned_unassigned_child():
    async def exercise():
        gate = Prototype()
        real_kernel = kernel
        def failing_kernel():
            k = real_kernel()
            k.AssignProcessToJobObject = lambda *args: False
            return k
        try:
            with patch('app.analytics.process_isolation.kernel', failing_kernel):
                with pytest.raises(IsolationError, match='assign_job_winerror_'):
                    await gate.run([])
        finally:
            await gate.shutdown()
        clean(gate, 1)
    asyncio.run(exercise())


def test_unrestricted_control_allocation_and_job_close_cleanup():
    # Only fixed synthetic child, same runtime. No host-memory exhaustion or page touches.
    import app.analytics.process_isolation as module
    command = [sys._base_executable, '-I', '-S', str(Path(module.__file__).resolve()), '--synthetic-child']
    def spawn():
        return subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, env={'SystemRoot': 'C:\\Windows'},
            close_fds=True, creationflags=subprocess.CREATE_NO_WINDOW, bufsize=0)
    p = spawn()
    try:
        output, _ = p.communicate(validate('memory', []), timeout=5)
        assert p.returncode == 0
        assert output[:2] == b'R\n'
        assert decode(output[2:]) == {'v': 1, 'pid': p.pid, 'allocation_denied': False}
    finally:
        if p.poll() is None:
            p.kill()
        p.wait(timeout=5)
        p.stdout.close()
        p.stdin.close()
        p._handle.Close()
    k, job, p = kernel(), None, None
    try:
        job = k.CreateJobObjectW(None, None)
        checked(job, 'create_job')
        limits = Extended()
        limits.basic.flags = 0x2000
        checked(k.SetInformationJobObject(job, 9, C.byref(limits), C.sizeof(limits)), 'set_job')
        p = spawn()
        checked(k.AssignProcessToJobObject(job, int(p._handle)), 'assign_job')
        p.stdin.write(validate('hang', []))
        p.stdin.close()
        import msvcrt
        pipe = msvcrt.get_osfhandle(p.stdout.fileno())
        deadline = time.monotonic() + 5
        available = W.DWORD()
        while available.value < 2:
            checked(k.PeekNamedPipe(pipe, None, 0, None, C.byref(available), None), 'ready_pipe')
            assert time.monotonic() < deadline
            time.sleep(.005)
        assert p.stdout.read(2) == b'R\n'
        assert p.poll() is None
        checked(k.CloseHandle(job), 'close_job')
        job = None
        # KILL_ON_JOB_CLOSE uses exit status 0 here; timed wait proves death,
        # not an assumed nonzero status. The synthetic child otherwise sleeps 30s.
        assert type(p.wait(timeout=5)) is int
        assert k.WaitForSingleObject(int(p._handle), 0) == 0
    finally:
        if job:
            k.CloseHandle(job)
        if p:
            if p.poll() is None:
                p.kill()
            p.wait(timeout=5)
            p.stdin.close()
            p.stdout.close()
            p._handle.Close()


def test_repeated_jobs_do_not_leak_process_or_pipe_handles():
    async def exercise():
        k = kernel()
        k.GetCurrentProcess.restype = W.HANDLE
        k.GetProcessHandleCount.argtypes = [W.HANDLE, C.POINTER(W.DWORD)]
        def count():
            value = W.DWORD()
            checked(k.GetProcessHandleCount(k.GetCurrentProcess(), C.byref(value)), 'handles')
            return value.value
        gate = Prototype(1)
        before = count()
        try:
            for _ in range(5):
                assert (await gate.run([1]))['sum'] == 1
        finally:
            await gate.shutdown()
        clean(gate, 5)
        assert count() == before
    asyncio.run(exercise())


@pytest.mark.parametrize('raw', [b'{', b'{"v":1,"v":1}', b'x' * 2049,
    b'{"v":1,"mode":"arbitrary command","values":[]}'])
def test_child_independently_rejects_bad_protocol(raw):
    import app.analytics.process_isolation as module
    p = subprocess.Popen([sys._base_executable, '-I', '-S', str(Path(module.__file__).resolve()), '--synthetic-child'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        env={'SystemRoot': 'C:\\Windows'}, close_fds=True, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        output, _ = p.communicate(raw, timeout=5)
        assert p.returncode == 20 and output == b''
    finally:
        if p.poll() is None:
            p.kill()
        p.wait(timeout=5)
        p.stdin.close()
        p.stdout.close()
        p._handle.Close()
