"""Official Fabrikant host probe never substitutes secondary indexes for HTML."""
import asyncio
from contextlib import asynccontextmanager

from app.sources.http import ConnectorTransportError
from scripts import research_ru_fabrikant_soap4_original_host as s

HISTORICAL=(
    '<html><h1>Сведения о закупке 0372200119926000094</h1>'
    '<p>Поставка лекарственного препарата</p>'
    '<p>Дата окончания срока подачи заявок 04.09.2026</p></html>'
).encode("utf8")
CURRENT=(
    '<html><h1>Сведения о закупке 0114500000826002518</h1>'
    '<p>Поставка организационной техники</p>'
    '<p>Комитет государственного заказа Республики Ингушетия ИНН 0608058533</p>'
    '<p>Дата и время окончания срока подачи заявок 06.11.2026 09:00</p></html>'
).encode("utf8")


def test_only_actual_visible_original_fields_qualify_and_no_login_page():
    p=s.public_original_markers(CURRENT,current=True)
    assert p["eis_id_visible"] and p["organizer_inn_visible"]
    assert p["procurement_title_visible"] and p["independent_deadline_date_visible"]
    assert p["official_provenance"] is False
    q=s.public_original_markers(CURRENT.replace(b"2518",b"2519"),current=True)
    assert not q["eis_id_visible"]
    try:
        s.public_original_markers("Для просмотра необходимо авторизоваться".encode(),current=True)
        assert False,"login-only details must be refused"
    except ValueError:
        pass


def test_host_is_exact_and_url_hypothesis_never_claimed_without_live_get(monkeypatch):
    assert s.CURRENT_CANDIDATE.startswith("https://soap4.fabrikant.ru/44/procedure/ea21/")
    requested=[]
    class Response:
        headers={"content-type":"text/html"}
        def __init__(self,content): self.content=content
        def raise_for_status(self):pass
    class Client:
        async def get(self,url):
            requested.append(url)
            return Response(HISTORICAL if url==s.CONTROL else CURRENT)
    @asynccontextmanager
    async def client(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        yield Client()
    monkeypatch.setattr(s,"source_client",client)
    outcome=asyncio.run(s.inspect())
    assert len(requested)==2
    assert outcome[0]["category"]=="verified_individual_original"
    assert outcome[1]["category"]=="verified_individual_original"
    assert outcome[1]["verified_marker_count"]==5


def test_independently_blocked_original_is_not_counted(monkeypatch,capsys):
    class Client:
        async def get(self,url):
            raise ConnectorTransportError(reason="network")
    @asynccontextmanager
    async def client(**kwargs):
        yield Client()
    monkeypatch.setattr(s,"source_client",client)
    outcome=asyncio.run(s.inspect())
    assert len(outcome)==2
    assert all(x["category"]=="network" for x in outcome)
    assert s.main()==0
    text=capsys.readouterr().out
    assert "RELEASE_READY=NO" in text
    assert "SOURCE_LIST_DISCOVERY=NOT_PROVED" in text
    assert "WORKER_SQL_SEARCH=NOT_PROVED" in text
