"""Process-local finite admission. Cancellation never terminates a thread."""
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from functools import partial
from fastapi import HTTPException
from fastapi.routing import APIRoute

current_lease = ContextVar('analytics_lease', default=None)


class Admission:
    def __init__(self, limit=2):
        if limit < 1:
            raise ValueError('Positive admission limit required')
        self.limit = limit
        self.leases = set()
        self.pending = set()
        self.closing = False
        self.executor = ThreadPoolExecutor(max_workers=limit, thread_name_prefix='analytics-H')

    def acquire(self):
        # All state is owned by the application event loop; no await between check/add.
        if self.closing or len(self.leases) >= self.limit:
            raise HTTPException(503, 'Analytics capacity unavailable; retry later.',
                                headers={'Retry-After': '1', 'Cache-Control': 'no-store'})
        lease = Lease(self)
        self.leases.add(lease)
        return lease

    async def shutdown(self):
        self.closing = True
        # Requests must have unwound before runtime repositories are closed.
        while self.leases:
            await asyncio.gather(*(lease.finished.wait() for lease in tuple(self.leases)))
        self.executor.shutdown(wait=True, cancel_futures=False)


class Lease:
    def __init__(self, owner):
        self.owner = owner
        self.pending = set()
        self.closed = False
        self.finished = asyncio.Event()
        self.deadline = time.monotonic() + 10

    def close(self):
        self.closed = True
        self._release()

    def _release(self):
        if self.closed and not self.pending:
            self.owner.leases.discard(self)
            self.finished.set()

    def check_deadline(self):
        if time.monotonic() >= self.deadline:
            raise HTTPException(503, "Analytics time budget exceeded; narrow search interval.")

    async def run(self, function, *args, **kwargs):
        if self.closed or self.pending:
            raise RuntimeError('Analytics lease is closed or already executing')
        self.check_deadline()
        future = asyncio.get_running_loop().run_in_executor(
            self.owner.executor, partial(function, *args, **kwargs))
        self.pending.add(future)
        self.owner.pending.add(future)
        def completed(done):
            # Retrieve exceptions even after the HTTP awaiter has gone away.
            if not done.cancelled():
                done.exception()
            self.pending.discard(done)
            self.owner.pending.discard(done)
            self._release()
        future.add_done_callback(completed)
        result = await asyncio.shield(future)
        self.check_deadline()
        return result


class HistoryRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def admitted(request):
            if '/history/' not in self.path:
                return await handler(request)
            lease = request.app.state.analytics_admission.acquire()
            token = current_lease.set(lease)
            try:
                return await handler(request)
            finally:
                current_lease.reset(token)
                lease.close()
        return admitted


async def dispatch(function, *args, **kwargs):
    lease = current_lease.get()
    if lease is None:
        return await asyncio.to_thread(function, *args, **kwargs)
    return await lease.run(function, *args, **kwargs)
