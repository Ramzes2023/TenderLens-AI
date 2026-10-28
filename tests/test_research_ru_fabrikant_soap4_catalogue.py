"""Official Fabrikant discovery requires publisher-owned linked IDs."""
import asyncio
from contextlib import asynccontextmanager
from app.sources.http import ConnectorTransportError
from scripts import research_ru_fabrikant_soap4_catalogue as s


def test_only_official_real_anchor_ids_count_as_publisher_discovery():
    html=(
        "<html><a href='/44/procedure/ea21/0114500000826002518'>Ingush</a>"
        "<a href='https://soap4.fabrikant.ru/44/procedure/ea21/0194200000526005756"
        "?backurl=LzQ0'>Chechen</a>"
        "<a href='https://evil.invalid/44/procedure/ea21/0194200000526005775'>Malicious</a>"
        "<a href='//evil.invalid/44/procedure/ea21/0194200000526005775'>Evil</a>"
        "<a href='/44/procedure/ea21/0114500000826002518?token=private'>Secret</a>"
        "<a href='/44/procedure/ea21/111'>Bad ID</a>"
        "</html>"
    ).encode("utf8")
    assert s.catalogue_ids(html)=={
        "0114500000826002518","0194200000526005756"}


def test_source_owned_catalogue_is_not_detail_or_working_source(monkeypatch,capsys):
    class Reply:
        headers={"content-type":"text/html"}
        content=b"<a href='/44/procedure/ea21/0194200000526005775'>Original</a>"
        def raise_for_status(self): pass
    class Client:
        async def get(self,url):
            assert url in ["https://"+s.HOST+p for p in s.PATHS]
            return Reply()
    @asynccontextmanager
    async def factory(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        yield Client()
    monkeypatch.setattr(s,"source_client",factory)
    out=asyncio.run(s.inspect())
    assert len(out)==2
    assert all(v["sample_current_originals_discovered"]==1 for v in out)
    assert s.main()==0
    output=capsys.readouterr().out
    assert "REGIONAL_CURRENT_DISCOVERY_AND_WORKER=NOT_PROVED" in output
    assert "SOURCES_ACTIVATED=NO" in output


def test_official_public_index_rejection_is_not_hidden(monkeypatch):
    class Client:
        async def get(self,url):
            raise ConnectorTransportError(reason="http_status")
    @asynccontextmanager
    async def factory(**kwargs):
        yield Client()
    monkeypatch.setattr(s,"source_client",factory)
    out=asyncio.run(s.inspect())
    assert len(out)==2 and all(x["category"]=="http_status" for x in out)
