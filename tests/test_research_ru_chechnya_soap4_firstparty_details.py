"""Chechnya fresh Fabrikant originals are real only after original HTML GET."""
import asyncio
from contextlib import asynccontextmanager
from app.sources.http import ConnectorTransportError
from scripts import research_ru_chechnya_soap4_firstparty_details as source


def test_exact_official_chechnya_detail_markers_and_no_login():
    number,title=source.ORIGINALS[0]
    html=("<html><h1>"+number+"</h1><p>"+title+"</p>"
          "<p>Организатор закупки ИНН 2016014690</p>"
          "<p>Окончание подачи заявок 05.11.2026 09:00</p></html>").encode("utf8")
    assert all(source.original_markers(html,number,title).values())
    assert not source.original_markers(html.replace(number.encode(),b"0000000000000000000"),number,title)["id"]
    try:
        source.original_markers("необходимо авторизоваться".encode(),number,title)
        assert False,"Login page cannot be an original"
    except ValueError:
        pass


def test_two_strict_fabrikant_gets_or_blocked_without_false_release(monkeypatch,capsys):
    calls=[]
    class Response:
        headers={"content-type":"text/html"}
        def __init__(self,body):self.content=body
        def raise_for_status(self):pass
    class Client:
        async def get(self,url):
            calls.append(url)
            assert url.startswith("https://soap4.fabrikant.ru/44/procedure/ea21/")
            number,title=next((n,t) for n,t in source.ORIGINALS if url.endswith(n))
            return Response(("<html><h1>"+number+"</h1><p>"+title+"</p>"
                             "<p>ИНН 2016014690</p><p>05.11.2026</p></html>").encode())
    @asynccontextmanager
    async def factory(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        yield Client()
    monkeypatch.setattr(source,"source_client",factory)
    r=asyncio.run(source.check())
    assert len(calls)==2 and all(x["category"]=="verified_individual_original" for x in r)
    assert source.main()==0
    out=capsys.readouterr().out
    assert "RELEASE_READY=NO" in out
    assert "WORKER_SQL_AND_SEARCH=NOT_PROVED" in out


def test_source_network_refusal_cannot_be_masked(monkeypatch):
    class Client:
        async def get(self,url):
            raise ConnectorTransportError(reason="network")
    @asynccontextmanager
    async def factory(**kwargs):
        yield Client()
    monkeypatch.setattr(source,"source_client",factory)
    r=asyncio.run(source.check())
    assert len(r)==2 and all(x["category"]=="network" for x in r)
