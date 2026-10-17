"""Offline-only regression: genuine JobRepository leases for Russian live acceptance scripts."""
from pathlib import Path

import pytest

from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.jobs.models import JobScope
from app.monitoring.config import MonitoringSettings
from app.sources.b2b_center import B2BCenterSource
from app.sources.catalog import build_source_catalog
from app.sources.models import TenderNotice
from app.sources.opportunities import OpportunityRepository
from app.sources.snapshots import snapshot_catalog
from scripts.ci_ru_leased_connector import run_leased_connector

NOTICE = TenderNotice(
    source="b2b_center",
    external_id="B2B12345678",
    title="Поставка вычислительного оборудования",
    url="https://www.b2b-center.ru/search/number/B2B12345678/",
)


def test_real_claim_and_fenced_upsert_use_disposable_sqlite(tmp_path, monkeypatch):
    async def source_fixture(self, limit=20):
        return [NOTICE]

    monkeypatch.setattr(B2BCenterSource, "fetch", source_fixture)
    catalog = build_source_catalog(MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=5,
        max_notifications_per_cycle=5, request_timeout=20,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
        b2b_center_enabled=True,
    ))
    database = Database(DatabaseSettings("ru-fenced-contract", tmp_path / "fence.sqlite"))
    try:
        opportunities = OpportunityRepository(database)
        opportunities.initialize()
        report = run_leased_connector(
            database, catalog, opportunities, "b2b_center", max_records=1
        )
        assert report["fetched_count"] == 1
        assert report["accepted_count"] == 1
        assert report["inserted_count"] == 1
        assert opportunities.read("b2b_center", limit=1)[0].identity == NOTICE.identity
    finally:
        database.close()


def test_disabled_source_fails_before_job_write(tmp_path, monkeypatch):
    catalog = build_source_catalog(MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=5,
        max_notifications_per_cycle=5, request_timeout=20,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
        b2b_center_enabled=False,
    ))
    database = Database(DatabaseSettings("ru-fenced-refusal", tmp_path / "refusal.sqlite"))
    try:
        opportunities = OpportunityRepository(database)
        opportunities.initialize()
        with pytest.raises(Exception):
            run_leased_connector(database, catalog, opportunities, "b2b_center", max_records=1)
        assert opportunities.read("b2b_center") == []
    finally:
        database.close()


def test_all_remaining_live_entrypoints_require_real_durable_worker():
    """Live scripts may not bypass JobRepository with fabricated job contexts."""
    for name in (
        "ci_ru_mikroton_real_worker.py",
        "ci_ru_tektorg_real_worker.py",
    ):
        script = (Path("scripts") / name).read_text(encoding="utf-8")
        assert "from scripts.ci_ru_leased_connector import run_leased_connector" in script
        assert "= run_leased_connector(db, catalog," in script
        assert "SimpleNamespace" not in script
        assert "ConnectorSyncHandler(" not in script
        assert "TemporaryDirectory" in script
        assert "snapshot_catalog" in script
        assert "store.upsert(" in script or "repo.upsert(" in script
