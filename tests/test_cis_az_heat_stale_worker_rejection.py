"""OFFLINE hardened Worker HTTP boundary for public Azerbaijan heat notices.

No mocked response here proves genuine live procurement, stored SQL or Telegram.
A Worker release still requires current first-party HTTPS -> fenced SQL -> search.
"""
import asyncio
from contextlib import asynccontextmanager

import httpx
import pytest

import app.sources.az_azeristilik as az
from app.sources.eis_rss import SourceError
from app.sources.http import BoundedClient, FetchPolicy, bounded_fetch
from app.sources.transport_errors import SourceTransportError


TITLE = "İş yerlərinin attestasiyasının keçirilməsi xidmətinin satınalınmasına dair kotirovka sorğusu elan edir"
VALID = ("https://azeristilik.gov.az/post/"
         "is-yerlerinin-attestasiyasinin-kecirilmesi-xidmetinin-satinalinmasina-dair-kotirovka-sorgusu-elan-edir")
STALE = "https://azeristilik.gov.az/post/obsolete-procurement-announcement-2026"
INDEX = ('<html><a href="' + VALID + '">' + TITLE + '</a>'
         '<a href="' + STALE + '">Təchizat xidməti satınalınmasına dair tender elan edir</a></html>')
DETAIL = (
    "<main><h1>" + TITLE + "</h1>"
    "<div>Satınalan təşkilatın adı: Azəristiliktəchizat ASC</div>"
    "<div>Müsabiqənin başlanma tarixi və vaxtı: 07.10.2026</div>"
    "<div>Təkliflərin son təqdim olunma tarixi və vaxtı: 22.10.2026</div></main>"
)


def wire(monkeypatch, *, stale_status=404, index_status=200,
         valid_status=200, list_body=INDEX):
    requests = []

    def respond(request):
        url = str(request.url)
        requests.append((str(request.method), url))
        assert request.url.scheme == "https" and request.url.host == az.HOST
        if url == az.INDEX_URL:
            return httpx.Response(index_status, text=list_body,
                                  headers={"content-type": "text/html"})
        if url == VALID:
            return httpx.Response(valid_status, text=DETAIL,
                                  headers={"content-type": "text/html"})
        if url == STALE:
            return httpx.Response(stale_status, text="not an original notice",
                                  headers={"content-type": "text/html"})
        raise AssertionError("Disallowed source network route")

    def official_client(**kwargs):
        assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        # Keep actual hardened BoundedClient status rejection; do not use a
        # permissive standard HTTPX client as a substitute.
        return BoundedClient(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(az, "source_client", official_client)
    return requests


async def run_with_worker_limit(n=2):
    policy = FetchPolicy(frozenset({az.HOST}), 1 + az.MAX_DETAILS,
                         max_bytes=az.MAX_BODY)
    with bounded_fetch(policy):
        rows = await az.AzerbaijanHeatSource().fetch(n)
    return rows, policy.requests


@pytest.mark.parametrize("status", [403, 404, 410])
def test_stale_individual_is_excluded_but_verified_neighbour_survives(monkeypatch, status):
    seen = wire(monkeypatch, stale_status=status)
    rows, count = asyncio.run(run_with_worker_limit())
    assert len(rows) == 1
    assert rows[0].url == VALID and rows[0].customer == "Azəristiliktəchizat ASC"
    assert count == 3
    assert seen == [("GET", az.INDEX_URL), ("GET", VALID), ("GET", STALE)]


@pytest.mark.parametrize("status", [401, 429, 500, 302])
def test_restricted_or_failed_details_never_turn_into_partial_success(monkeypatch, status):
    seen = wire(monkeypatch, stale_status=status)
    with pytest.raises((SourceError, SourceTransportError)):
        asyncio.run(run_with_worker_limit())
    assert len(seen) == 3


def test_all_stale_details_are_not_a_verified_batch(monkeypatch):
    seen = wire(monkeypatch, valid_status=404, stale_status=404)
    with pytest.raises(SourceError, match="complete notice batch empty"):
        asyncio.run(run_with_worker_limit())
    assert len(seen) == 3


def test_index_access_denied_is_never_treated_as_skippable_detail(monkeypatch):
    seen = wire(monkeypatch, index_status=403)
    with pytest.raises(SourceError):
        asyncio.run(run_with_worker_limit())
    assert seen == [("GET", az.INDEX_URL)]


def test_non_html_individual_is_not_accepted_as_original(monkeypatch):
    seen = []
    def respond(request):
        url = str(request.url)
        seen.append(url)
        if url == az.INDEX_URL:
            return httpx.Response(200, text=INDEX, headers={"content-type": "text/html"})
        if url == VALID:
            return httpx.Response(200, content=b"%PDF-1.7",
                                  headers={"content-type": "application/pdf"})
        if url == STALE:
            return httpx.Response(404)
        raise AssertionError("Unexpected route")
    monkeypatch.setattr(
        az, "source_client",
        lambda **kwargs: BoundedClient(transport=httpx.MockTransport(respond),
                                       **kwargs),
    )
    with pytest.raises(SourceError, match="complete notice batch empty"):
        asyncio.run(run_with_worker_limit())
    assert seen == [az.INDEX_URL, VALID, STALE]
