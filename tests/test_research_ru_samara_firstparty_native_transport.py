"""No Samara diagnostic outcome can be mistaken for working procurement."""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

from app.sources.http import ConnectorTransportError
from scripts import research_ru_samara_firstparty_native_transport as subject


class Reply:
    def __init__(self, body=b"<html>public grid</html>", kind="text/html"):
        self.content=body
        self.headers={"content-type":kind}

    def raise_for_status(self):
        return None

    def json(self):
        return {"items":[],"totalRows":0}


def client_factory(*, fail="", sent=None):
    sent = [] if sent is None else sent

    class Client:
        async def get(self, url):
            sent.append(("GET",url))
            if fail == "GET":
                raise ConnectorTransportError(reason="network")
            return Reply()

        async def post(self,url,*,json,headers):
            sent.append(("POST",url))
            assert url == subject.JSON_URL
            assert json["settings"]["page"] == 0
            assert json["settings"]["rp"] == subject.PAGE_SIZE
            assert headers["RequestVerificationToken"] == "anonymous-fixed-token"
            assert headers["Referer"] == subject.GRID
            assert headers["X-Requested-With"] == "XMLHttpRequest"
            if fail == "POST":
                raise ConnectorTransportError(reason="http_status")
            return Reply(b'{"items":[],"totalRows":0}',"application/json")

    @asynccontextmanager
    async def fake_source_client(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        assert kwargs["timeout"] <= 25
        yield Client()

    return fake_source_client,sent


def test_official_grid_block_never_claims_live_success(monkeypatch):
    fake,sent=client_factory(fail="GET")
    monkeypatch.setattr(subject,"source_client",fake)
    result=asyncio.run(subject.inspect())
    assert (result.stage,result.category,result.verified_list_rows)==(
        "OFFICIAL_GRID_GET","network",0)
    assert sent == [("GET",subject.GRID)]


def test_post_is_accurately_classified_without_exposing_tokens(monkeypatch):
    fake,sent=client_factory(fail="POST")
    monkeypatch.setattr(subject,"source_client",fake)
    monkeypatch.setattr(subject,"public_token",lambda body:"anonymous-fixed-token")
    result=asyncio.run(subject.inspect())
    assert result.stage=="FIRSTPARTY_NOTICESJSON_POST"
    assert result.category=="http_status"
    assert len(sent)==2
    assert sent[1][1]==subject.JSON_URL


def test_native_list_success_still_does_not_verify_original_details(monkeypatch,capsys):
    fake,sent=client_factory()
    monkeypatch.setattr(subject,"source_client",fake)
    monkeypatch.setattr(subject,"public_token",lambda body:"anonymous-fixed-token")
    monkeypatch.setattr(subject,"parse_public_list",lambda value,limit:[
        SimpleNamespace(external_id="111111"),SimpleNamespace(external_id="222222")
    ])
    result=asyncio.run(subject.inspect())
    assert result.verified_list_rows == 2
    assert result.category=="visible_unverified_detail"
    assert subject.main()==0
    output=capsys.readouterr().out
    assert "RELEASE_READY=NO" in output
    assert "PUBLIC_FIRSTPARTY_ORIGINAL_DETAILS=NOT_VERIFIED" in output
    assert "FENCED_WORKER_SQL_PUBLIC_SEARCH=NOT_VERIFIED" in output


def test_no_sensitive_raw_transport_messages_in_classification(capsys):
    secret="api_key=VERY_PRIVATE"
    assert subject.classify(ConnectorTransportError(reason="network"))=="network"
    assert subject.classify(ConnectorTransportError(reason="private_key"))=="unclassified"
    assert subject.classify(ValueError(secret))=="official_contract"
    assert secret not in capsys.readouterr().out


def test_source_diagnostic_stays_immutable_and_research_only():
    from pathlib import Path
    content=Path("scripts/research_ru_samara_firstparty_native_transport.py").read_text()
    assert "RELEASE_READY=NO" in content
    assert "PRODUCTION_CHANGED=NO" in content
    assert "telegram" not in content.lower().split("def main()")[1]
    assert "database" not in content.lower().split("def main()")[1]
