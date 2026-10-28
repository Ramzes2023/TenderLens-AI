"""No alternate Samara original detail request unless official HTML authorizes it."""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from scripts import research_ru_samara_declared_detail_route as s

DECLARED=(b"<html><script>const originalDetail='/smallpurchases/GzwSP/Notice"
          b"?noticeLink=' + number;</script></html>")
NO_ROUTE=b"<html><a href='/smallpurchases/GzwSP/NoticesJson'>List</a></html>"


def test_bounded_inline_publisher_disclosure_and_foreign_script_rejection():
    assert s.explicitly_announced(DECLARED)
    assert not s.explicitly_announced(NO_ROUTE)
    assert not s.explicitly_announced(b"")
    assert not s.explicitly_announced(None)
    assert not s.explicitly_announced(
        b"<script src='//bad.invalid/a.js'></script><p>noticeLink</p>")
    assert not s.explicitly_announced(
        b"<script src='https://bad.invalid/a.js'>"
        b"/smallpurchases/GzwSP/Notice?noticeLink=123</script>")


def test_publisher_only_identity_is_bound_and_can_never_be_guessed():
    native="/smallpurchases/GzwSP/123456"
    assert s.authorized_detail_url(native,published_html=DECLARED)==(
        "https://webtorgi.samregion.ru/smallpurchases/GzwSP/Notice"
        "?noticeLink=123456"
    )
    with pytest.raises(ValueError):
        s.authorized_detail_url(native,published_html=NO_ROUTE)
    for bad in ("https://evil.example/smallpurchases/GzwSP/123456",
                "/smallpurchases/GzwSP/../123456",
                "/smallpurchases/GzwSP/123456?token=secret",
                "/smallpurchases/GzwSP/../../private"):
        with pytest.raises(ValueError):
            s.authorized_detail_url(bad,published_html=DECLARED)


def fake_client(monkeypatch,html=NO_ROUTE,fail_detail=False):
    rows=[
        {"link":"/smallpurchases/GzwSP/123456"},
        {"link":"/smallpurchases/GzwSP/123457"},
    ]
    names=[
        ("ИМЗ-2026-0-223-002452","Поставка холодильников",
         "Самарская ветеринарная лаборатория"),
        ("ИМЗ-2026-0-223-002453","Поставка реагентов",
         "Самарская больница"),
    ]
    notices=[
        SimpleNamespace(tender_number=n,title=t,customer=c)
        for n,t,c in names
    ]
    monkeypatch.setattr(s,"public_token",lambda body:"ANONYMOUS")
    monkeypatch.setattr(s,"parse_public_list",lambda body,limit:notices[:limit])
    calls=[]
    class Response:
        headers={"content-type":"text/html"}
        def __init__(self,content,kind=None):
            self.content=content
            self.headers={"content-type":kind or "text/html"}
        def raise_for_status(self):return None
        def json(self):return {"items":rows,"totalRows":2}
    class Client:
        async def get(self,url,headers=None):
            calls.append(("GET",url))
            if url==s.GRID:
                return Response(html)
            assert "?noticeLink=" in url
            if fail_detail:
                from app.sources.http import ConnectorTransportError
                raise ConnectorTransportError(reason="http_status")
            index=0 if url.endswith("123456") else 1
            n,t,c=names[index]
            return Response(("<html><h2>"+t+"</h2><div>"+n+"</div><p>"+c+
                             "</p></html>").encode("utf8"))
        async def post(self,url,json,headers):
            calls.append(("POST",url))
            assert url==s.JSON_URL
            assert json["settings"]["page"]==0
            assert headers["RequestVerificationToken"]=="ANONYMOUS"
            return Response(b'{"items":[]}',"application/json")
    @asynccontextmanager
    async def factory(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        yield Client()
    monkeypatch.setattr(s,"source_client",factory)
    return calls


def test_undeclared_route_never_even_requests_native_json_or_details(monkeypatch):
    calls=fake_client(monkeypatch)
    result=asyncio.run(s.inspect())
    assert result=={"stage":"PUBLISHER_DECLARED_ALTERNATE_ROUTE",
                   "category":"not_declared_by_publisher","independent_details":0}
    assert calls==[("GET",s.GRID)]


def test_two_exact_native_originals_require_publisher_html_and_visible_fields(monkeypatch):
    calls=fake_client(monkeypatch,html=DECLARED)
    result=asyncio.run(s.inspect())
    assert result["category"]=="native_firstparty_details_verified"
    assert result["independent_details"]==2
    assert [method for method,_ in calls]==["GET","POST","GET","GET"]


def test_upstream_detail_rejection_fails_closed(monkeypatch,capsys):
    fake_client(monkeypatch,html=DECLARED,fail_detail=True)
    result=asyncio.run(s.inspect())
    assert result=={"stage":"DECLARED_NOTICE_DETAIL_GET",
                   "category":"http_status","independent_details":0}
    assert s.main()==0
    out=capsys.readouterr().out
    assert "RELEASE_READY=NO" in out
    assert "PUBLIC_SOURCE_ENABLED=NO" in out
    assert "TWO_INDEPENDENT_OFFICIAL_ORIGINALS=FALSE" in out
