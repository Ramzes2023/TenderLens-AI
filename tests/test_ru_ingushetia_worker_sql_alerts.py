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


def test_hourly_operator_queue_notice_remains_fresh_until_next_run_with_bounded_drift(tmp_path):
    """Offline: hourly job identity must not create a 30-minute silent alert gap."""
    from app.sources.snapshots import INGUSHETIA_WORKER_MAX_AGE_SECONDS
    assert INGUSHETIA_WORKER_MAX_AGE_SECONDS == 75 * 60
    db = Database(DatabaseSettings("ing-hourly-ttl", tmp_path / "hourly.sqlite"))
    repo = OpportunityRepository(db)
    repo.initialize()
    try:
        repo.upsert(notice(N1), connector_version(EIS))
        catalog = fresh_ingushetia_worker_catalog(build_source_catalog(settings()), repo)
        # Typical 10-minute notification cycle before next hourly run:
        # the last genuine Worker observation can be 50-70 minutes old.
        earlier = (datetime.now(timezone.utc) - timedelta(minutes=68)).isoformat()
        with db.connect() as conn:
            conn.execute("UPDATE source_opportunities SET last_seen=? WHERE source_id=?",
                         (earlier, EIS))
        report = asyncio.run(catalog.fetch(source_keys=(EIS,)))
        assert not report.failures and [n.tender_number for n in report.notices] == [N1]
        # A missed hourly execution, beyond bounded drift, must NOT
        # resurrect expired tenders or claim a healthy source.
        too_old = (datetime.now(timezone.utc) - timedelta(minutes=76)).isoformat()
        with db.connect() as conn:
            conn.execute("UPDATE source_opportunities SET last_seen=? WHERE source_id=?",
                         (too_old, EIS))
        stale = asyncio.run(catalog.fetch(source_keys=(EIS,)))
        assert stale.total_failure and not stale.notices
        assert stale.failures[0].source == EIS
        # Archived database rows remain visible for explicit saved searches.
        assert [n.tender_number for n in repo.read(EIS, limit=5)] == [N1]
    finally:
        db.close()


def test_worker_sql_26th_candidate_reaches_subscriber_after_keyword_filter(tmp_path):
    """Real local SQLite/monitor path; no external source or Telegram API.

    Insert the ONLY matching record first, then 25 unrelated newer records:
    a pre-tenant max_items=3 SQL/candidate slice would silently drop it.
    """
    from types import SimpleNamespace
    from app.bot.monitoring import monitor_loop
    from app.monitoring.repository import MonitoringRepository
    from app.monitoring.service import TenderMonitorService
    from app.scoring.models import CompanyProfile

    db = Database(DatabaseSettings("ing-late-keyword", tmp_path / "stored.sqlite"))
    store = OpportunityRepository(db)
    store.initialize()
    cfg = settings(
        ru_ingushetia_fabrikant44_enabled=False,
        max_items=3,
        max_notifications_per_cycle=3,
    )
    mrepo = MonitoringRepository(tmp_path / "monitor.sqlite")
    mrepo.initialize()
    mrepo.set_subscription(101, 202, True)
    profile = CompanyProfile(
        profile_version="1", company_name="Drainage services",
        search_keywords=["канализации"],
        allowed_regions=["Ингушетия"],
    )
    service = TenderMonitorService(
        cfg, None, mrepo, None,
        profile_resolver=lambda owner: profile if owner == 101 else None,
    )
    stop = asyncio.Event()
    ordinary_subscriptions = service.active_subscriptions

    async def one_cycle():
        stop.set()
        return await ordinary_subscriptions()

    service.active_subscriptions = one_cycle

    class LocalBot:
        def __init__(self):
            self.calls = []

        async def send_message(self, chat, body, **kwargs):
            self.calls.append((chat, body))
            return SimpleNamespace(message_id=len(self.calls),
                                   chat=SimpleNamespace(id=chat))

    matching = "0114500000826002599"
    try:
        store.upsert(notice(matching, title="Устройство ливневой канализации"),
                     connector_version(EIS))
        for index in range(25):
            number = str(114500000826002500 + index).zfill(19)
            store.upsert(notice(number, title="Поставка канцелярских товаров"),
                         connector_version(EIS))

        # A direct SQL source limit of three excludes the older matching ID.
        assert matching not in {n.tender_number for n in store.read(EIS, limit=3)}

        live_catalog = build_source_catalog(cfg)
        stored_catalog = fresh_ingushetia_worker_catalog(live_catalog, store)
        bot = LocalBot()
        asyncio.run(monitor_loop(bot, service, stop, source_catalog=stored_catalog))
        assert len(bot.calls) == 1
        assert bot.calls[0][0] == 202
        assert matching in bot.calls[0][1]
        assert mrepo.seen(101, "eis_44", matching)

        stop.clear()
        asyncio.run(monitor_loop(bot, service, stop, source_catalog=stored_catalog))
        assert len(bot.calls) == 1  # confirmed item is never resent
    finally:
        db.close()


def test_regional_eis_worker_can_store_26th_real_candidate_without_lifting_other_caps(
        monkeypatch, tmp_path):
    """Offline Worker+SQL contract, not an actual HTTP or Telegram live proof.

    A regional EIS item which falls after the global default 20-result
    ingestion cap must still reach source SQL and per-subscriber search when
    the separately approved regional deep scan is explicitly configured.
    """
    from app.jobs import HandlerRegistry, JobRepository, JobSettings
    from app.jobs.models import JobScope
    from app.jobs.worker import Worker
    from app.sources.ingestion import (
        JOB_TYPE, ConnectorSyncHandler, ConnectorSyncService,
    )
    from app.sources.ru_ingushetia_eis44 import IngushetiaEis44Source
    from app.monitoring.service import TenderMonitorService
    from app.monitoring.repository import MonitoringRepository
    from app.scoring.models import CompanyProfile

    full = []
    for i in range(26):
        number = f"011450000082600{2400 + i:04d}"
        title = "Канализация в Ингушетии" if i == 25 else "Поставка бетона"
        full.append(notice(number, source=EIS, title=title))
    assert len({n.tender_number for n in full}) == 26

    seen_limits = []

    async def synthetic_first_party_rss(self, limit=20):
        seen_limits.append(limit)
        assert self.name == EIS
        return full[:limit]

    monkeypatch.setattr(IngushetiaEis44Source, "fetch", synthetic_first_party_rss)
    db = Database(DatabaseSettings("regional-eis-26th", tmp_path / "worker.sqlite"))
    repo = OpportunityRepository(db)
    repo.initialize()
    cat = build_source_catalog(settings(ru_ingushetia_fabrikant44_enabled=False))
    jobs = JobRepository(db, JobSettings(lease_seconds=240, heartbeat_seconds=10))
    jobs.initialize()
    try:
        # Keep ordinary connectors at 20. Only the separately authorized
        # Ingushetia EIS source can expand to the fixed 100-item safety cap.
        with pytest.raises(ValueError, match="Ingushetia EIS record bound"):
            ConnectorSyncHandler(cat, repo, max_records=20,
                                 ingushetia_eis_max_records=101)
        handlers = HandlerRegistry()
        handlers.register(JOB_TYPE, ConnectorSyncHandler(
            cat, repo, max_records=20, ingushetia_eis_max_records=100,
        ))
        queued = ConnectorSyncService(jobs, cat).enqueue(EIS)
        assert Worker(jobs, handlers, job_types=(JOB_TYPE,)).run_once()
        completed = jobs.get(queued.id, scope=JobScope())
        assert completed is not None and completed.state == "succeeded"
        assert seen_limits == [100] and completed.result["fetched_count"] == 26
        assert completed.result["accepted_count"] == 26
        assert completed.result["inserted_count"] == 26
        assert len(repo.read(EIS, limit=100)) == 26

        regional_sql = fresh_ingushetia_worker_catalog(cat, repo)
        profile = CompanyProfile(
            profile_version="1", company_name="Regional drainage",
            search_keywords=["канализации"],
            allowed_regions=["Ингушетия"],
        )
        monitor = TenderMonitorService(
            settings(ru_ingushetia_fabrikant44_enabled=False),
            None, MonitoringRepository(tmp_path / "seen.sqlite"), None,
        )
        matches, report = asyncio.run(monitor.fetch_matches_from_catalog_for_profile(
            regional_sql, profile, source_keys=(EIS,), max_items=100,
        ))
        assert not report.failures and len(matches) == 1
        assert matches[0].notice.tender_number == full[-1].tender_number
    finally:
        db.close()


def test_russian_minus_tsiya_keyword_inflections_match_without_unrelated_matches():
    """Common requested inflections must not silently drop genuine RU tenders."""
    from app.monitoring.service import _term_match
    assert _term_match("Канализация в Ингушетии", "канализации")
    assert _term_match("Строительство канализации", "канализация")
    assert _term_match("Ремонт станции", "станция")
    assert not _term_match("Поставка бетона", "канализации")
    assert not _term_match("Новая линия", "канализации")


def test_worker_sql_keyword_search_does_not_confuse_russian_substrings(tmp_path):
    """A short tenant term must not match the prefix of an unrelated word."""
    db = Database(DatabaseSettings("ing-strict-keyword", tmp_path / "keywords.sqlite"))
    repo = OpportunityRepository(db)
    repo.initialize()
    try:
        repo.upsert(
            notice(N1, title="Поставка оборудования Газпром"),
            connector_version(EIS),
        )
        repo.upsert(
            notice(N2, title="Поставка газа для котельной"),
            connector_version(EIS),
        )
        catalog = fresh_ingushetia_worker_catalog(
            build_source_catalog(settings(ru_ingushetia_fabrikant44_enabled=False)),
            repo,
        )
        source = catalog.registry.get(EIS).source
        gas = asyncio.run(source.for_search_terms(("газ",)).fetch(limit=3))
        assert gas == []  # No complete token "газ"; "газа" is another form.
        unrelated = asyncio.run(source.for_search_terms(("Газпром",)).fetch(limit=3))
        assert [n.tender_number for n in unrelated] == [N1]
        relevant = asyncio.run(source.for_search_terms(("газа",)).fetch(limit=3))
        assert [n.tender_number for n in relevant] == [N2]
    finally:
        db.close()
