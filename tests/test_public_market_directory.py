"""Honest dynamic source directory and differentiated public marketing."""
from fastapi.testclient import TestClient
from app.api.main import create_app
from app.api.runtime import ApiRuntime
from app.api.public_sources import source_directory
from app.sources.registry import SourceRegistry, SourceRegistration, SourceTransport, SourceCapabilities


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


def test_directory_has_no_fabricated_sources_if_runtime_has_none():
    with TestClient(create_app(runtime=ApiRuntime())) as client:
        response=client.get("/public/source-directory.json")
        assert response.status_code==200
        assert response.json()["source_count"]==0
        assert response.json()["sources"]==[]
        assert response.headers["cache-control"]=="no-store"
        html=client.get("/").text
        assert 'id="sourceDirectory"' in html
        assert "/assets/market_directory.js" in html
        assert "Better visibility into the market." in html
        assert "Billing is not enabled" in html
        assert "100 verified" not in html
        assert "competitors do not" not in html
