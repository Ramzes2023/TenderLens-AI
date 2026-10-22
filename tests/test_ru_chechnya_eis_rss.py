"""Chechnya EIS adapter contracts. All inputs are synthetic; no live claim."""
from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from app.monitoring.config import (
    MonitoringConfigurationError,
    MonitoringSettings,
    load_monitoring_settings,
)
from app.sources.catalog import build_source_catalog
from app.sources.eis_rss import EisRssSource, SourceError, parse_eis_feed, verify_eis_feed_law
from app.sources.ingestion import HOSTS, connector_version, validate_payload
from app.sources.models import TenderNotice
from app.sources.ru_dedup import deduplicate
from app.sources.ru_notice_identity import original_notice_key
from app.sources.ru_chechnya_eis_rss import (
    SOURCE_KEY,
    ChechnyaEisRssSource,
    is_chechnya_notice,
    validate_chechnya_feed_urls,
)

URL = (
    "https://zakupki.gov.ru/epz/order/extendedsearch/rss.html"
    "?fz44=on&searchString=%D0%A7%D0%B5%D1%87%D0%B5%D0%BD%D1%81%D0%BA%D0%B0%D1%8F%20%D0%A0%D0%B5%D1%81%D0%BF%D1%83%D0%B1%D0%BB%D0%B8%D0%BA%D0%B0"
)
EIS_ORIGINAL = (
    "https://zakupki.gov.ru/epz/order/notice/ea20/view/common-info.html"
    "?regNumber=0194200000526005027"
)


def settings():
    return MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=20,
        max_notifications_per_cycle=5, request_timeout=20,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
    )


def notice(n, *, customer=None, region=None, title="Поставка продуктов питания"):
    return TenderNotice(
        source=SOURCE_KEY, external_id=str(n), title=title,
        url=EIS_ORIGINAL.replace("0194200000526005027", str(n)),
        tender_number=str(n), customer=customer, region=region,
    )


def test_adapter_disabled_by_default_and_worker_host_allowlisted():
    catalog = build_source_catalog(settings())
    assert SOURCE_KEY not in catalog.enabled_keys
    assert SOURCE_KEY not in {m.key for m in catalog.registry.metadata()}
    assert HOSTS[SOURCE_KEY] == frozenset({"zakupki.gov.ru"})


def test_operator_only_enable_registers_adapter_and_worker_routing():
    cfg = replace(settings(), ru_chechnya_eis_enabled=True,
                  ru_chechnya_eis_rss_urls=(URL,))
    catalog = build_source_catalog(cfg)
    assert SOURCE_KEY in catalog.enabled_keys
    entry = catalog.registry.get(SOURCE_KEY)
    assert isinstance(entry.source, ChechnyaEisRssSource)
    assert entry.official and entry.jurisdictions == ("RU",)
    payload = {
        "schema": 1, "source_id": SOURCE_KEY,
        "sync_window": "2026-10-22T11Z",
        "connector_version": connector_version(SOURCE_KEY),
    }
    assert validate_payload(payload, catalog.registry) is entry


@pytest.mark.parametrize("url", [
    "http://zakupki.gov.ru/epz/order/extendedsearch/rss.html?fz44=on&searchString=Чеченская",
    "https://evil.example/epz/order/extendedsearch/rss.html?fz44=on&searchString=Чеченская",
    "https://zakupki.gov.ru/epz/order/extendedsearch/rss.html?fz223=on&searchString=Чеченская",
    "https://zakupki.gov.ru/epz/order/extendedsearch/rss.html?fz44=on",
    "https://zakupki.gov.ru/epz/order/extendedsearch/rss.html?fz44=on&searchString=Москва",
])
def test_refuse_insecure_ambiguous_or_nationwide_feed(url):
    with pytest.raises((SourceError, ValueError)):
        validate_chechnya_feed_urls((url,))


def test_regional_evidence_from_customer_or_delivery_not_title_or_summary():
    assert is_chechnya_notice(notice("0194200000526005027",
                                    customer="Комитет правительства Чеченской Республики"))
    assert is_chechnya_notice(notice("0194200000526005028", region="г. Грозный"))
    assert not is_chechnya_notice(notice("0194200000526005029",
                                        customer="Министерство Московской области",
                                        region="Московская область",
                                        title="Доставка в Чеченскую Республику"))


def test_only_verified_region_procedures_leave_adapter(monkeypatch):
    async def synthetic_upstream(self, limit=20):
        assert self.name == SOURCE_KEY and limit == 100
        return [
            notice("0194200000526005027",
                   customer="Комитет правительства Чеченской Республики"),
            notice("0194200000526005027",
                   customer="Комитет правительства Чеченской Республики"),
            notice("0194200000526005028", region="Грозный"),
            notice("0194200000526005029", region="Москва"),
            notice("0194200000526005030", title="Объект в Чеченской Республике"),
            replace(notice("0194200000526005031", region="г. Грозный"), tender_number=None),
        ]
    monkeypatch.setattr(EisRssSource, "fetch", synthetic_upstream)
    result = asyncio.run(ChechnyaEisRssSource((URL,)).fetch(limit=5))
    assert [n.external_id for n in result] == [
        "0194200000526005027", "0194200000526005028"
    ]
    assert all(n.source == SOURCE_KEY for n in result)


def test_rejects_procedure_number_that_does_not_match_original_eis_card(monkeypatch):
    async def synthetic_upstream(self, limit=20):
        return [
            replace(notice("0194200000526005027", region="Чеченская Республика"),
                    tender_number="0194200000526005028"),
            replace(notice("0194200000526005027", region="Чеченская Республика"),
                    url="https://evil.example/epz/order/notice/ea20/view/common-info.html?regNumber=0194200000526005027"),
            notice("0194200000526005029", region="Чеченская Республика"),
        ]
    monkeypatch.setattr(EisRssSource, "fetch", synthetic_upstream)
    rows = asyncio.run(ChechnyaEisRssSource((URL,)).fetch(limit=3))
    assert [row.tender_number for row in rows] == ["0194200000526005029"]


def test_eis_44_original_law_is_checked_before_regional_normalization():
    sample = (
        '<rss version="2.0"><channel><item>'
        '<title>Поставка продуктов</title>'
        '<guid>0194200000526005027</guid>'
        '<link>' + EIS_ORIGINAL.replace("&", "&amp;") + '</link>'
        '<description>Размещение выполняется по: 44-ФЗ. '
        'Регион: Чеченская Республика; '
        'Заказчик: Комитет Правительства Чеченской Республики</description>'
        '</item></channel></rss>'
    ).encode("utf-8")
    verify_eis_feed_law(sample, "44-FZ")
    items = parse_eis_feed(sample, source_name=SOURCE_KEY)
    assert len(items) == 1 and items[0].tender_number == "0194200000526005027"
    assert is_chechnya_notice(items[0])


def test_enabled_without_operator_url_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("RU_CHECHNYA_EIS_ENABLED", "true")
    monkeypatch.delenv("RU_CHECHNYA_EIS_RSS_URLS", raising=False)
    with pytest.raises(MonitoringConfigurationError):
        load_monitoring_settings(tmp_path / "does-not-exist.env")


def test_disabled_configuration_does_not_auto_register(monkeypatch, tmp_path):
    monkeypatch.setenv("RU_CHECHNYA_EIS_ENABLED", "false")
    monkeypatch.setenv("RU_CHECHNYA_EIS_RSS_URLS", URL)
    cfg = load_monitoring_settings(tmp_path / "does-not-exist.env")
    assert not cfg.ru_chechnya_eis_enabled
    assert SOURCE_KEY not in build_source_catalog(cfg).enabled_keys


def test_same_eis_original_is_never_counted_twice_across_national_and_regional_feeds():
    from dataclasses import replace
    regional = notice('0194200000526005027', region='Чеченская Республика')
    national = replace(regional, source='eis')
    assert original_notice_key(regional) == original_notice_key(national)
    unique, duplicates = deduplicate([regional, national])
    assert len(unique) == 1 and unique[0].source == 'eis'
    assert len(duplicates) == 1


def test_live_local_alert_sink_returns_required_synthetic_receipt_only():
    """Offline: local capture ACK unblocks marking after successful send.

    Never treats a local-only test stub as Telegram API delivery.
    """
    from scripts.ci_ru_chechnya_eis_real_worker import LocalCaptureBot

    async def run():
        stop = asyncio.Event()
        bot = LocalCaptureBot(stop)
        text = "🆕 НОВАЯ ЗАКУПКА\\nИсточник: " + SOURCE_KEY
        receipt = await bot.send_message(
            99102, text, disable_web_page_preview=True,
        )
        # The shared monitor ACK gate lives in a separate unmerged PR;
        # this source-specific test only checks local receipt shape.
        assert type(receipt.message_id) is int and receipt.message_id > 0
        assert type(receipt.chat.id) is int and receipt.chat.id == 99102
        assert receipt.message_id == 1
        assert receipt.chat.id == 99102
        assert stop.is_set() and bot.messages == [text]
        with pytest.raises(AssertionError):
            await bot.send_message(12345, text, disable_web_page_preview=True)
        with pytest.raises(AssertionError):
            await bot.send_message(99102, "unverified source",
                                   disable_web_page_preview=True)
        assert len(bot.messages) == 1

    asyncio.run(run())


def test_user_notification_catalog_reads_real_worker_snapshot_not_second_rss(monkeypatch):
    """Offline boundary: monitoring must consume the persisted Worker identity."""
    from app.bot.monitoring import enabled_ru_catalog_keys
    from app.sources.snapshots import snapshot_catalog

    stored = notice(
        "0194200000526005027",
        customer="Комитет Правительства Чеченской Республики",
    )
    class IsolatedStore:
        def __init__(self):
            self.read_count = 0

        def read(self, source, limit, terms):
            assert source == SOURCE_KEY and limit == 5
            self.read_count += 1
            return [stored]

    async def forbidden_second_network_fetch(self, limit=20):
        raise AssertionError("No fresh EIS fetch after leased Worker persisted original")

    monkeypatch.setattr(ChechnyaEisRssSource, "fetch", forbidden_second_network_fetch)
    catalog = build_source_catalog(
        replace(settings(), ru_chechnya_eis_enabled=True,
                ru_chechnya_eis_rss_urls=(URL,))
    )
    store = IsolatedStore()
    persisted = snapshot_catalog(catalog, store)
    assert enabled_ru_catalog_keys(persisted) == (SOURCE_KEY,)
    rows = asyncio.run(persisted.registry.get(SOURCE_KEY).source.fetch(limit=5))
    assert rows == [stored] and store.read_count == 1
