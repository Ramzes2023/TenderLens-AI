"""Main-first Ingushetia source integration: offline contract; NOT live acceptance."""
import asyncio
from dataclasses import replace
import pytest
from app.monitoring.config import MonitoringSettings
from app.sources.catalog import build_source_catalog
from app.sources.ingestion import HOSTS
from app.sources.ru_notice_identity import original_notice_key
from app.sources.ru_ingushetia_eis44 import normalize_ingushetia_notice, RSS_URL
from app.sources.ru_ingushetia_fabrikant44 import IngushetiaFabrikant44Source
from app.sources.models import TenderNotice
from app.sources.ru_cycle import approved_ru_keys

N = "0114500000826002402"
def cfg(**changes):
    return replace(MonitoringSettings(False, 600, 20, 5, 25, (), None), **changes)

def test_default_off_on_main_keeps_all_previous_ru_sources():
    cat = build_source_catalog(cfg())
    assert "ru_ingushetia_eis44" not in cat.enabled_keys
    assert "ru_ingushetia_fabrikant44" not in cat.enabled_keys
    assert {"ru_samara_public_list", "ru_dagestan_public_list"} <= set(HOSTS)
    with pytest.raises(ValueError, match="No operator-approved"):
        approved_ru_keys(cat)

def test_explicit_enabled_sources_keep_publisher_provenance_and_operator_queue():
    cat = build_source_catalog(cfg(ru_ingushetia_eis44_enabled=True,
                                  ru_ingushetia_fabrikant44_enabled=True))
    assert {"ru_ingushetia_eis44", "ru_ingushetia_fabrikant44"} <= set(cat.enabled_keys)
    assert approved_ru_keys(cat) == ("ru_ingushetia_eis44", "ru_ingushetia_fabrikant44")
    assert HOSTS["ru_ingushetia_eis44"] == frozenset({"zakupki.gov.ru"})
    assert HOSTS["ru_ingushetia_fabrikant44"] == frozenset({"44.fabrikant.ru", "soap4.fabrikant.ru"})
    assert "Ингушетия" in cat.registry.get("ru_ingushetia_eis44").display_name

def test_eis_buyer_region_and_cross_mirror_original_identity():
    official = TenderNotice(
        source="ru_ingushetia_eis44", external_id=N, tender_number=N,
        title="Устройство ливневой канализации", customer="Комитет Республики Ингушетия",
        url="https://zakupki.gov.ru/epz/order/notice/ok20/view/common-info.html?regNumber="+N)
    regional = normalize_ingushetia_notice(official)
    assert regional is not None and regional.region == "Республика Ингушетия"
    mirror = replace(regional, source="ru_ingushetia_fabrikant44",
        url="https://44.fabrikant.ru/44/procedure/okb20/"+N)
    assert original_notice_key(regional) == original_notice_key(mirror) == ("eis_44", N)
    assert normalize_ingushetia_notice(replace(official,customer="Другой регион")) is None

def test_operator_cannot_fetch_invalid_placement_or_untrusted_url():
    from app.sources.ru_ingushetia_eis44 import validate_ingushetia_rss_url
    with pytest.raises(ValueError):
        validate_ingushetia_rss_url("https://evil.example/?fz44=on")
    with pytest.raises(ValueError):
        asyncio.run(IngushetiaFabrikant44Source().fetch(limit=0))
    assert RSS_URL.startswith("https://zakupki.gov.ru/")
