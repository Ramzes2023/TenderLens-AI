"""Deterministic seven-source queue+search operator contracts; no live network."""
from __future__ import annotations

import asyncio
import json
from dataclasses import replace

import pytest

from app.sources.asia_public import ASIA_RSS_FEEDS
from app.sources.asia_seven import SOURCES, main, search_stored, validate_sources
from app.sources.jp_jetro_bid_rss import SOURCE_ID as JETRO
from app.sources.models import TenderNotice
from app.sources.ingestion import HOSTS, connector_version
from app.sources.opportunities import OpportunityRepository


def notice(source, external_id, title="Medical equipment tender"):
    host = next(iter(HOSTS[source]))
    return TenderNotice(
        source=source, external_id=external_id, title=title,
        url=f"https://{host}/procurement/bid/2026/{external_id}",
        published_at="2026-10-16", region="Asia",
    )


def test_seven_are_six_hong_kong_plus_own_jetro_rss():
    assert SOURCES == (*ASIA_RSS_FEEDS, JETRO)
    assert len(SOURCES) == len(set(SOURCES)) == 7
    assert JETRO not in ASIA_RSS_FEEDS
    assert all(HOSTS[key] for key in SOURCES)


def test_dry_run_is_non_mutating_and_does_not_need_configuration(monkeypatch, capsys):
    monkeypatch.delenv("VALYQON_ASIA_OPERATIONS_ENABLED", raising=False)
    assert main([]) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["mode"] == "dry_run"
    assert value["enqueued"] == 0
    assert value["production_changed"] is False
    assert len(value["sources"]) == 7


def test_flags_required_before_any_enqueue(monkeypatch):
    from scripts.asia_six_live_acceptance import settings
    from app.sources.catalog import build_source_catalog

    monkeypatch.delenv("VALYQON_ASIA_SOURCES_ENABLED", raising=False)
    monkeypatch.delenv("VALYQON_ASIA_JETRO_BID_ENABLED", raising=False)
    with pytest.raises(ValueError):
        validate_sources(build_source_catalog(settings()))
    monkeypatch.setenv("VALYQON_ASIA_SOURCES_ENABLED", "1")
    with pytest.raises(ValueError):
        validate_sources(build_source_catalog(settings()))
    monkeypatch.setenv("VALYQON_ASIA_JETRO_BID_ENABLED", "1")
    cat = build_source_catalog(settings())
    assert validate_sources(cat) == SOURCES


def test_operator_gate_rejects_unapproved_access(monkeypatch, capsys):
    monkeypatch.delenv("VALYQON_ASIA_OPERATIONS_ENABLED", raising=False)
    assert main(["--search", "equipment"]) == 2
    assert "failed" in capsys.readouterr().out
    assert main(["--enqueue"]) == 2


@pytest.mark.parametrize("term", ["", "\x00abc", "a", "a" * 121, "\nfoo"])
def test_invalid_search_queries_fail_closed(term):
    class Forbidden:
        def read(self, *args, **kwargs):
            pytest.fail("Invalid input must not read DB")
    with pytest.raises(ValueError):
        search_stored(Forbidden(), term)


def test_stored_keyword_search_is_local_bounded_seven_source_only():
    class FakeStore:
        def __init__(self):
            self.calls = []
        def read(self, source, limit=20, search_terms=()):
            self.calls.append((source, limit, search_terms))
            return [notice(source, source + "-one")] if search_terms == ("equipment",) else []

    store = FakeStore()
    result = search_stored(store, "equipment", limit=7)
    assert len(result) == 7
    assert set(x["source"] for x in result) == set(SOURCES)
    assert all(x["title"] == "Medical equipment tender" for x in result)
    assert store.calls == [(source, 7, ("equipment",)) for source in SOURCES]



def test_source_scoped_search_never_reads_other_sources():
    class FakeStore:
        def __init__(self):
            self.calls = []
        def read(self, source, limit=20, search_terms=()):
            self.calls.append(source)
            return [notice(source, source + "-one")]

    store = FakeStore()
    found = search_stored(store, "equipment", limit=5, source=JETRO)
    assert store.calls == [JETRO]
    assert len(found) == 1 and found[0]["source"] == JETRO
    with pytest.raises(ValueError):
        search_stored(store, "equipment", limit=5, source="evil_unknown")
    assert store.calls == [JETRO]


def test_seven_real_queue_and_snapshot_path_offline_fixture(tmp_path, monkeypatch):
    """All seven actual source IDs use the real job/worker/schema/storage/search."""
    from app.database.backend import Database
    from app.database.config import DatabaseSettings
    from app.jobs import HandlerRegistry, JobRepository, JobService
    from app.jobs.worker import Worker
    from app.sources.catalog import build_source_catalog
    from app.sources.ingestion import JOB_TYPE, SYSTEM_SCOPE, ConnectorSyncHandler, ConnectorSyncService
    from app.sources.snapshots import snapshot_catalog
    from scripts.asia_six_live_acceptance import settings

    monkeypatch.setenv("VALYQON_ASIA_SOURCES_ENABLED", "1")
    monkeypatch.setenv("VALYQON_ASIA_JETRO_BID_ENABLED", "1")
    cat = build_source_catalog(settings())
    assert validate_sources(cat) == SOURCES
    # Only mocked official-source fetch; production implementation stays intact.
    for key in SOURCES:
        source = cat.registry.get(key).source
        async def fake_fetch(limit=20, *, identity=key):
            return [notice(identity, "sample-" + identity)]
        object.__setattr__(source, "fetch", fake_fetch)

    db = Database(DatabaseSettings("seven-fixture", tmp_path / "seven.sqlite"))
    try:
        jobs = JobRepository(db)
        jobs.initialize()
        store = OpportunityRepository(db)
        store.initialize()
        service = ConnectorSyncService(JobService(jobs), cat)
        handlers = HandlerRegistry()
        handlers.register(JOB_TYPE, ConnectorSyncHandler(cat, store, max_records=3))
        worker = Worker(jobs, handlers, job_types=(JOB_TYPE,))
        scheduled = [service.enqueue(key) for key in SOURCES]
        for _ in scheduled:
            assert worker.run_once() is True
        assert all(jobs.get(job.id, scope=SYSTEM_SCOPE).state == "succeeded" for job in scheduled)
        assert len(search_stored(store, "equipment", limit=10)) == 7
        assert len(search_stored(store, "nonsense-unmatched", limit=10)) == 0
        assert all(service.enqueue(key).id == scheduled[i].id for i, key in enumerate(SOURCES))
        snap = snapshot_catalog(cat, store)
        report = asyncio.run(snap.fetch(source_keys=SOURCES, search_terms=("equipment",)))
        assert len(report.notices) == 7 and not report.failures
    finally:
        db.close()
