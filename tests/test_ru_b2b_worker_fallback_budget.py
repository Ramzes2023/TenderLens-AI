"""B2B root+same-origin office fallback requires two fenced Worker requests.

This is an OFFLINE regression for request allocation only; genuine upstream
proof remains a separate mandatory GitHub live job, never inferred here.
"""
from types import SimpleNamespace

from app.monitoring.config import MonitoringSettings
from app.sources.b2b_center import B2BCenterSource
from app.sources.catalog import build_source_catalog
from app.sources.http import _policy
from app.sources.ingestion import (
    ConnectorSyncHandler, SYSTEM_SCOPE, connector_version, sync_window,
)
from app.sources.models import TenderNotice


def test_b2b_fenced_worker_permits_bounded_original_office_fallback(monkeypatch):
    config = MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=10,
        max_notifications_per_cycle=5, request_timeout=25,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
        b2b_center_enabled=True,
    )
    catalog = build_source_catalog(config)
    observed = []

    async def only_in_process_budget_probe(self, limit):
        budget = _policy.get()
        observed.append((budget.max_requests, budget.hosts, limit))
        assert budget.max_requests == 2
        assert budget.hosts == frozenset({"www.b2b-center.ru"})
        return [TenderNotice(
            source="b2b_center", external_id="A123",
            title="Официальная проверка ограничения запросов",
            url="https://www.b2b-center.ru/search/number/A123/",
        )]

    monkeypatch.setattr(B2BCenterSource, "fetch", only_in_process_budget_probe)

    class EphemeralSink:
        def upsert_fenced(self, row, version, fenced_write):
            assert row.source == "b2b_center"
            assert version == connector_version("b2b_center")
            return True

    handler = ConnectorSyncHandler(catalog, EphemeralSink(), max_records=5)
    job = SimpleNamespace(scope=SYSTEM_SCOPE)
    result = handler(SimpleNamespace(job=job, should_stop=False), {
        "schema": 1,
        "source_id": "b2b_center",
        "sync_window": sync_window(),
        "connector_version": connector_version("b2b_center"),
    })
    assert observed == [(2, frozenset({"www.b2b-center.ru"}), 5)]
    assert result["inserted_count"] == result["accepted_count"] == 1
