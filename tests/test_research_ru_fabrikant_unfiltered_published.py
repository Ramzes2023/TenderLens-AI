"""Research only: official Fabrikant list HTML may not imply source readiness."""
import asyncio
from contextlib import asynccontextmanager

from app.sources.http import ConnectorTransportError
from scripts import research_ru_fabrikant_unfiltered_published as subject


def test_known_firstparty_published_original_anchor_and_foreign_host_excluded():
    html = (
        "<html><main><h1>Реестр опубликованных закупок по 44-ФЗ</h1>"
        "<a href='/44/procedure/ea21/0114500000826002518'>Ингушетия</a>"
        "<a href='https://soap4.fabrikant.ru/44/procedure/ea21/0194200000526005756'>Чечня</a>"
        "<a href='https://untrusted.invalid/44/procedure/ea21/0194200000526005775'>Чужой</a>"
        "</main></html>"
    ).encode("utf8")
    result = subject.classify_publisher_html(
        html, host="soap4.fabrikant.ru")
    assert result == {
        "category": "firstparty_published_anchor_candidates",
        "firstparty_anchor_count": 2,
        "known_current_ids": 2,
    }


def test_login_captcha_and_no_links_are_never_source_evidence():
    for challenge in ["Необходимо авторизоваться", "Введите капчу",
                      "Подтвердите, что вы не робот"]:
        html = (
            "<h1>" + challenge + "</h1>"
            "<a href='/44/procedure/ea21/0114500000826002518'>x</a>"
        ).encode("utf8")
        result = subject.classify_publisher_html(
            html, host="44.fabrikant.ru")
        assert result == {
            "category": "official_login_or_challenge",
            "firstparty_anchor_count": 0, "known_current_ids": 0,
        }
    plain = subject.classify_publisher_html(
        b"<html><h1>No public table</h1></html>", host="soap4.fabrikant.ru")
    assert plain["firstparty_anchor_count"] == 0
    assert plain["category"] == "firstparty_published_html_without_anchors"


def test_research_probe_contacts_only_fixed_publisher_routes(monkeypatch):
    calls = []
    source = (
        b"<html><a href='/44/procedure/ea21/0114500000826002518'>"
        b"first party</a></html>"
    )
    class Reply:
        headers={"content-type":"text/html; charset=utf-8"}
        content=source
        def raise_for_status(self):
            pass

    class Client:
        async def get(self, url):
            calls.append(url)
            return Reply()

    @asynccontextmanager
    async def fake_source_client(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        assert kwargs["timeout"] <= 25
        yield Client()

    monkeypatch.setattr(subject, "source_client", fake_source_client)
    result = asyncio.run(subject.inspect())
    assert len(result) == 4
    assert all(r["category"] == "firstparty_published_anchor_candidates"
               for r in result)
    assert set(calls) == {
        f"https://{h}{subject.PATH}{suffix}"
        for h in subject.HOSTS for suffix in subject.SUFFIXES
    }
    assert all(r["known_current_ids"] == 1 for r in result)


def test_blocked_publisher_stays_blocked_without_leaking_exception(monkeypatch,capsys):
    class Client:
        async def get(self, url):
            raise ConnectorTransportError(reason="network")
    @asynccontextmanager
    async def fake_client(**kwargs):
        yield Client()
    monkeypatch.setattr(subject,"source_client",fake_client)
    result=asyncio.run(subject.inspect())
    assert len(result)==4
    assert all(r["category"]=="network" for r in result)
    assert all(r["firstparty_anchor_count"]==0 for r in result)
    assert subject.main()==0
    output=capsys.readouterr().out
    assert "REGION_SCOPED_AUTOMATIC_DISCOVERY=NOT_PROVED" in output
    assert "ACTUAL_WORKER_SQL_GUEST=NOT_PROVED" in output
    assert "PRODUCTION_CHANGED=NO" in output
    assert "RELEASE_READY=NO" in output
