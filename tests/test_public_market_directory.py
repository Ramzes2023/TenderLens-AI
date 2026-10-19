"""Honest dynamic source directory and differentiated public marketing."""
import pytest
from fastapi.testclient import TestClient
from app.api.main import create_app
from app.api.runtime import ApiRuntime
from app.api.public_sources import source_directory
from app.sources.registry import SourceRegistry, SourceRegistration, SourceTransport, SourceCapabilities

EXPECTED_OPTIONAL_KEYS = {
    "ru_ingushetia_eis44", "ru_ingushetia_fabrikant44", "eis_223", "b2b_center",
    "mikroton_tender", "tektorg", "eis_44_html", "lenobl_small_public",
    "stan_commercial_public", "nmck_native_public", "gpb_etp_public",
}


class Dummy:
    def __init__(self,name): self.name=name
    async def fetch(self,limit=20): return []


class Catalog:
    def __init__(self):
        self.registry=SourceRegistry((
            SourceRegistration(key="ru_small",display_name="Regional small purchases",source=Dummy("ru_small"),
                jurisdictions=("RU",),enabled=False,homepage_url="https://example.org/",transport=SourceTransport.HTML),
            SourceRegistration(key="ted",display_name="Tenders Electronic Daily",source=Dummy("ted"),
                jurisdictions=("EU",),enabled=True,homepage_url="https://ted.europa.eu/",
                transport=SourceTransport.API,capabilities=SourceCapabilities()),
        ))


def test_source_directory_is_scoped_to_actual_registry_not_live_health():
    result=source_directory(Catalog())
    assert result["source_count"]==2 and result["enabled_count"]==1
    assert result["live_health_verified"] is False
    assert result["sources"][0]["key"]=="ru_small"
    assert result["sources"][0]["focus"]=="regional_small"
    assert result["sources"][0]["live_status"]=="not_verified"
    assert result["sources"][0]["enabled"] is False
    assert result["sources"][1]["enabled"] is True
    assert result["sources"][1]["homepage"]=="https://ted.europa.eu/"
    # Opt-in adapters are discoverable, but are not counted as registered.
    assert result["optional_count"] == len(EXPECTED_OPTIONAL_KEYS)
    assert result["candidate_count"] == 38
    keys = {item["key"] for item in result["optional_sources"]}
    assert keys == EXPECTED_OPTIONAL_KEYS
    assert all(item["registered"] is False and item["enabled"] is False
               and item["live_status"] == "not_verified"
               for item in result["optional_sources"])


def test_directory_has_no_fabricated_sources_if_runtime_has_none():
    with TestClient(create_app(runtime=ApiRuntime())) as client:
        response=client.get("/public/source-directory.json")
        assert response.status_code==200
        assert response.json()["source_count"]==0
        assert response.json()["sources"]==[]
        assert response.json()["optional_sources"]==[]
        assert response.headers["cache-control"]=="no-store"
        html=client.get("/").text
        assert 'id="sourceDirectory"' in html
        assert "/assets/market_directory.js" in html
        assert "Better visibility into the market." in html
        assert "Billing is not enabled" in html
        assert "100 verified" not in html
        assert "competitors do not" not in html

@pytest.mark.parametrize('key', ['lenobl_small_public', 'ru_ingushetia_eis44', 'ru_ingushetia_fabrikant44'])
def test_ru_optional_adapter_not_duplicated_when_registered(key):
    catalog = Catalog()
    catalog.registry.register(SourceRegistration(
        key=key,
        display_name="Leningrad Oblast official public small-purchase requests",
        source=Dummy(key),
        jurisdictions=("RU",), enabled=True,
        homepage_url="https://zakupki.lenreg.ru/Search/NewRequests",
        transport=SourceTransport.HTML,
    ))
    result = source_directory(catalog)
    assert result["source_count"] == 3
    assert result["optional_count"] == len(EXPECTED_OPTIONAL_KEYS) - 1
    assert {item["key"] for item in result["optional_sources"]} == EXPECTED_OPTIONAL_KEYS - {key}
    assert result["candidate_count"] == 38
    assert sum(item["key"] == key for item in
               result["sources"] + result["optional_sources"]) == 1

def test_every_curated_ru_candidate_is_visible_but_never_enabled():
    from app.api.ru_source_inventory import RU_STAGED_ADAPTERS, RU_RESEARCH_TARGETS
    entries = source_directory(Catalog())
    candidates = entries["candidate_sources"]
    expected = {x[0] for x in RU_STAGED_ADAPTERS + RU_RESEARCH_TARGETS}
    assert len(expected) == 38
    assert {x["key"] for x in candidates} == expected
    assert len({x["key"] for x in candidates + entries["sources"] +
                entries["optional_sources"]}) == len(candidates) + entries["source_count"] + entries["optional_count"]
    assert all(not x["enabled"] and x["registered"] is False and
               x["live_status"] == "not_verified" for x in candidates)
    assert all(x["evidence_url"].startswith("https://github.com/Ramzes2023/TenderLens-AI/")
               for x in candidates)
    assert {x["inventory_status"] for x in candidates} == {"staged", "research"}


def test_ru_probe_targets_appear_in_directory_or_corresponding_parent_adapter():
    # All 37 approved probe targets are accounted for; parent adapters are
    # intentionally not multiplied into new live sources by their audit URLs.
    from scripts.ru_trusted_live_probe import TARGETS
    entries = source_directory(Catalog())
    keys = {x["key"] for group in ("sources", "optional_sources", "candidate_sources")
            for x in entries[group]}
    parent = {"b2b_office": "b2b_center", "fabrikant_44": "fabrikant_44_public",
              "roseltorg": "roseltorg_public", "lenobl": "lenobl_small_public",
              "vologda": "vologda_small", "gpb_rss": "gpb_rss_feed",
              "tektorg": "tektorg"}
    assert len(TARGETS) == 37
    assert {"ossetia_official_small", "stavropol_rts_small"} <= keys
    assert all(parent.get(label, label) in keys for label in TARGETS)
