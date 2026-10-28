"""Offline Chechnya real-source registration / Worker release contract only.

These are fixture/tenant guards, NOT proof of a current official procurement.
Real first-party publisher + fenced Worker + customer search is a separate CI job.
"""
import asyncio
from dataclasses import replace
from pathlib import Path

import pytest

from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.jobs import HandlerRegistry, JobRepository, JobSettings
from app.jobs.models import JobScope
from app.jobs.worker import PermanentJobError, Worker
from app.monitoring.config import MonitoringSettings
from app.scoring.runs import ScoringInputError, ScoringRunService, validate_configuration
from app.jobs import JobService
from app.sources.catalog import build_source_catalog
from app.sources.http import _policy
from app.sources.ingestion import (
    HOSTS, JOB_TYPE, ConnectorSyncHandler, ConnectorSyncService,
    connector_version, sync_window, validate_payload,
)
from app.sources.opportunities import OpportunityRepository
from app.sources.ru_chechnya_fabrikant44 import (
    SOURCE_ID, HOST, DETAIL_MIRROR_HOST, ORGANIZER, REGION,
    ChechnyaFabrikant44Source,
)
from app.sources.models import TenderNotice


def cfg(optin=False):
    baseline = MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=3,
        max_notifications_per_cycle=5, request_timeout=25,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
    )
    return build_source_catalog(replace(baseline,
               ru_chechnya_fabrikant44_enabled=optin))


def payload():
    return {"schema": 1, "source_id": SOURCE_ID, "sync_window": sync_window(),
            "connector_version": connector_version(SOURCE_ID)}


def test_disabled_by_default_and_only_fixed_official_origins():
    assert SOURCE_ID not in cfg().enabled_keys
    with pytest.raises(PermanentJobError):
        validate_payload(payload(), cfg().registry)
    registration = validate_payload(payload(), cfg(True).registry)
    assert registration.key == SOURCE_ID
    assert registration.jurisdictions == ("RU",)
    assert registration.enabled
    assert HOSTS[SOURCE_ID] == frozenset({HOST, DETAIL_MIRROR_HOST})
    assert validate_configuration([SOURCE_ID], 3)["sources"] == [SOURCE_ID]


def test_source_scoring_requires_explicit_operator_optin(tmp_path):
    db = Database(DatabaseSettings("chechnya-disabled-score", Path(tmp_path)/"deny.sqlite"))
    try:
        jobs = JobRepository(db)
        jobs.initialize()
        service = ScoringRunService(JobService(jobs), catalog=cfg(False))
        with pytest.raises(ScoringInputError, match="explicitly configured"):
            service.enqueue(scope=JobScope(1, 1, 1), sources=(SOURCE_ID,))
    finally:
        db.close()


def test_actual_fenced_worker_handler_preserves_original_identity(tmp_path, monkeypatch):
    number = "0194200000526005514"
    url = f"https://{HOST}/44/procedure/ea21/{number}"
    found = []

    async def synthetic_fetch(self, limit=20):
        policy = _policy.get()
        assert policy.hosts == HOSTS[SOURCE_ID]
        assert policy.max_requests == 12
        assert limit == 3
        found.append(True)
        return [TenderNotice(
            source=SOURCE_ID, external_id=number, tender_number=number,
            title="Строительство здания общественного назначения",
            url=url, customer=ORGANIZER, region=REGION,
        )]

    monkeypatch.setattr(ChechnyaFabrikant44Source, "fetch", synthetic_fetch)
    db = Database(DatabaseSettings("chechnya-offline-fenced",
                                   Path(tmp_path)/"isolated.sqlite"))
    try:
        repo = JobRepository(db, JobSettings(lease_seconds=240, heartbeat_seconds=10))
        repo.initialize()
        store = OpportunityRepository(db)
        store.initialize()
        catalog = cfg(True)
        claim = ConnectorSyncService(repo, catalog).enqueue(SOURCE_ID)
        handlers = HandlerRegistry()
        handlers.register(JOB_TYPE, ConnectorSyncHandler(catalog, store, max_records=3))
        assert Worker(repo, handlers, job_types=(JOB_TYPE,)).run_once()
        completed = repo.get(claim.id, scope=JobScope())
        assert completed.state == "succeeded"
        assert completed.result["inserted_count"] == 1
        assert store.read(SOURCE_ID, limit=3)[0].tender_number == number
        assert len(found) == 1
    finally:
        db.close()
