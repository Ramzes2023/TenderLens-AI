"""Offline kernel-handle proofs; only fixed owned Windows children."""
import asyncio
import ctypes as C
from ctypes import wintypes as W
import gc
from pathlib import Path
import sys
from unittest.mock import patch
import uuid

import pytest

from app.analytics.p39r2_suspended_child import SuspendedChild
from app.analytics.process_isolation import IsolationError

pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='requires real Windows kernel suspended-start proof')


def handle_count():
    from app.analytics.p39r2_suspended_child import win_kernel
    k = win_kernel()
    k.GetCurrentProcess.restype = W.HANDLE
    k.GetProcessHandleCount.argtypes = [W.HANDLE, C.POINTER(W.DWORD)]
    k.GetProcessHandleCount.restype = W.BOOL
    value = W.DWORD()
    assert k.GetProcessHandleCount(k.GetCurrentProcess(), C.byref(value))
    return value.value


@pytest.fixture(scope='session')
def warmed_runtime():
    import _winapi
    async def exercise():
        event = asyncio.Event()
        task = asyncio.create_task(event.wait())
        await asyncio.sleep(.005)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        await asyncio.gather(task, return_exceptions=True)
        with patch('_winapi.CreateProcess', side_effect=OSError('warmup')):
            with pytest.raises(OSError):
                _winapi.CreateProcess()
        uuid.uuid4()
        Path(__file__).resolve(strict=True)
    # Initialize Windows asyncio/crypto/mock machinery outside operation counts.
    # A second pass must balance exactly: repeated growth is not a warmup excuse.
    asyncio.run(exercise())
    gc.collect()
    before = handle_count()
    asyncio.run(exercise())
    gc.collect()
    assert handle_count() == before, 'runtime warmup itself leaks handles'


@pytest.fixture(autouse=True)
def every_case_preserves_parent_handles(warmed_runtime):
    children = []
    original = SuspendedChild.__init__
    def track(child, **kwargs):
        original(child, **kwargs)
        children.append(child)
    gc.collect()
    before = handle_count()
    with patch.object(SuspendedChild, '__init__', track):
        yield
    for child in children:
        assert all(getattr(child, name) is None for name in ('process', 'thread', 'job', 'event'))
        assert child.pid is None or child.reaped
    # Closed asyncio loops can remain in reference cycles until GC. Count only
    # after collecting both sides; the acceptance criterion remains exact.
    gc.collect()
    assert handle_count() == before


def duplicate(child):
    import _winapi
    current = _winapi.GetCurrentProcess()
    return _winapi.DuplicateHandle(current, child.process, current, 0, False, _winapi.DUPLICATE_SAME_ACCESS)


def clean(child, proof):
    assert child.k.WaitForSingleObject(proof, 0) == 0
    assert child.reaped and type(child.exitcode) is int
    assert all(getattr(child, name) is None for name in ('process', 'thread', 'job', 'event'))
    child.close()  # Terminal cleanup must be idempotent while proof stays valid.
    assert child.k.WaitForSingleObject(proof, 0) == 0


def test_disabled_and_invalid_input_do_not_spawn():
    with pytest.raises(IsolationError, match='candidate_disabled'):
        SuspendedChild()
    child = SuspendedChild(enabled=True)
    try:
        with patch('_winapi.CreateProcess', side_effect=AssertionError('spawned')):
            with pytest.raises(IsolationError, match='invalid_mode'):
                child.start('arbitrary command')
            with pytest.raises(IsolationError, match='invalid_deadline'):
                asyncio.run(child.run(seconds=float('nan')))
    finally:
        child.close()


def test_kernel_suspended_before_assignment_then_completion():
    import _winapi
    child = SuspendedChild(enabled=True)
    proof = None
    try:
        child.start()
        proof = duplicate(child)
        # Kernel suspend count=1 proves primary thread could not execute even
        # interpreter startup. Restore the extra test suspension immediately.
        assert child.k.SuspendThread(child.thread) == 1
        assert child.k.ResumeThread(child.thread) == 2
        assert child.k.WaitForSingleObject(child.event, 100) == 258
        assert child.k.WaitForSingleObject(proof, 0) == 258
        with pytest.raises(IsolationError, match='resume_requires_verified_job'):
            child.resume()
        child.assign()
        assert child.k.WaitForSingleObject(child.event, 50) == 258
        child.resume()
        assert child.k.WaitForSingleObject(child.event, 3000) == 0
        assert child.k.WaitForSingleObject(proof, 3000) == 0
        assert _winapi.GetExitCodeProcess(proof) == 7
    finally:
        try:
            child.close()
            if proof is not None:
                clean(child, proof)
        finally:
            if proof is not None:
                _winapi.CloseHandle(proof)


@pytest.mark.parametrize('action', ['cancel', 'timeout', 'malformed'])
def test_bounded_run_termination_and_cleanup(action):
    import _winapi
    async def exercise():
        child = SuspendedChild(enabled=True)
        ready = asyncio.Event()
        proofs = []
        original = child.start
        def capture(mode):
            result = original(mode)
            proofs.append(duplicate(child))
            return result
        task = None
        try:
            with patch.object(child, 'start', capture):
                task = asyncio.create_task(child.run('malformed' if action == 'malformed' else 'hang',
                    seconds=1 if action == 'timeout' else 3, started=ready))
                if action == 'cancel':
                    await asyncio.wait_for(ready.wait(), 2)
                    assert child.k.WaitForSingleObject(proofs[0], 0) == 258
                    task.cancel()
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await asyncio.wait_for(task, 4)
                else:
                    with pytest.raises(IsolationError, match='^' + ('deadline' if action == 'timeout' else 'invalid_completion') + '$'):
                        await asyncio.wait_for(task, 5)
                    if action == 'timeout':
                        assert ready.is_set(), 'timeout must kill an initialized child'
            assert len(proofs) == 1
            clean(child, proofs[0])
        finally:
            if task is not None:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            try:
                child.close()
            finally:
                for handle in proofs:
                    _winapi.CloseHandle(handle)
    gc.collect()
    before = handle_count()
    for _ in range(3):
        asyncio.run(exercise())
        gc.collect()
        assert handle_count() == before, 'repeated bounded runs leak handles'


def test_assignment_failure_never_executes_and_reaps():
    import _winapi
    child = SuspendedChild(enabled=True)
    proof = None
    try:
        child.start('hang')
        proof = duplicate(child)
        with patch.object(child.k, 'AssignProcessToJobObject', return_value=False):
            with pytest.raises(IsolationError, match='assign_job_winerror_'):
                child.assign()
        assert not child.resumed
        assert child.k.WaitForSingleObject(child.event, 50) == 258
    finally:
        try:
            child.close()
            if proof is not None:
                clean(child, proof)
        finally:
            if proof is not None:
                _winapi.CloseHandle(proof)


def test_create_failure_closes_handles():
    child = SuspendedChild(enabled=True)
    try:
        with patch('_winapi.CreateProcess', side_effect=OSError('synthetic startup failure')):
            with pytest.raises(IsolationError, match='^process_start_failure$'):
                child.start()
        assert all(getattr(child, name) is None for name in ('process', 'thread', 'job', 'event'))
    finally:
        child.close()


def test_success_and_exact_parent_handle_balance():
    async def exercise():
        child = SuspendedChild(enabled=True)
        k = child.k
        k.GetCurrentProcess.restype = W.HANDLE
        k.GetProcessHandleCount.argtypes = [W.HANDLE, C.POINTER(W.DWORD)]
        k.GetProcessHandleCount.restype = W.BOOL
        def count():
            value = W.DWORD()
            assert k.GetProcessHandleCount(k.GetCurrentProcess(), C.byref(value))
            return value.value
        before = count()
        for _ in range(5):
            child = SuspendedChild(enabled=True)
            proof = None
            original = child.start
            def capture(mode):
                nonlocal proof
                result = original(mode)
                proof = duplicate(child)
                return result
            try:
                with patch.object(child, 'start', capture):
                    assert await child.run() == 7
                clean(child, proof)
            finally:
                try:
                    child.close()
                finally:
                    if proof is not None:
                        import _winapi
                        _winapi.CloseHandle(proof)
            assert count() == before, 'persistent handle growth across operations'
    asyncio.run(exercise())


@pytest.mark.parametrize('signaled,assigned', [(False, False), (True, False), (True, True)])
def test_access_denied_requires_owned_kernel_signal(signaled, assigned):
    import _winapi
    child = SuspendedChild(enabled=True)
    proof = None
    try:
        child.start('hang')
        proof = duplicate(child)
        wait = child.k.WaitForSingleObject
        if assigned:
            child.assign()
            assert wait(proof, 0) == 258
        elif signaled:
            assert child.k.TerminateProcess(child.process, 1)
            assert wait(proof, 3000) == 0
        else:
            assert wait(proof, 0) == 258
        calls = []
        def observe(handle, milliseconds):
            calls.append((handle, milliseconds))
            # Force the race at the first poll; all subsequent signal evidence
            # comes from the real owned handle. No PID/exit-code substitution.
            if len(calls) == 1 or (assigned and len(calls) == 2):
                return 258
            return wait(handle, milliseconds if assigned else 0)
        def denied(handle, code):
            assert handle == child.process
            C.set_last_error(5)
            return False
        with patch.object(child.k, 'WaitForSingleObject', observe), patch.object(child.k, 'TerminateProcess', denied):
            if signaled:
                child.close()
            else:
                with pytest.raises(IsolationError, match='^terminate_owned_winerror_5$'):
                    child.close()
                assert child.process and not child.reaped
                assert all(getattr(child, name) for name in ('process', 'thread', 'job', 'event'))
                assert wait(proof, 0) == 258
        assert len(calls) == (3 if assigned else 2)
    finally:
        try:
            child.close()
            if proof is not None:
                clean(child, proof)
        finally:
            if proof is not None:
                _winapi.CloseHandle(proof)
