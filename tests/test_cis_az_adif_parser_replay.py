"""ADIF bounded replay contracts. OFFLINE only; not a live procurement proof."""
import asyncio

import httpx
import pytest

import app.sources.az_adif_small as source
from app.sources.eis_rss import SourceError
from app.sources.http import BoundedClient, ConnectorTransportError, FetchPolicy, _policy, bounded_fetch


ORIGINAL = (
    "<html><article>"
    "<p>Əmanətlərin Sığortalanması Fondu mətbəə məhsullarının "
    "satınalınması ilə bağlı kotirovka sorğusu elan edir.</p>"
    "<p>Təkliflər 19 oktyabr 2026-cı il saat 12:00-dək qəbul olunur.</p>"
    "<p>Elanın yerləşdirilmə tarixi: 02.10.2026</p>"
    '<a href="https://adif.gov.az/media/2026/10/09/kotirovka_sorusu___-mtb.docx">'
    "Kotirovka sorğusu</a></article></html>"
)
MALFORMED = "<html><h1>Official list temporarily unavailable</h1></html>"


def install_bounded_official_transport(monkeypatch, replies):
    calls = []

    def route(request):
        assert str(request.url) == source.URL
        assert "cookie" not in request.headers
        calls.append(str(request.url))
        code, html, content_type = replies[min(len(calls) - 1, len(replies) - 1)]
        return httpx.Response(code, text=html, headers={"content-type": content_type,
                                                         "set-cookie": "session=synthetic; Path=/"})

    def client(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        return BoundedClient(transport=httpx.MockTransport(route), **kwargs)
    monkeypatch.setattr(source, "source_client", client)
    return calls


def fetch_with_budget():
    policy = FetchPolicy(frozenset({source.HOST}), 2, max_bytes=source.MAX_BYTES)
    async def run():
        with bounded_fetch(policy):
            result = await source.AzerbaijanAdifSmallSource().fetch(limit=5)
            return result
    return asyncio.run(run()), policy


def test_first_html_schema_drift_retries_same_origin_and_keeps_closed_bids_closed(monkeypatch):
    calls = install_bounded_official_transport(monkeypatch, [
        (200, MALFORMED, "text/html"),
        (200, ORIGINAL, "text/html"),
    ])
    rows, policy = fetch_with_budget()
    assert rows == []  # Official bid closed on October 19. Never send stale tenders.
    assert calls == [source.URL, source.URL]
    assert policy.requests == policy.max_requests == 2


def test_first_verified_listing_does_not_waste_second_request(monkeypatch):
    calls = install_bounded_official_transport(monkeypatch, [(200, ORIGINAL, "text/html")])
    rows, policy = fetch_with_budget()
    assert rows == []
    assert calls == [source.URL]
    assert policy.requests == 1


def test_two_invalid_official_responses_remain_red(monkeypatch):
    calls = install_bounded_official_transport(monkeypatch, [(200, MALFORMED, "text/html")])
    with pytest.raises(SourceError, match="article structure"):
        fetch_with_budget()
    assert calls == [source.URL, source.URL]


@pytest.mark.parametrize("status", [401, 403, 404, 429, 503])
def test_http_auth_rate_limit_and_upstream_errors_are_not_schema_replays(monkeypatch, status):
    calls = install_bounded_official_transport(monkeypatch, [(status, MALFORMED, "text/html")])
    with pytest.raises(SourceError, match="official HTTPS"):
        fetch_with_budget()
    assert calls == [source.URL]


def test_non_html_content_is_not_replayed_as_a_tender(monkeypatch):
    calls = install_bounded_official_transport(monkeypatch, [(200, "{}", "application/json")])
    with pytest.raises(SourceError, match="not HTML"):
        fetch_with_budget()
    assert calls == [source.URL]


def test_untrusted_first_party_document_does_not_enter_results(monkeypatch):
    forged = ORIGINAL.replace(
        "https://adif.gov.az/media/2026/10/09/kotirovka_sorusu___-mtb.docx",
        "https://evil.invalid/media/2026/10/09/kotirovka_sorusu___-mtb.docx",
    )
    calls = install_bounded_official_transport(monkeypatch, [(200, forged, "text/html")])
    with pytest.raises(SourceError):
        fetch_with_budget()
    assert calls == [source.URL, source.URL]
