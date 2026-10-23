"""Manual /tenders opt-in Ingushetia Worker-SQL depth; offline real DB tests.

These tests do not reach Russian publishers or the Telegram Bot API.
"""
import asyncio
from types import SimpleNamespace

from app.bot.monitoring import tenders_handler
from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.monitoring.config import MonitoringSettings
from app.monitoring.repository import MonitoringRepository
from app.monitoring.service import TenderMonitorService, MonitorMatch
from app.scoring.models import CompanyProfile
from app.sources.catalog import build_source_catalog
from app.sources.ingestion import connector_version
from app.sources.models import TenderNotice
from app.sources.opportunities import OpportunityRepository
from app.sources.snapshots import fresh_ingushetia_worker_catalog


EIS = "ru_ingushetia_eis44"


def notice(number, title):
    return TenderNotice(
        source=EIS, external_id=number, tender_number=number,
        url="https://zakupki.gov.ru/epz/order/notice/ea20/view/common-info.html?regNumber=" + number,
        title=title,
        customer="Министерство здравоохранения Республики Ингушетия",
        region="Республика Ингушетия",
    )


class Message:
    from_user = SimpleNamespace(id=101)
    chat = SimpleNamespace(id=5001)

    def __init__(self):
        self.sent = []
        self.edited = []

    async def answer(self, text, **kwargs):
        self.sent.append(text)
        return SimpleNamespace(
            message_id=len(self.sent),
            chat=SimpleNamespace(id=self.chat.id),
            edit_text=self.edit_text,
        )

    async def edit_text(self, text):
        self.edited.append(text)


def test_manual_tenders_reaches_late_matching_ingushetia_original_via_sql(tmp_path):
    """The 26th matching original must survive max_items=3 and be claimed only on ACK."""
    cfg = MonitoringSettings(
        enabled=True, interval_seconds=600, max_items=3,
        max_notifications_per_cycle=2, request_timeout=20,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
        ru_background_catalog_enabled=True,
        ru_ingushetia_worker_sql_alerts_enabled=True,
        ru_ingushetia_eis44_enabled=True,
    )
    db = Database(DatabaseSettings("ing-manual-deep", tmp_path / "workers.sqlite"))
    store = OpportunityRepository(db)
    store.initialize()
    seen = MonitoringRepository(tmp_path / "seen.sqlite")
    seen.initialize()
    selected = "0114500000826002599"
    profile = CompanyProfile(
        profile_version="1", company_name="Road drainage",
        search_keywords=["канализации"],
        allowed_regions=["Ингушетия"],
    )
    service = TenderMonitorService(
        cfg, None, seen, None,
        profile_resolver=lambda uid: profile if uid == 101 else None,
    )
    try:
        store.upsert(notice(selected, "Устройство ливневой канализации"), connector_version(EIS))
        for i in range(25):
            number = str(114500000826002500 + i).zfill(19)
            store.upsert(notice(number, "Поставка канцелярских товаров"), connector_version(EIS))
        assert selected not in {row.tender_number for row in store.read(EIS, limit=3)}
        catalog = fresh_ingushetia_worker_catalog(build_source_catalog(cfg), store)
        msg = Message()
        asyncio.run(tenders_handler(msg, monitoring_service=service, source_catalog=catalog))
        sent = [body for body in msg.sent if selected in body]
        assert len(sent) == 1
        assert "Номер: " + selected in sent[0]
        assert seen.seen(101, "eis_44", selected)
        assert any("Найдено новых подходящих закупок: 1" in status for status in msg.edited)
        again = Message()
        asyncio.run(tenders_handler(again, monitoring_service=service, source_catalog=catalog))
        assert not any(selected in body for body in again.sent)
        assert "Новых подходящих закупок" in again.edited[0]
    finally:
        db.close()


def test_manual_regional_pool_does_not_starve_other_enabled_sources():
    """Two opt-in source groups are interleaved before per-cycle send cap."""
    from app.bot.monitoring import _manual_regional_worker_sql_search

    class Catalog:
        class Registry:
            def metadata(self):
                return (
                    SimpleNamespace(key=EIS, enabled=True),
                    SimpleNamespace(key="kavkaz_rf_firstparty", enabled=True),
                )

            def get(self, key):
                from app.sources.snapshots import FreshIngushetiaWorkerSource
                assert key == EIS
                return SimpleNamespace(
                    source=FreshIngushetiaWorkerSource(object(), key),
                )
        registry = Registry()

    class Service:
        def __init__(self):
            self.calls = []

        async def profile_for_owner(self, uid):
            assert uid == 101
            return "profile"

        async def fetch_matches_from_catalog_for_profile(
                self, cat, profile, *, source_keys, max_items=None):
            assert cat is catalog and profile == "profile"
            self.calls.append((source_keys, max_items))
            matches = [MonitorMatch(
                notice("011450000082600" + str(2400 + i).zfill(4), "Поставка товара"),
                (),
            ) for i in range(5)] if source_keys == (EIS,) else [
                MonitorMatch(TenderNotice(
                    source="kavkaz_rf_firstparty", external_id="a",
                    url="https://xn--80aafvlc.xn--p1ai/purchases_sales/",
                    title="Кавказ.РФ подряд",
                ), ())]
            report = SimpleNamespace(
                attempted_sources=source_keys, successful_sources=source_keys,
                failures=(),
            )
            return matches, report

    catalog = Catalog()
    service = Service()
    matches, report = asyncio.run(_manual_regional_worker_sql_search(service, catalog, 101))
    assert service.calls == [((EIS,), 1000), (("kavkaz_rf_firstparty",), None)]
    assert [m.notice.source for m in matches[:3]] == [
        EIS, "kavkaz_rf_firstparty", EIS,
    ]
    assert len(matches) == 6
    assert report.attempted_sources == (EIS, "kavkaz_rf_firstparty")
    assert not report.total_failure


def test_manual_worker_sql_mode_rejects_unwrapped_live_catalog_without_fetching():
    """Do not silently fetch live EIS/ETP per chat when fixed Worker SQL is mandated."""
    import pytest
    from app.sources.eis_rss import SourceError
    from app.bot.monitoring import _manual_regional_worker_sql_search

    class Catalog:
        class Registry:
            def metadata(self):
                return (SimpleNamespace(key=EIS, enabled=True),)

            def get(self, key):
                assert key == EIS
                return SimpleNamespace(source=object())  # accidental live adapter
        registry = Registry()

    class Service:
        async def profile_for_owner(self, uid):
            pytest.fail("No profile or network access permitted")
        async def fetch_matches_from_catalog_for_profile(self, *args, **kwargs):
            pytest.fail("Unverified catalog must never be used")

    with pytest.raises(SourceError, match="Worker-SQL catalog"):
        asyncio.run(_manual_regional_worker_sql_search(Service(), Catalog(), 101))
