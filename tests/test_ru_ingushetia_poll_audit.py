"""Synthetic poll sequences, distinct from live audit evidence."""
import asyncio
from types import SimpleNamespace

import httpx

from app.sources.models import TenderNotice
from scripts.ru_ingushetia_poll_audit import PollHistory, poll, EIS, FAB


def notice(number, source=FAB, **changes):
    return TenderNotice(source=source, external_id=number, tender_number=number,
                        title=changes.get("title", "Synthetic procurement"),
                        url="https://44.fabrikant.ru/44/procedure/ea21/" + number)


A, B, C = "0114500000826002390", "0114500000826002391", "0114500000826002392"


def test_reordered_changed_disappeared_and_reappearing_cards_are_not_new():
    h = PollHistory()
    assert h.observe(FAB, [notice(A), notice(B)])["newly_observed_numbers"] == []
    r = h.observe(FAB, [notice(B, title="Updated"), notice(A), notice(C), notice(C)])
    assert r["newly_observed_numbers"] == [C]
    assert r["already_observed_numbers"] == [A, B]
    h.observe(FAB, [notice(C)])
    assert h.observe(FAB, [notice(A), notice(B)])["newly_observed_numbers"] == []
    assert h.observe(EIS, [notice(A, EIS), notice(B, EIS)])["baseline_numbers"] == []
    assert h.observe(EIS, [notice(C, EIS)])["newly_observed_numbers"] == []


def test_failed_poll_preserves_history_and_independent_source_results(monkeypatch):
    from scripts import ru_ingushetia_poll_audit as audit
    h = PollHistory()
    h.observe(FAB, [notice(A)])
    async def failed(limit):
        raise httpx.ReadError("private request information")
    async def eis(limit):
        return [notice(B, EIS)]
    async def checked(notices):
        assert [n.tender_number for n in notices] == [B]
    monkeypatch.setattr(audit, "_check_original_links", checked)
    sources = {FAB: SimpleNamespace(fetch=failed), EIS: SimpleNamespace(fetch=eis)}
    catalog = SimpleNamespace(registry=SimpleNamespace(get=lambda key: SimpleNamespace(source=sources[key])))
    result = asyncio.run(poll(catalog, h, (FAB, EIS)))
    assert result["sources"][FAB]["category"] == "response_read_failure"
    assert result["sources"][EIS]["state"] == "PASS"
    assert h.observe(FAB, [notice(A)])["newly_observed_numbers"] == []
    assert "private" not in str(result)


def test_real_worker_sql_and_monitor_only_alert_unseen_originals_across_polls(tmp_path):
    from datetime import datetime, timedelta, timezone
    from app.database.backend import Database
    from app.database.config import DatabaseSettings
    from app.jobs import HandlerRegistry, JobRepository
    from app.jobs.models import JobScope
    from app.jobs.worker import Worker
    from app.sources.catalog import SourceCatalog
    from app.sources.registry import SourceRegistry, SourceRegistration
    from app.sources.multi import MultiSourceFetcher
    from app.sources.ingestion import JOB_TYPE, ConnectorSyncHandler, ConnectorSyncService
    from app.sources.opportunities import OpportunityRepository
    from app.monitoring.repository import MonitoringRepository
    from app.monitoring.service import TenderMonitorService, prefilter_notice
    from scripts.ci_ru_ingushetia_live_worker import _catalog_settings

    class Source:
        name = FAB
        rows = [notice(A)]
        async def fetch(self, limit):
            return self.rows[:limit]

    source = Source()
    registry = SourceRegistry([SourceRegistration(FAB, "Synthetic poll source", source)])
    catalog = SourceCatalog(registry, MultiSourceFetcher(registry))
    db = Database(DatabaseSettings("synthetic-poll-test", tmp_path / "worker.sqlite"))
    try:
        jobs = JobRepository(db)
        jobs.initialize()
        store = OpportunityRepository(db)
        store.initialize()
        handlers = HandlerRegistry()
        handlers.register(JOB_TYPE, ConnectorSyncHandler(catalog, store, max_records=5))
        worker = Worker(jobs, handlers, job_types=(JOB_TYPE,))
        sync = ConnectorSyncService(jobs, catalog)
        repo = MonitoringRepository(tmp_path / "monitor.sqlite")
        repo.initialize()
        service = TenderMonitorService(_catalog_settings(), None, repo, None)
        now = datetime(2026, 10, 19, tzinfo=timezone.utc)
        for hour, rows, inserted, fresh in (
            (0, [notice(A)], 1, [A]),
            (1, [notice(B), notice(A, title="Changed title")], 1, [B]),
            (2, [notice(A)], 0, []),
        ):
            source.rows = rows
            job = sync.enqueue(FAB, now=now + timedelta(hours=hour))
            assert worker.run_once()
            done = jobs.get(job.id, scope=JobScope())
            assert done.state == "succeeded"
            assert done.result["inserted_count"] == inserted
            assert done.result["updated_count"] == len(rows) - inserted
            stored = store.read(FAB, limit=5)
            matches = [prefilter_notice(n, None) for n in stored]
            unseen = asyncio.run(service.unseen_matches(101, matches))
            assert sorted(m.notice.tender_number for m in unseen) == fresh
            # Offline simulated acknowledgement only; no Telegram API.
            asyncio.run(service.claim_new(101, unseen))
        mirror = prefilter_notice(notice(A, EIS), None)
        assert asyncio.run(service.unseen_matches(101, [mirror])) == []
        assert len(store.read(FAB, limit=5)) == 2
    finally:
        db.close()
