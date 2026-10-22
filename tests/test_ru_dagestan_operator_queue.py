"""Offline safeguards: only operator-enabled genuine Dagestan source can be enqueued.

This test does not claim real network availability or subscriber delivery.
"""
import pytest

from app.monitoring.config import MonitoringSettings
from app.sources.catalog import build_source_catalog
from app.sources.ru_cycle import RU_APPROVED_SOURCES, approved_ru_keys, enqueue_approved_ru


def catalog(*, dagestan=False):
    return build_source_catalog(MonitoringSettings(
        enabled=False,
        interval_seconds=600,
        max_items=2,
        max_notifications_per_cycle=2,
        request_timeout=25,
        eis_rss_urls=(),
        ca_bundle_file=None,
        profile_feeds_enabled=False,
        ru_dagestan_public_list_enabled=dagestan,
    ))


def test_dagestan_not_queued_without_operator_opt_in():
    assert "ru_dagestan_public_list" in RU_APPROVED_SOURCES
    with pytest.raises(ValueError, match="No operator-approved"):
        approved_ru_keys(catalog(dagestan=False))


def test_dagestan_only_queued_after_explicit_opt_in():
    cat = catalog(dagestan=True)
    assert approved_ru_keys(cat) == ("ru_dagestan_public_list",)

    class Queue:
        def __init__(self):
            self.called = []
        def enqueue(self, source, *, now=None):
            self.called.append((source, now))
            return type("Job", (), {"id":"synthetic-test-only", "state":"queued"})()

    queue = Queue()
    result = enqueue_approved_ru(queue, cat, now=1800000000)
    assert list(result) == ["ru_dagestan_public_list"]
    assert queue.called == [("ru_dagestan_public_list", 1800000000)]
    assert result["ru_dagestan_public_list"]["state"] == "queued"
