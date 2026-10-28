"""Never promote unverified Fabrikant published-list HTML to a live source."""
import asyncio
from contextlib import asynccontextmanager

from app.sources.http import ConnectorTransportError
from scripts import research_ru_fabrikant_published_regional_routes as s


def test_only_canonical_firstparty_19_digit_original_links_qualify():
    html=(
        "<a href='/44/procedure/ea21/0194200000526005756'>official</a>"
        "<a href='https://soap4.fabrikant.ru/44/procedure/ea21/0114500000826002518"
        "?backurl=YWJj'>official</a>"
        "<a href='//evil.invalid/44/procedure/ea21/0194200000526005775'>evil</a>"
        "<a href='https://bad.invalid/44/procedure/ea21/0194200000526005775'>evil</a>"
        "<a href='/44/procedure/ea21/111'>bad</a>"
        "<a href='/44/procedure/ea21/0194200000526005756?token=oops'>secret</a>"
    ).encode("utf8")
    assert s.official_list_ids(html,"44.fabrikant.ru")=={
        "0194200000526005756","0114500000826002518"}


def test_real_paths_are_fixed_exact_hosts_and_regional_organizers(monkeypatch,capsys):
    requested=[]
    class R:
        headers={"content-type":"text/html"}
        content=b"<a href='/44/procedure/ea21/0194200000526005756'>original</a>"
        def raise_for_status(self):pass
    class Client:
        async def get(self,url):
            requested.append(url)
            return R()
    @asynccontextmanager
    async def client(**kw):
        assert kw["trust_env"] is False
        assert kw["follow_redirects"] is False
        yield Client()
    monkeypatch.setattr(s,"source_client",client)
    rows=asyncio.run(s.inspect())
    assert len(rows)==4 and len(requested)==4
    assert all(r["canonical_original_ids"]==1 for r in rows)
    assert all(r["publisher_host"] in s.HOSTS for r in rows)
    assert all(r["category"]=="published_html_with_anchors" for r in rows)
    assert s.main()==0
    out=capsys.readouterr().out
    assert "INDIVIDUAL_LIVE_DETAIL_AND_WORKER=NOT_VERIFIED" in out
    assert "REGIONAL_SOURCES_ACTIVATED=NO" in out


def test_official_publisher_http_failure_stays_blocked(monkeypatch):
    class Client:
        async def get(self,url):
            raise ConnectorTransportError(reason="http_status")
    @asynccontextmanager
    async def client(**kw):
        yield Client()
    monkeypatch.setattr(s,"source_client",client)
    assert [x["category"] for x in asyncio.run(s.inspect())]==["http_status"]*4
