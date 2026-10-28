"""Read-only official EIS probe may never mask a failed Worker as a success."""
import asyncio
from types import SimpleNamespace

import pytest

from app.sources.http import ConnectorTransportError
from app.sources.eis_rss import SourceError
from scripts import research_ru_ingushetia_eis_rss_failure as d


def test_strict_transport_failure_codes_have_no_raw_message():
    assert d.classify_exception(ConnectorTransportError(reason="network"))=="transport_network"
    assert d.classify_exception(ConnectorTransportError(reason="tls_certificate"))=="transport_tls_certificate"
    assert d.classify_exception(ConnectorTransportError(reason="unexpected"))=="transport_unclassified"
    assert d.classify_exception(SourceError("original buyer secret"))=="source_contract"
    assert d.classify_exception(TimeoutError("sensitive URL secret"))=="network_or_tls"


def test_zero_originals_do_not_claim_valid_current_source():
    class Empty:
        async def fetch(self,limit):
            assert limit==10
            return []
    result=asyncio.run(d.fetch_originals(Empty()))
    assert result["originals"]==0
    assert result["unique_original_numbers"]==0
    assert result["source"]=="ru_ingushetia_eis44"


def test_only_real_source_fetched_originals_can_be_counted():
    class Real:
        async def fetch(self,limit):
            return [
                SimpleNamespace(tender_number="0114500000826002518",
                                url="https://zakupki.gov.ru/epz/order/notice/ea20/view/common-info.html?regNumber=0114500000826002518")
            ]
    result=asyncio.run(d.fetch_originals(Real()))
    assert result["originals"]==1
    assert result["official_origin"]
    assert result["unique_original_numbers"]==1


def test_live_failure_is_never_claimed_as_delivery_or_deployment(monkeypatch,capsys):
    monkeypatch.setattr(d,"select_verified_eis_ca",lambda: "pinned-test-root")
    class Fail:
        def __init__(self,**kwargs):pass
    monkeypatch.setattr(d,"IngushetiaEis44Source",lambda **kwargs: Fail())
    async def fail(source):
        raise ConnectorTransportError(reason="network")
    monkeypatch.setattr(d,"fetch_originals",fail)
    assert d.main()==0
    out=capsys.readouterr().out
    assert "INGUSHETIA_EIS_DIAGNOSTIC=transport_network" in out
    assert "LEASED_WORKER_SQL_SEARCH=NOT_VERIFIED" in out
    assert "REGIONAL_SOURCE_ENABLED=NO" in out
