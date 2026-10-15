"""Deterministic worker lifetime and real ASGI handler admission proofs."""
import asyncio
import threading
from unittest.mock import patch

import httpx
import pytest
from fastapi import HTTPException

from app.analytics.admission import Admission
from tests.test_analytics_api import analytics, get
from tests.test_discovery_history_api_behavior import workspace


@pytest.mark.parametrize('failure', [False, True])
def test_cancelled_worker_slot_shutdown_and_recycling(failure):
    async def exercise():
        gate = Admission(2)
        loop = asyncio.get_running_loop()
        entered = asyncio.Event()
        release = threading.Event()
        lease = gate.acquire()
        other = gate.acquire()
        def worker():
            loop.call_soon_threadsafe(entered.set)
            assert release.wait(10), 'worker not released'
            if failure:
                raise ValueError('private worker error')
            return 7
        task = asyncio.create_task(lease.run(worker))
        shutdown = None
        try:
            await asyncio.wait_for(entered.wait(), 5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            lease.close()
            assert lease in gate.leases and gate.pending
            with pytest.raises(HTTPException) as error:
                gate.acquire()
            assert error.value.status_code == 503
            assert error.value.headers['Retry-After'] == '1'
            other.close()
            recycled = gate.acquire()
            assert await recycled.run(lambda: 9) == 9
            recycled.close()
            shutdown_waiting = asyncio.Event()
            original_wait = lease.finished.wait
            async def observed_wait():
                shutdown_waiting.set()
                await original_wait()
            # Handshake at the actual shutdown join, without timing sleeps.
            with patch.object(lease.finished, 'wait', observed_wait):
                shutdown = asyncio.create_task(gate.shutdown())
                await asyncio.wait_for(shutdown_waiting.wait(), 5)
            assert gate.closing and not shutdown.done()
            with pytest.raises(HTTPException):
                gate.acquire()
        finally:
            release.set()
            other.close()
            lease.close()
            await asyncio.gather(task, return_exceptions=True)
            await asyncio.wait_for(shutdown or gate.shutdown(), 5)
        assert not gate.leases and not gate.pending
        assert all(not thread.is_alive() for thread in gate.executor._threads)
    asyncio.run(exercise())


def test_pre_submit_and_worker_exception_recycle():
    async def exercise():
        gate = Admission(1)
        lease = gate.acquire()
        lease.close()  # cancellation/rejection before submission
        lease = gate.acquire()
        try:
            def fail():
                raise ValueError('private')
            with pytest.raises(ValueError):
                await lease.run(fail)
        finally:
            lease.close()
            await gate.shutdown()
        assert not gate.leases and not gate.pending
    asyncio.run(exercise())


def test_http_overlap_cancel_overload_unrelated_and_reuse(analytics):
    w, repo, company, base, persist, record = analytics
    from app.api import analytics_routes
    original = analytics_routes._load
    async def exercise():
        loop = asyncio.get_running_loop()
        entered = [asyncio.Event(), asyncio.Event()]
        release = threading.Event()
        lock = threading.Lock()
        calls = 0
        def blocked(*args):
            nonlocal calls
            with lock:
                index = calls
                calls += 1
            if index < 2:
                loop.call_soon_threadsafe(entered[index].set)
                assert release.wait(10), 'HTTP worker not released'
            return original(*args)
        gate = w.client.app.state.analytics_admission
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=w.client.app),
                base_url='http://testserver', cookies=dict(w.client.cookies)) as client:
            url = base + '/history/aggregate?timezone_name=Europe/Rome'
            with patch.object(analytics_routes, '_load', blocked):
                tasks = [asyncio.create_task(client.get(url)) for _ in range(2)]
                try:
                    for event in entered:
                        await asyncio.wait_for(event.wait(), 5)
                    response = await client.get(url)
                    assert response.status_code == 503
                    assert response.headers['retry-after'] == '1'
                    assert response.headers['cache-control'] == 'no-store'
                    tasks[0].cancel()  # disconnect-like ASGI coroutine cancellation
                    with pytest.raises(asyncio.CancelledError):
                        await tasks[0]
                    assert len(gate.leases) == 2
                    assert (await client.get(url)).status_code == 503
                    assert (await client.get('/')).status_code == 200
                    assert calls == 2
                finally:
                    release.set()
                    responses = await asyncio.gather(*tasks, return_exceptions=True)
                    for lease in tuple(gate.leases):
                        if lease.closed:
                            await asyncio.wait_for(lease.finished.wait(), 5)
                assert responses[1].status_code == 200
                assert not gate.leases and not gate.pending
                assert (await client.get(url)).status_code == 200
    w.client.portal.call(exercise)


@pytest.mark.parametrize('control', [{'population_token': 'invalid'}, {'category': 'invalid'}])
def test_http_rejections_release_slots(analytics, control):
    w, repo, company, base, persist, record = analytics
    assert get(w, base, **control).status_code == 422
    assert not w.client.app.state.analytics_admission.leases
    assert get(w, base).status_code == 200


@pytest.mark.parametrize('mutation,status', [('revoke', 403), ('profile', 409), ('error', 503)])
def test_calculation_barrier_final_scope_and_exception_cleanup(analytics, mutation, status):
    w, repo, company, base, persist, record = analytics
    from app.api import analytics_routes
    import sqlite3
    original = analytics_routes._calculate
    async def exercise():
        loop = asyncio.get_running_loop()
        entered = asyncio.Event()
        release = threading.Event()
        def blocked(*args):
            output = original(*args)
            loop.call_soon_threadsafe(entered.set)
            assert release.wait(10), 'calculation worker not released'
            if mutation == 'error':
                raise ValueError('private fixture error')
            return output
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=w.client.app),
                base_url='http://testserver', cookies=dict(w.client.cookies)) as client:
            with patch.object(analytics_routes, '_calculate', blocked):
                task = asyncio.create_task(client.get(base + '/history/aggregate?timezone_name=Europe/Rome'))
                try:
                    await asyncio.wait_for(entered.wait(), 5)
                    assert (await client.get('/')).status_code == 200
                    with sqlite3.connect(repo.path) as conn:
                        if mutation == 'revoke':
                            conn.execute('DELETE FROM organization_members WHERE account_id=? AND organization_id=?',
                                         (w.owner.id, w.organization.id))
                    if mutation == 'profile':
                        changed = w.profile('Analytics')
                        changed['product_keywords'] = ['changed']
                        updated = await client.patch(w.url() + '/' + str(company), json={'profile': changed})
                        assert updated.status_code == 200, updated.text
                    release.set()
                    response = await task
                    assert response.status_code == status, response.text
                    assert 'private fixture error' not in response.text
                finally:
                    release.set()
                    await asyncio.gather(task, return_exceptions=True)
            gate = w.client.app.state.analytics_admission
            assert not gate.leases and not gate.pending
    w.client.portal.call(exercise)


def test_lifespan_joins_cancelled_worker_before_runtime_close():
    from app.api.main import create_app
    from app.api.config import ApiSettings
    from types import SimpleNamespace
    async def exercise():
        closed = []
        def close_runtime():
            gate = app.state.analytics_admission
            assert not gate.pending and not gate.leases
            assert all(not thread.is_alive() for thread in gate.executor._threads)
            closed.append(True)
        runtime = SimpleNamespace(close=close_runtime)
        app = create_app(settings=ApiSettings(host='127.0.0.1', port=8000, reload=False, api_key='fixture-signing-key'))
        release = threading.Event()
        entered = asyncio.Event()
        loop = asyncio.get_running_loop()
        with patch("app.api.main.build_runtime", return_value=runtime):
            context = app.router.lifespan_context(app)
            await context.__aenter__()
        try:
            gate = app.state.analytics_admission
            lease = gate.acquire()
            def worker():
                loop.call_soon_threadsafe(entered.set)
                assert release.wait(10)
            task = asyncio.create_task(lease.run(worker))
            try:
                await asyncio.wait_for(entered.wait(), 5)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                lease.close()
            finally:
                release.set()
                await asyncio.gather(task, return_exceptions=True)
        finally:
            await context.__aexit__(None, None, None)
        assert closed == [True]
        assert gate.closing and not gate.pending and not gate.leases
        assert all(not thread.is_alive() for thread in gate.executor._threads)
    asyncio.run(exercise())


@pytest.mark.parametrize('phase', ['session', 'calculation'])
def test_http_cancellation_retains_each_worker_phase(analytics, phase):
    w, repo, company, base, persist, record = analytics
    from app.api import analytics_routes
    target = w.client.app.state.runtime.auth_service if phase == 'session' else analytics_routes
    name = 'account_for_token' if phase == 'session' else '_calculate'
    original = getattr(target, name)
    async def exercise():
        entered = asyncio.Event()
        loop = asyncio.get_running_loop()
        release = threading.Event()
        def blocked(*args, **kwargs):
            loop.call_soon_threadsafe(entered.set)
            assert release.wait(10)
            return original(*args, **kwargs)
        gate = w.client.app.state.analytics_admission
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=w.client.app),
                base_url='http://testserver', cookies=dict(w.client.cookies)) as client:
            with patch.object(target, name, blocked):
                task = asyncio.create_task(client.get(base + '/history/aggregate?timezone_name=Europe/Rome'))
                try:
                    await asyncio.wait_for(entered.wait(), 5)
                    lease = next(iter(gate.leases))
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await task
                    assert lease.closed and lease.pending and lease in gate.leases
                finally:
                    release.set()
                    await asyncio.gather(task, return_exceptions=True)
                    for lease in tuple(gate.leases):
                        await asyncio.wait_for(lease.finished.wait(), 5)
            assert not gate.pending and not gate.leases
            assert (await client.get(base + '/history/aggregate?timezone_name=Europe/Rome')).status_code == 200
    w.client.portal.call(exercise)


def test_deadline_at_worker_boundary_does_not_submit():
    async def exercise():
        gate = Admission(1)
        lease = gate.acquire()
        lease.deadline = 0
        try:
            with pytest.raises(HTTPException) as error:
                await lease.run(lambda: pytest.fail('expired work submitted'))
            assert error.value.status_code == 503
            assert not gate.pending
        finally:
            lease.close()
            await gate.shutdown()
    asyncio.run(exercise())
