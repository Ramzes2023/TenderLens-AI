"""Offline real worker routing contract for the candidate Russian MikroTon adapter.

These deterministic tests validate policy/DB integration only. They do not
claim that the MikroTon public endpoint currently returns real tenders.
"""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.jobs.models import JobScope
from app.jobs.worker import PermanentJobError
from app.monitoring.config import MonitoringSettings
from app.sources.catalog import build_source_catalog
from app.sources.http import _policy
from app.sources.ingestion import (
    HOSTS, ConnectorSyncHandler, connector_version, sync_window, validate_payload,
)
from app.sources.mikroton_tender import (
    HOST, SOURCE_ID, MikrotonTenderSource, parse_listing,
)
from app.sources.opportunities import OpportunityRepository
from tests.test_mikroton_tender import envelope, item


def _catalog(enabled: bool):
    settings = MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=10,
        max_notifications_per_cycle=5, request_timeout=15,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
    )
    return build_source_catalog(replace(settings, mikroton_tender_enabled=enabled))


def _payload():
    return {
        "schema": 1,
        "source_id": SOURCE_ID,
        "sync_window": sync_window(),
        "connector_version": connector_version(SOURCE_ID),
    }


def test_opt_in_worker_routing_rejects_disabled_source():
    with pytest.raises(PermanentJobError):
        validate_payload(_payload(), _catalog(False).registry)
    enabled = _catalog(True)
    registration = validate_payload(_payload(), enabled.registry)
    assert registration.key == SOURCE_ID
    assert HOSTS[SOURCE_ID] == frozenset({HOST})


def test_worker_preserves_exact_two_list_requests_and_sqlite_query(tmp_path, monkeypatch):
    catalog = _catalog(True)
    requests_observed = []

    async def simulated_two_list_requests(self, limit):
        # Offline adapter stub: ensures the real worker installs the audited
        # bounded policy. Actual live HTTP belongs in the separate strict gate.
        policy = _policy.get()
        assert policy is not None
        assert policy.hosts == frozenset({HOST})
        assert policy.max_requests == 2
        assert 0 <= policy.requests <= 2
        assert limit == 10
        requests_observed.append((policy.hosts, policy.max_requests))
        return parse_listing(envelope([item()]))

    monkeypatch.setattr(MikrotonTenderSource, "fetch", simulated_two_list_requests)
    db = Database(DatabaseSettings("mikroton-worker-isolated", Path(tmp_path) / "test.sqlite"))
    try:
        opportunities = OpportunityRepository(db)
        opportunities.initialize()
        worker = ConnectorSyncHandler(catalog, opportunities, max_records=10)
        context = SimpleNamespace(
            job=SimpleNamespace(scope=JobScope()), should_stop=False,
        )
        first = worker(context, _payload())
        assert first["fetched_count"] == 1
        assert first["accepted_count"] == 1
        assert first["inserted_count"] == 1
        assert first["updated_count"] == 0
        assert first["skipped_count"] == 0

        result = opportunities.read(SOURCE_ID, limit=10, search_terms=("1",))
        assert len(result) == 1
        assert result[0].source == SOURCE_ID
        assert result[0].url == "https://tender.mt52.ru/tenders/1"

        second = worker(context, _payload())
        assert second["inserted_count"] == 0
        assert second["updated_count"] == 1
        assert len(requests_observed) == 2
    finally:
        db.close()

def test_scoring_candidate_is_explicitly_opt_in_only():
    from app.scoring.runs import ScoringInputError, ScoringRunService, validate_configuration
    from app.jobs import JobRepository, JobService
    from app.database.backend import Database
    from app.database.config import DatabaseSettings
    import tempfile
    from pathlib import Path

    assert validate_configuration([SOURCE_ID], 10)["sources"] == [SOURCE_ID]
    with tempfile.TemporaryDirectory(prefix="ru-mikroton-scoring-optin-") as folder:
        db = Database(DatabaseSettings("mikroton-scoring-guard", Path(folder) / "guard.sqlite"))
        try:
            jobs = JobRepository(db)
            jobs.initialize()
            service = ScoringRunService(JobService(jobs), catalog=_catalog(False))
            # The disabled source must be refused before private profile access.
            with pytest.raises(ScoringInputError, match="explicitly configured"):
                service.enqueue(scope=JobScope(1, 1, 1), sources=(SOURCE_ID,))
        finally:
            db.close()
