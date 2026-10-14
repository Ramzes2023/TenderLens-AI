"""P3.9R1: cancellation is not hard termination in the main Admission lifecycle.

No HTTP/auth/DB gate evidence. On Windows, contrast the existing unwired
prototype before reporting the main lifecycle gap. Only that gap may xfail;
startup, cancellation, process termination and cleanup errors must fail normally.
"""
import asyncio
import sys
import threading

import pytest

from app.analytics.admission import Admission


class MissingHardTermination(AssertionError):
    """The request waiter ended while its admitted work remained alive."""


@pytest.mark.xfail(
    strict=True,
    raises=MissingHardTermination,
    reason="P3.9R1 BLOCKED: request cancellation does not terminate admitted thread work",
)
def test_request_cancellation_must_stop_work_before_cleanup():
    async def exercise():
        admission = Admission(1)
        lease = admission.acquire()
        loop = asyncio.get_running_loop()
        entered = asyncio.Event()
        release = threading.Event()
        exited = threading.Event()
        worker_threads = []
        following_phase = []

        def blocking_work():
            worker_threads.append(threading.current_thread())
            loop.call_soon_threadsafe(entered.set)
            try:
                # Fail-safe bound even if orchestration fails; never an infinite wait.
                assert release.wait(8), "test did not release fake workload"
                return 7
            finally:
                exited.set()

        async def request():
            try:
                await lease.run(blocking_work)
                following_phase.append("must not run after cancellation")
            finally:
                # Same ownership transition as HistoryRoute's request finally.
                lease.close()

        task = asyncio.create_task(request())
        missing_transition = False
        try:
            await asyncio.wait_for(entered.wait(), 3)
            assert worker_threads[0].is_alive() and not exited.is_set()
            # An expired boundary deadline cannot interrupt this in-flight function.
            lease.deadline = 0
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 3)
            assert task.cancelled() and lease.closed
            assert following_phase == []
            missing_transition = not exited.is_set()
            if missing_transition:
                assert worker_threads[0].is_alive()
                assert lease in admission.leases and not lease.finished.is_set()
                assert len(lease.pending) == len(admission.pending) == 1
                assert not next(iter(lease.pending)).cancelled()
        finally:
            # Test-owned release is cleanup, NOT evidence of cancellation termination.
            release.set()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            lease.close()
            await asyncio.wait_for(admission.shutdown(), 3)
        assert exited.is_set()
        assert not admission.leases and not admission.pending and not lease.pending
        assert lease.finished.is_set()
        assert worker_threads and all(not thread.is_alive() for thread in worker_threads)

        if sys.platform == "win32":
            import _winapi

            from app.analytics.process_isolation import Prototype, kernel

            prototype = Prototype(1)
            ready = asyncio.Event()
            child_task = asyncio.create_task(
                prototype.run([], mode="hang", seconds=5, started=ready)
            )
            try:
                await asyncio.wait_for(ready.wait(), 3)
                assert len(prototype.active) == 1
                child = next(iter(prototype.active.values()))
                assert child.poll() is None
                # Retain our own proof handle before prototype closes its handle.
                current_process = _winapi.GetCurrentProcess()
                proof_handle = _winapi.DuplicateHandle(
                    current_process, int(child._handle), current_process,
                    0, False, _winapi.DUPLICATE_SAME_ACCESS,
                )
                try:
                    child_task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await asyncio.wait_for(child_task, 3)
                    # Kernel signaling, not waiter cancellation/PID/exit-code inference.
                    assert kernel().WaitForSingleObject(int(proof_handle), 0) == 0
                    assert child.returncode is not None
                    assert not prototype.active and not prototype.tasks
                    assert len(prototype.receipts) == 1
                    assert prototype.receipts[0][:2] == (child.pid, child.returncode)
                    assert child.stdin.closed and child.stdout.closed
                finally:
                    _winapi.CloseHandle(proof_handle)
            finally:
                await prototype.shutdown()
                await asyncio.gather(child_task, return_exceptions=True)

        # Report only after every cleanup and (on Windows) real child proof passes.
        if missing_transition:
            raise MissingHardTermination(
                "Cancelled request and expired deadline left fake thread work alive; "
                "lease/pending ownership cleared only after test-owned release. "
                "Missing: request cancellation -> hard work termination -> cleanup."
            )

    asyncio.run(exercise())
