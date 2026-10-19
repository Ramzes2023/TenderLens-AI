"""Offline contract checks only; these do NOT certify live EIS delivery."""
import asyncio
from dataclasses import replace

import pytest

from app.monitoring.config import MonitoringSettings, MonitoringConfigurationError, load_monitoring_settings
from app.sources.catalog import build_source_catalog
from app.sources.eis_rss import EisRssSource, SourceError
from app.sources.ingestion import HOSTS
from app.sources.models import TenderNotice
from app.sources.ru_dedup import deduplicate
from app.sources.ru_ingushetia_eis44 import (
    SOURCE_ID, REGION, RSS_URL, IngushetiaEis44Source, normalize_ingushetia_notice,
)
from app.sources.ru_notice_identity import original_notice_key

N = "0114500000826002364"
U = "https://zakupki.gov.ru/epz/order/notice/ea20/view/common-info.html?regNumber=" + N


def sample(**overrides):
    fields = dict(source=SOURCE_ID, external_id="EIS-GUID-" + N,
                  tender_number=N, url=U, title="Поставка медицинских товаров",
                  customer="Комитет государственного заказа Республики Ингушетия",
                  region=None, published_at="2026-10-16")
    fields.update(overrides)
    return TenderNotice(**fields)


def settings(**kw):
    fields = dict(enabled=False, interval_seconds=600, max_items=10,
                  max_notifications_per_cycle=3, request_timeout=20,
                  eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False)
    fields.update(kw)
    return MonitoringSettings(**fields)


def test_region_requires_original_metadata_not_title_or_untrusted_query():
    n = normalize_ingushetia_notice(sample())
    assert n.region == REGION
    assert n.external_id == n.tender_number == N
    assert n.enrichment is None
    assert normalize_ingushetia_notice(sample(
        customer="Больница постороннего региона", region=None,
        title="Доставка в Республику Ингушетия")) is None
    assert normalize_ingushetia_notice(sample(
        customer="Муниципальное учреждение", region="Ингушетия республика")) is not None


@pytest.mark.parametrize("patch", [
    {"tender_number": None},
    {"tender_number": "12345"},
    {"url": U.replace("zakupki.gov.ru", "zakupki.gov.ru.attacker.example")},
    {"url": U.replace("https:", "http:")},
    {"url": U.replace("regNumber=", "regNumber=123&other=")},
    {"url": U + "&token=test"},
    {"url": U.replace("/epz/order/notice/", "/223/purchase/public/purchase/")},
    {"source": "eis"},
])
def test_unsafe_original_provenance_fails_closed(patch):
    with pytest.raises(SourceError):
        normalize_ingushetia_notice(sample(**patch))


def test_no_duplicate_eis_notifications_for_same_original():
    regional = normalize_ingushetia_notice(sample())
    ordinary = replace(regional, source="eis", external_id="different-eis-guid")
    assert original_notice_key(regional) == ("eis_44", N)
    assert original_notice_key(ordinary) == ("eis_44", N)
    unique, duplicates = deduplicate([ordinary, regional])
    assert len(unique) == 1 and unique[0].source == "eis"
    assert len(duplicates) == 1


def test_source_stays_off_by_default_and_uses_one_official_host():
    assert "regions=06" in RSS_URL and RSS_URL.startswith("https://zakupki.gov.ru/")
    assert HOSTS[SOURCE_ID] == frozenset({"zakupki.gov.ru"})
    assert SOURCE_ID not in build_source_catalog(settings()).registry.keys()
    catalog = build_source_catalog(settings(ru_ingushetia_eis44_enabled=True))
    assert SOURCE_ID in catalog.enabled_keys
    entry = catalog.registry.get(SOURCE_ID)
    assert isinstance(entry.source, IngushetiaEis44Source)
    assert entry.homepage_url == RSS_URL and entry.official
    assert entry.jurisdictions == ("RU",)


def test_environment_explicit_opt_in_and_invalid_value(monkeypatch, tmp_path):
    f = tmp_path / "not-present.env"
    monkeypatch.delenv("RU_INGUSHETIA_EIS44_ENABLED", raising=False)
    assert load_monitoring_settings(f).ru_ingushetia_eis44_enabled is False
    monkeypatch.setenv("RU_INGUSHETIA_EIS44_ENABLED", "true")
    assert load_monitoring_settings(f).ru_ingushetia_eis44_enabled is True
    monkeypatch.setenv("RU_INGUSHETIA_EIS44_ENABLED", "invalid")
    with pytest.raises(MonitoringConfigurationError):
        load_monitoring_settings(f)


def test_live_adapter_shape_with_mocked_upstream_never_counts_as_live(monkeypatch):
    async def synthetic(self, limit=20):
        assert limit == 100
        assert self.name == SOURCE_ID and self.direct is True
        assert self.urls == (RSS_URL,)
        return [
            sample(title="Поставка тестового оборудования"),
            sample(customer="Чужой регион", title="Ингушетия оборудование", region=None,
                   tender_number="0114500000826002365",
                   url=U.replace(N, "0114500000826002365")),
            sample(),
        ]

    monkeypatch.setattr(EisRssSource, "fetch", synthetic)
    notices = asyncio.run(IngushetiaEis44Source().fetch(limit=2))
    assert len(notices) == 1 and notices[0].external_id == N
    with pytest.raises(ValueError):
        asyncio.run(IngushetiaEis44Source().fetch(limit=0))
