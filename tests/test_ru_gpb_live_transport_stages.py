"""Offline safety tests for a diagnostic, NEVER genuine GPB procurement acceptance."""
import asyncio
from contextlib import asynccontextmanager

import httpx
import pytest

from app.sources.http import ConnectorTransportError
from scripts import ci_ru_gpb_live_transport_stages as diag

ID = "1299761"
URL = "https://etpgpb.ru/procedures/etp/1299761/"
LIST = f"<html><a href='{URL}'>Current tender</a></html>".encode()
# Includes full independent human-visible procedure ID and one H1.
DETAIL = (f"<html><body><div>Номер процедуры {ID}</div>"
          "<h1>Поставка промышленного оборудования</h1></body></html>").encode()


class FakeClient:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    async def get(self, url, **kwargs):
        self.calls.append(url)
        return self.handler(url)


@asynccontextmanager
async def client_for(handler, **kwargs):
    assert kwargs["trust_env"] is False
    assert kwargs["follow_redirects"] is False
    yield FakeClient(handler)


@pytest.mark.parametrize("reason", ["tls_certificate", "public_ip", "policy"])
def test_permanent_html_transport_stops_without_rss_fallback(monkeypatch, capsys, reason):
    calls = []
    @asynccontextmanager
    async def fake_source(**kwargs):
        async with client_for(lambda url: (_ for _ in ()).throw(
            ConnectorTransportError(retryable=False, reason=reason)), **kwargs) as c:
            yield c
            calls.extend(c.calls)

    monkeypatch.setattr(diag, "source_client", fake_source)
    assert asyncio.run(diag.probe()) == 2
    assert calls == [diag.LIST_URL]
    report = capsys.readouterr().out
    assert "GPB_STAGE=LIST_GET" in report
    assert f"GPB_TRANSPORT_REASON={reason}" in report
    assert "GPB_STAGE=FIRSTPARTY_DETAIL_VERIFIED" not in report


@pytest.mark.parametrize("status", [401, 403, 404, 500])
def test_http_error_page_with_true_id_and_heading_never_confirms_detail(
    monkeypatch, capsys, status,
):
    calls = []

    def handler(url):
        if url == diag.LIST_URL:
            return httpx.Response(200, content=LIST,
                                  headers={"content-type": "text/html"},
                                  request=httpx.Request("GET", url))
        assert url == URL
        return httpx.Response(status, content=DETAIL,
                              headers={"content-type": "text/html"},
                              request=httpx.Request("GET", url))

    @asynccontextmanager
    async def fake_source(**kwargs):
        async with client_for(handler, **kwargs) as c:
            yield c
            calls.extend(c.calls)

    monkeypatch.setattr(diag, "source_client", fake_source)
    assert asyncio.run(diag.probe()) == 2
    assert calls == [diag.LIST_URL, URL]
    report = capsys.readouterr().out
    assert "GPB_STAGE=NO_VERIFIED_FIRSTPARTY_DETAIL" in report
    assert "GPB_STALE_DETAILS_IGNORED=1" in report
    assert "FIRSTPARTY_DETAIL_VERIFIED" not in report


def test_only_real_200_exact_detail_can_pass_diagnostic(monkeypatch, capsys):
    def handler(url):
        if url == diag.LIST_URL:
            body = LIST
        elif url == URL:
            body = DETAIL
        else:
            raise AssertionError("Unapproved synthetic URL")
        return httpx.Response(200, content=body,
                              headers={"content-type": "text/html"},
                              request=httpx.Request("GET", url))

    @asynccontextmanager
    async def fake_source(**kwargs):
        async with client_for(handler, **kwargs) as c:
            yield c

    monkeypatch.setattr(diag, "source_client", fake_source)
    assert asyncio.run(diag.probe()) == 0
    assert "GPB_STAGE=FIRSTPARTY_DETAIL_VERIFIED" in capsys.readouterr().out
