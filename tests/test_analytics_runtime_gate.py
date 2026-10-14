"""Offline deterministic tests for the narrow pre-expansion guards."""
import json
import asyncio
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.analytics.resource_limits import json_cost
from app.api.analytics_routes import _validate_snapshots
from tests.test_analytics_api import analytics, get
from tests.test_discovery_history_api_behavior import workspace


@pytest.mark.parametrize('raw', ['[' * 65 + '0' + ']' * 65, '[', '"unterminated', ']'])
def test_reject_before_json_expansion(raw):
    event = SimpleNamespace(snapshot_json=raw, attempted_sources_json='[]',
                            successful_sources_json='[]', failed_sources_json='[]')
    with patch('app.api.analytics_routes._json', side_effect=AssertionError('parsed too soon')):
        with pytest.raises(HTTPException) as error:
            _validate_snapshots(SimpleNamespace(events=[event]))
    assert error.value.status_code == 503


def test_strings_escapes_and_depth_boundary():
    raw = json.dumps({'items': [], 'extra': '"\\' + '[{,:}]' * 100})
    assert json_cost(raw) < 20
    assert json_cost('[' * 64 + '0' + ']' * 64) == 64


def test_many_events_share_one_expansion_budget():
    raw = json.dumps({'items': [], 'extra': [0] * 60000})
    event = SimpleNamespace(snapshot_json=raw, attempted_sources_json='[]',
                            successful_sources_json='[]', failed_sources_json='[]')
    with pytest.raises(HTTPException) as error:
        _validate_snapshots(SimpleNamespace(events=[event] * 4))
    assert error.value.status_code == 503


@pytest.mark.parametrize('raw', ['{"items":[],"x":NaN}', '{"items":[],"items":[]}', '{"items":[],"x":}'])
def test_invalid_json_stays_fail_closed(raw):
    event = SimpleNamespace(snapshot_json=raw, attempted_sources_json='[]',
                            successful_sources_json='[]', failed_sources_json='[]')
    with pytest.raises(HTTPException) as error:
        _validate_snapshots(SimpleNamespace(events=[event]))
    assert error.value.status_code == 503


def test_query_bytes_rejected_before_authorization_storage(analytics):
    w, repo, company, base, persist, record = analytics
    with patch('app.api.analytics_routes._authorize', side_effect=AssertionError('authorization dispatched')):
        assert get(w, base, category='x' * 17000).status_code == 422


def test_overlapping_reads_and_cancelled_awaiter_do_not_stop_worker():
    # Exercise the same to_thread + BoundedHistory boundary used by _load.
    # This proves the remaining hazard, not a hard-cancellation guarantee.
    from app.api.analytics_routes import BoundedHistory
    entered = [threading.Event(), threading.Event()]
    release = threading.Event()
    exited = [threading.Event(), threading.Event()]

    class Repository:
        def __init__(self, index):
            self.index = index

        def page_discovery_history(self, **kwargs):
            entered[self.index].set()
            try:
                if not release.wait(5):
                    raise AssertionError('test worker was not released')
                return dict(observed_count=0, records=[])
            finally:
                exited[self.index].set()

    async def exercise():
        tasks = [asyncio.create_task(asyncio.to_thread(
            BoundedHistory(Repository(i), None, time.monotonic() + 20).page_discovery_history))
            for i in range(2)]
        try:
            for event in entered:
                assert await asyncio.to_thread(event.wait, 3)
            tasks[0].cancel()
            with pytest.raises(asyncio.CancelledError):
                await tasks[0]
            assert not exited[0].is_set()
            assert not exited[1].is_set()
        finally:
            release.set()
            await asyncio.gather(*tasks, return_exceptions=True)
            for event in exited:
                assert await asyncio.to_thread(event.wait, 3)

    asyncio.run(exercise())
