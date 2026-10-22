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
        # Russian inflection is matched locally, not discarded by a raw SQL
        # substring filter before the real profile matcher can run.
        assert [n.tender_number for n in asyncio.run(
            local.registry.get(EIS).source.for_search_terms(("оборудование",)).fetch()
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


def test_fresh_worker_sql_reaches_per_chat_monitor_only_after_valid_bot_ack(tmp_path):
    """Offline production-component chain: Worker SQL -> profile -> receipt -> seen."""
    from types import SimpleNamespace
    from app.bot.monitoring import monitor_loop
    from app.monitoring.repository import MonitoringRepository
    from app.monitoring.service import TenderMonitorService
    from app.scoring.models import CompanyProfile

    db = Database(DatabaseSettings("ing-bot-chain", tmp_path / "stored.sqlite"))
    store = OpportunityRepository(db)
    store.initialize()
    profile = CompanyProfile(
        profile_version="1", company_name="Medical buyer",
        search_keywords=["оборудования"], allowed_regions=["Ингушетия"],
    )
    mrepo = MonitoringRepository(tmp_path / "ack.sqlite")
    mrepo.initialize()
    mrepo.set_subscription(101, 5001, True)
    cfg = settings(ru_ingushetia_fabrikant44_enabled=False)
    live_catalog = build_source_catalog(cfg)
    stored_catalog = fresh_ingushetia_worker_catalog(live_catalog, store)
    service = TenderMonitorService(
        cfg, None, mrepo, None,
        profile_resolver=lambda uid: profile if uid == 101 else None,
    )
    stop = asyncio.Event()
    active = service.active_subscriptions

    async def cycle():
        stop.set()  # Complete exactly one normal monitoring iteration.
        return await active()
    service.active_subscriptions = cycle

    class Bot:
        def __init__(self):
            self.calls = []
        async def send_message(self, chat, message, **kwargs):
            self.calls.append((chat, message))
            if len(self.calls) == 1:
                # First bot response is for the WRONG chat: no SQL seen claim.
                return SimpleNamespace(message_id=42, chat=SimpleNamespace(id=9999))
            return SimpleNamespace(message_id=43, chat=SimpleNamespace(id=chat))

    try:
        store.upsert(notice(N1), connector_version(EIS))
        bot = Bot()
        asyncio.run(monitor_loop(bot, service, stop, source_catalog=stored_catalog))
        assert len(bot.calls) == 1
        assert bot.calls[0][0] == 5001 and N1 in bot.calls[0][1]
        assert not mrepo.seen(101, "eis_44", N1)

        stop.clear()
        asyncio.run(monitor_loop(bot, service, stop, source_catalog=stored_catalog))
        assert len(bot.calls) == 2
        assert mrepo.seen(101, "eis_44", N1)

        stop.clear()
        asyncio.run(monitor_loop(bot, service, stop, source_catalog=stored_catalog))
        assert len(bot.calls) == 2  # Cross-cycle repeat never duplicates a receipt.
    finally:
        db.close()


def test_worker_snapshot_cutoff_accepts_exact_utc_and_rejects_non_utc(tmp_path):
    """UTC zero offset is required and must NOT be treated as invalid."""
    db = Database(DatabaseSettings("ing-snapshot-utc", tmp_path / "utc.sqlite"))
    repo = OpportunityRepository(db)
    repo.initialize()
    try:
        repo.upsert(notice(N1), connector_version(EIS))
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
        assert [n.tender_number for n in repo.read(
            EIS, limit=5, not_before=cutoff,
        )] == [N1]
        # A timezone-aware value with a different offset must be normalized
        # by its caller, not silently accepted by a UTC-only API.
        plus_two = timezone(timedelta(hours=2))
        with pytest.raises(ValueError, match="UTC-aware"):
            repo.read(EIS, not_before=cutoff.astimezone(plus_two))
        with pytest.raises(ValueError, match="UTC-aware"):
            repo.read(EIS, not_before=cutoff.replace(tzinfo=None))
        # Fresh SQL catalog must use the exact same accepted cutoff.
        snap = fresh_ingushetia_worker_catalog(
            build_source_catalog(settings(ru_ingushetia_fabrikant44_enabled=False)), repo,
        )
        report = asyncio.run(snap.fetch(source_keys=(EIS,)))
        assert len(report.notices) == 1 and not report.failures
        assert report.notices[0].tender_number == N1
    finally:
        db.close()
