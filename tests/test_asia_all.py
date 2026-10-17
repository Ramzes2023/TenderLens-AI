"""All-fourteen operator contracts; live HTTP is separately covered by hosted source jobs."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import pytest

from app.sources.asia_all import FLAGS, SOURCES, main, stored_search, validate_batch
from app.sources.models import TenderNotice


def test_roster_unique_approved_and_env_flags_exact():
    from app.sources.asia_public import ASIA_RSS_FEEDS
    from app.sources.hk_hyd_tenders import SOURCE_ID as HYD
    from app.sources.jp_jetro_bid_rss import SOURCE_ID as JETRO
    from app.sources.hk_hkma_tender import SOURCE_ID as HKMA
    from app.sources.india_epublish import SOURCE_ID as INDIA
    from app.sources.uae_mof_rfqs import SOURCE_ID as UAE
    from app.sources.tr_ankara_municipality import SOURCE_ID as ANKARA
    from app.sources.sg_gebiz_rss import FEEDS
    from app.sources.ingestion import HOSTS

    assert SOURCES == (*ASIA_RSS_FEEDS, JETRO, HYD, *FEEDS, HKMA, INDIA, UAE, ANKARA)
    assert len(SOURCES) == len(FLAGS) == len(set(SOURCES)) == 14
    assert all(key in HOSTS and HOSTS[key] for key in SOURCES)


def test_dry_run_never_requires_db_network_or_credentials(monkeypatch, capsys):
    monkeypatch.delenv("VALYQON_ASIA_OPERATIONS_ENABLED", raising=False)
    assert main([]) == 0
    doc=json.loads(capsys.readouterr().out)
    assert doc["total_sources"] == 14
    assert doc["enqueued"] == 0 and doc["production_changed"] is False
    assert doc["mode"] == "dry_run"


def test_all_ten_require_explicit_activation_and_approved_routing(monkeypatch):
    from scripts.asia_six_live_acceptance import settings
    from app.sources.catalog import build_source_catalog

    for flag in set(FLAGS.values()):
        monkeypatch.delenv(flag, raising=False)
    with pytest.raises(ValueError):
        validate_batch(build_source_catalog(settings()))
    for flag in set(FLAGS.values()):
        monkeypatch.setenv(flag, "1")
    catalog=build_source_catalog(settings())
    assert validate_batch(catalog) == SOURCES
    assert validate_batch(catalog, sources=("sg_gebiz_professional",)) == (
        "sg_gebiz_professional",)
    with pytest.raises(ValueError):
        validate_batch(catalog, sources=("sg_gebiz_misc", "sg_gebiz_misc"))
    with pytest.raises(ValueError):
        validate_batch(catalog, sources=("malicious",))
    monkeypatch.setenv("VALYQON_ASIA_GEBIZ_ENABLED", "0")
    with pytest.raises(ValueError):
        validate_batch(catalog, sources=("sg_gebiz_professional",))
    # Independent Japan can still enqueue when Singapore flag is off.
    assert validate_batch(catalog, sources=("jp_jetro_bid",)) == ("jp_jetro_bid",)


def test_operator_gate_fails_closed_before_database(monkeypatch, capsys):
    monkeypatch.delenv("VALYQON_ASIA_OPERATIONS_ENABLED", raising=False)
    assert main(["--enqueue"]) == 2
    assert main(["--search", "equipment"]) == 2
    assert "blocked" in capsys.readouterr().out


@pytest.mark.parametrize("word", ["", "x", "\nxyz", "123\x00AB", "\tword", "x"*121])
def test_invalid_search_before_storage(word):
    class Forbidden:
        def read(self,*args,**kwargs):
            pytest.fail("Bad input must not access store")
    with pytest.raises(ValueError):
        stored_search(Forbidden(), word)


def test_source_scoped_query_does_not_expose_other_sources():
    class Store:
        def __init__(self): self.calls=[]
        def read(self,source,limit=20,search_terms=()):
            self.calls.append((source,search_terms))
            return [TenderNotice(source,source+"-123","Hospital equipment tender",
                                "https://www.gebiz.gov.sg/public/bid")]
    store=Store()
    result=stored_search(store,"equipment",source="sg_gebiz_misc")
    assert len(result)==1 and result[0]["source"]=="sg_gebiz_misc"
    assert store.calls==[("sg_gebiz_misc",("equipment",))]
    assert len(stored_search(store,"equipment",limit=14)) == 14
    assert len(store.calls)==15


def test_all_ten_genuine_queue_worker_db_snapshot_path_with_offline_sole_network_stub(
    tmp_path, monkeypatch,
):
    """Uses real queue, worker, lease fencing, DB, profiles and snapshot search."""
    from app.database.backend import Database
    from app.database.config import DatabaseSettings
    from app.jobs import HandlerRegistry, JobRepository, JobService
    from app.jobs.worker import Worker
    from app.sources.catalog import build_source_catalog
    from app.sources.ingestion import JOB_TYPE, SYSTEM_SCOPE, ConnectorSyncHandler, ConnectorSyncService, HOSTS
    from app.sources.opportunities import OpportunityRepository
    from app.sources.snapshots import snapshot_catalog
    from scripts.asia_six_live_acceptance import settings

    for flag in set(FLAGS.values()):
        monkeypatch.setenv(flag, "1")
    cat=build_source_catalog(settings())
    assert validate_batch(cat) == SOURCES

    for key in SOURCES:
        registered=cat.registry.get(key).source
        async def fake_fetch(limit=20, *, identity=key):
            host=sorted(HOSTS[identity])[0]
            return [TenderNotice(
                source=identity, external_id="proof-"+identity,
                title="Verified source equipment opportunity",
                url="https://"+host+"/public/tender/proof-"+identity,
                published_at="2026-10-16", region="Asia",
            )]
        object.__setattr__(registered, "fetch", fake_fetch)

    db=Database(DatabaseSettings("asia-all-test",tmp_path/"all.db"))
    try:
        jobs=JobRepository(db);jobs.initialize()
        store=OpportunityRepository(db);store.initialize()
        service=ConnectorSyncService(JobService(jobs),cat)
        handlers=HandlerRegistry()
        handlers.register(JOB_TYPE,ConnectorSyncHandler(cat,store,max_records=2))
        worker=Worker(jobs,handlers,job_types=(JOB_TYPE,))
        clock=datetime(2026,10,16,12,tzinfo=timezone.utc)
        queued=[service.enqueue(key,now=clock) for key in SOURCES]
        for _ in queued:
            assert worker.run_once()
        assert all(jobs.get(job.id,scope=SYSTEM_SCOPE).state=="succeeded" for job in queued)
        assert len(stored_search(store,"equipment",limit=20))==14
        assert len(stored_search(store,"nonexistent",limit=20))==0
        snap=snapshot_catalog(cat,store)
        report=asyncio.run(snap.fetch(source_keys=SOURCES,search_terms=("equipment",)))
        assert len(report.notices)==14 and not report.failures
        assert [service.enqueue(key,now=clock).id for key in SOURCES] == [job.id for job in queued]
    finally:
        db.close()
