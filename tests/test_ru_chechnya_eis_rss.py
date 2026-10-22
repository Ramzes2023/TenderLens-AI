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
from app.sources.ru_chechnya_eis_rss import (
    SOURCE_KEY,
    ChechnyaEisRssSource,
    is_chechnya_notice,
    validate_chechnya_feed_urls,
)

URL = (
    "https://zakupki.gov.ru/epz/order/extendedsearch/rss.html"
    "?fz44=on&searchString=%D0%A7%D0%B5%D1%87%D0%B5%D0%BD%D1%81%D0%BA%D0%B0%D1%8F"
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
