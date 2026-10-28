"""Official Samara native detail research must stay fail-closed and read-only."""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

from app.sources.http import ConnectorTransportError
from scripts import research_ru_samara_firstparty_original_details as target


def prepare(monkeypatch, *, failure=None):
    rows=[
        {"link":"/smallpurchases/GzwSP/111111", "number":"ИМЗ-2026-0-223-002451",
         "name":"Поставка холодильников", "uchr_sname":"Больница Самарской области"},
        {"link":"/smallpurchases/GzwSP/222222", "number":"ИМЗ-2026-0-223-002452",
         "name":"Поставка фармацевтических холодильников", "uchr_sname":"Ветеринарная лаборатория"},
    ]
    notices=[
        SimpleNamespace(external_id=row["link"].rsplit("/",1)[-1],
                        tender_number=row["number"],title=row["name"],customer=row["uchr_sname"])
        for row in rows
    ]
    monkeypatch.setattr(target,"public_token",lambda body:"anonymous-public-token")
    monkeypatch.setattr(target,"parse_public_list",lambda body,limit: notices)
    log=[]

    class Response:
        def __init__(self,content,kind="text/html"):
            self.content=content
            self.headers={"content-type":kind}
        def raise_for_status(self):pass
        def json(self):return {"items":rows,"totalRows":2}

    class Client:
        async def get(self,url,*,headers=None):
            log.append(("GET",url))
            if url==target.GRID:
                return Response(b"<html>public registry</html>")
            assert url in ["https://"+target.HOST+row["link"] for row in rows]
            if failure=="details":
                raise ConnectorTransportError(reason="network")
            row=next(x for x in rows if url.endswith(x["link"]))
            return Response((
                "<html><body><h1>"+row["name"]+"</h1>"
                "<p>"+row["number"]+"</p><p>"+row["uchr_sname"]+"</p>"
                "</body></html>"
            ).encode("utf8"))
        async def post(self,url,*,json,headers):
            log.append(("POST",url))
            assert url==target.JSON_URL
            assert json["settings"]["page"]==0
            assert headers["RequestVerificationToken"]=="anonymous-public-token"
            return Response(b'{"items":[]}',"application/json")

    @asynccontextmanager
    async def mocked_client(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        yield Client()
    monkeypatch.setattr(target,"source_client",mocked_client)
    return log


def test_two_official_detail_ids_are_proved_only_by_visible_exact_fields(monkeypatch):
    log=prepare(monkeypatch)
    r=asyncio.run(target.inspect_details())
    assert r=={"stage":"INDEPENDENT_DETAIL_FIELDS",
               "category":"independent_originals_verified",
               "verified_original_details":2}
    assert [x[0] for x in log]==["GET","POST","GET","GET"]


def test_native_json_without_accessible_detail_does_not_claim_two_originals(monkeypatch):
    log=prepare(monkeypatch,failure="details")
    r=asyncio.run(target.inspect_details())
    assert r=={"stage":"OFFICIAL_DETAIL_GET","category":"network",
               "verified_original_details":0}
    assert len(log)==3


def test_successful_details_are_still_not_release_proof(monkeypatch,capsys):
    prepare(monkeypatch)
    assert target.main()==0
    out=capsys.readouterr().out
    assert "TWO_INDEPENDENT_DETAILS_CONFIRMED=TRUE" in out
    assert "FENCED_WORKER_SQL_SEARCH=NOT_VERIFIED" in out
    assert "RELEASE_READY=NO" in out
    assert "PUBLIC_SOURCE_DEPLOYMENT=NO" in out
