"""An inaccessible official detail is never a tender, even with the bounded
production HTTP client. Synthetic responses only: live CI is still required.
"""
import asyncio

import httpx
import pytest

from app.sources.az_azeristilik import (
    AzerbaijanHeatSource, INDEX_URL, SOURCE,
)
from app.sources.http import BoundedClient, ConnectorTransportError, FetchPolicy, bounded_fetch, _policy
from app.sources.eis_rss import SourceError
from app.sources.transport_errors import SourceTransportError
import app.sources.az_azeristilik as source


TITLE = "İş yerlərinin attestasiyasının keçirilməsi xidmətinin satınalınmasına dair kotirovka sorğusu elan edir"
ORIGINAL = "https://azeristilik.gov.az/post/is-yerlerinin-attestasiyasinin-kecirilmesi-xidmetinin-satinalinmasina-dair-kotirovka-sorgusu-elan-edir"
SECOND = "https://azeristilik.gov.az/post/obsolete-procurement-announcement-2026"
INDEX = ('<a href="' + ORIGINAL + '">' + TITLE + '</a>'
         '<a href="' + SECOND + '">Təchizat xidməti satınalınmasına dair tender elan edir</a>')
DETAIL = (
    "<main><h1>" + TITLE + "</h1>"
    "<div>Satınalan təşkilatın adı: Azəristiliktəchizat ASC</div>"
    "<div>Müsabiqənin başlanma tarixi və vaxtı: 07.10.2026</div>"
    "<div>Təkliflərin son təqdim olunma tarixi və vaxtı: 22.10.2026</div></main>"
)


@pytest.mark.parametrize("status", [403, 404, 410])
def test_actual_bounded_client_allows_only_excluding_stale_detail(monkeypatch, status):
    called = []
    def respond(request):
        assert request.url.host == "azeristilik.gov.az"
        called.append(str(request.url))
        if str(request.url) == INDEX_URL:
            return httpx.Response(200, text=INDEX, headers={"content-type": "text/html"})
        if str(request.url) == ORIGINAL:
            return httpx.Response(200, text=DETAIL, headers={"content-type": "text/html"})
        if str(request.url) == SECOND:
            return httpx.Response(status, content=b"not a public tender")
        raise AssertionError("unexpected official route")

    def fake_client(**kwargs):
        assert kwargs["follow_redirects"] is False
        assert kwargs["trust_env"] is False
        return BoundedClient(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(source, "source_client", fake_client)
    notices = asyncio.run(AzerbaijanHeatSource().fetch(limit=2))
    assert [x.url for x in notices] == [ORIGINAL]
    assert called == [INDEX_URL, ORIGINAL, SECOND]
    assert notices[0].source == SOURCE


@pytest.mark.parametrize("status", [401, 429, 500, 302])
def test_bounded_client_does_not_accept_unapproved_status(monkeypatch, status):
    def respond(request):
        if str(request.url) == INDEX_URL:
            return httpx.Response(200, text=INDEX, headers={"content-type": "text/html"})
        if str(request.url) == ORIGINAL:
            return httpx.Response(200, text=DETAIL, headers={"content-type": "text/html"})
        if str(request.url) == SECOND:
            return httpx.Response(status, headers={"location": "https://outside.invalid/"})
        raise AssertionError("unexpected route")

    def fake_client(**kwargs):
        return BoundedClient(transport=httpx.MockTransport(respond), **kwargs)
    monkeypatch.setattr(source, "source_client", fake_client)
    with pytest.raises((SourceError, SourceTransportError)):
        asyncio.run(AzerbaijanHeatSource().fetch(limit=2))


def test_non_az_bounded_http_policy_is_fail_closed_for_404():
    async def scenario():
        with bounded_fetch(FetchPolicy(frozenset({"azeristilik.gov.az"}), 1)):
            async with BoundedClient(transport=httpx.MockTransport(
                    lambda req: httpx.Response(404)), trust_env=False) as client:
                with pytest.raises(ConnectorTransportError) as error:
                    await client.get(INDEX_URL)
                assert error.value.reason == "http_status"
    asyncio.run(scenario())
