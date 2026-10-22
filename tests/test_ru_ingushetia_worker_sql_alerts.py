"""Offline operator-only Ingushetia Worker-SQL alert freshness contracts.

Synthetic saved tenders: not proof of current external feeds or Telegram delivery.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.monitoring.config import MonitoringSettings, load_monitoring_settings
from app.sources.catalog import build_source_catalog
from app.sources.ingestion import connector_version
from app.sources.models import TenderNotice
from app.sources.opportunities import OpportunityRepository
from app.sources.snapshots import (
    FreshIngushetiaWorkerSource, fresh_ingushetia_worker_catalog,
)

EIS = "ru_ingushetia_eis44"
FAB = "ru_ingushetia_fabrikant44"
N1 = "0114500000826002402"
N2 = "0114500000826002403"


def settings(**flags):
    values = dict(
        enabled=True, interval_seconds=600, max_items=20,
        max_notifications_per_cycle=5, request_timeout=25,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
        ru_background_catalog_enabled=True, ru_ingushetia_eis44_enabled=True,
        ru_ingushetia_fabrikant44_enabled=True,
        ru_ingushetia_worker_sql_alerts_enabled=True,
    )
    values.update(flags)
    return MonitoringSettings(**values)


def notice(number, source=EIS, title="Поставка медицинского оборудования"):
    url = ("https://zakupki.gov.ru/epz/order/notice/ea20/view/common-info.html?regNumber="
           + number if source == EIS
           else "https://44.fabrikant.ru/44/procedure/ea21/" + number)
    return TenderNotice(
        source=source, external_id=number, tender_number=number, title=title,
        customer="Комитет государственного заказа Республики Ингушетия",
        region="Республика Ингушетия", url=url,
    )


def test_worker_sql_alert_mode_opt_in_only(monkeypatch, tmp_path):
    path = tmp_path / "absent-env"
    monkeypatch.delenv("VALYQON_RU_INGUSHETIA_WORKER_SQL_ALERTS_ENABLED", raising=False)
    assert load_monitoring_settings(path).ru_ingushetia_worker_sql_alerts_enabled is False
    monkeypatch.setenv("VALYQON_RU_INGUSHETIA_WORKER_SQL_ALERTS_ENABLED", "true")
    assert load_monitoring_settings(path).ru_ingushetia_worker_sql_alerts_enabled is True
    monkeypatch.setenv("VALYQON_RU_INGUSHETIA_WORKER_SQL_ALERTS_ENABLED", "unexpected")
    with pytest.raises(ValueError):
        load_monitoring_settings(path)


def test_no_enabled_regional_source_cannot_switch_catalog():
    catalog = build_source_catalog(settings(
        ru_ingushetia_eis44_enabled=False,
        ru_ingushetia_fabrikant44_enabled=False,
    ))
    with pytest.raises(ValueError, match="No operator-enabled"):
        fresh_ingushetia_worker_catalog(catalog, object())


def test_fresh_sql_isolated_from_live_origin_and_read_only(tmp_path):
    db = Database(DatabaseSettings("ing-snapshot-test", tmp_path / "stored.sqlite"))
    repo = OpportunityRepository(db)
    repo.initialize()
    base = build_source_catalog(settings())
    alternate = base.registry.get("eis").source
    local = fresh_ingushetia_worker_catalog(base, repo)
    assert local.registry.get("eis").source is alternate
    assert isinstance(local.registry.get(EIS).source, FreshIngushetiaWorkerSource)
    assert isinstance(local.registry.get(FAB).source, FreshIngushetiaWorkerSource)
    assert base.registry.get(EIS).source is not local.registry.get(EIS).source

    async def observe():
        empty = await local.fetch(source_keys=(EIS, FAB))
        assert set(f.source for f in empty.failures) == {EIS, FAB}
        assert empty.total_failure and not empty.notices
        return empty

    asyncio.run(observe())
    try:
        repo.upsert(notice(N1), connector_version(EIS))
        result = asyncio.run(local.fetch(source_keys=(EIS, FAB)))
        assert len(result.notices) == 1
        assert result.notices[0].tender_number == N1
        assert tuple(result.successful_sources) == (EIS,)
        assert {x.source for x in result.failures} == {FAB}
        assert result.partial_failure
        assert list(repo.read(EIS, limit=5))[0].tender_number == N1
        assert [n.tender_number for n in asyncio.run(
            local.registry.get(EIS).source.for_search_terms(("оборудования",)).fetch()
        )] == [N1]
        assert not asyncio.run(
            local.registry.get(EIS).source.for_search_terms(("неизвестно",)).fetch()
        )
    finally:
        db.close()


def test_recent_worker_notice_never_resurrects_other_stale_notice(tmp_path):
    db = Database(DatabaseSettings("ing-snapshot-age", tmp_path / "stored.sqlite"))
    repo = OpportunityRepository(db)
    repo.initialize()
    try:
        repo.upsert(notice(N1), connector_version(EIS))
        repo.upsert(notice(N2, title="Ремонт здания"), connector_version(EIS))
        stale = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
        with db.connect() as conn:
            conn.execute(
                "UPDATE source_opportunities SET last_seen=? WHERE source_id=? AND external_id=?",
                (stale, EIS, N1),
            )
        snap = fresh_ingushetia_worker_catalog(build_source_catalog(settings()), repo)
        matches = asyncio.run(snap.fetch(source_keys=(EIS,)))
        assert [n.tender_number for n in matches.notices] == [N2]
        with db.connect() as conn:
            conn.execute(
                "UPDATE source_opportunities SET last_seen=? WHERE source_id=?",
                (stale, EIS),
            )
        expired = asyncio.run(snap.fetch(source_keys=(EIS,)))
        assert expired.total_failure and expired.failures[0].source == EIS
        assert not expired.notices
        # Legacy saved searches must remain able to inspect historical SQL;
        # freshness is strictly a notification boundary, not destructive DB cleanup.
        assert {x.tender_number for x in repo.read(EIS, limit=5)} == {N1, N2}
    finally:
        db.close()


def test_future_worker_observation_and_naive_cutoff_fail_closed(tmp_path):
    db = Database(DatabaseSettings("ing-snapshot-future", tmp_path / "stored.sqlite"))
    repo = OpportunityRepository(db)
    repo.initialize()
    try:
        repo.upsert(notice(N1), connector_version(EIS))
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        with db.connect() as conn:
            conn.execute("UPDATE source_opportunities SET last_seen=? WHERE source_id=?",
                         (future, EIS))
        snap = fresh_ingushetia_worker_catalog(build_source_catalog(settings()), repo)
        result = asyncio.run(snap.fetch(source_keys=(EIS,)))
        assert result.total_failure and not result.notices
        with pytest.raises(ValueError, match="UTC-aware"):
            repo.read(EIS, not_before=datetime.now())
    finally:
        db.close()
