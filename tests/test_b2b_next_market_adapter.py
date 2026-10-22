"""Strict Vue SSR connector regressions; HTML fixture is NOT a live acceptance."""
import asyncio
from pathlib import Path

import httpx
import pytest

from app.sources.b2b_center import (
    B2BCenterSource, B2B_CENTER_NEXT_LIST_URL,
)
from app.sources.b2b_next_market import native_url, parse_next_market
from app.sources.eis_rss import SourceError
from app.sources.http import source_client, _policy

FIXTURE = (Path(__file__).parent / "fixtures" / "ru08" / "b2b_next_ssr.html").read_bytes()


def test_official_ssr_html_extracts_actual_fields_without_guessing_timezone():
    records = parse_next_market(FIXTURE)
    assert len(records) == 2
    assert [r.external_id for r in records] == ["4646931", "4646888"]
    assert [r.tender_number for r in records] == ["4646931", "4646888"]
    assert records[0].title == "Поставка сменного бурового инструмента и оснастки для нужд предприятий ЮГК"
    assert records[0].customer == 'ООО "УК ЮГК"'
    assert records[0].published_at == "2026-10-19T21:31:00"
    assert records[0].deadline == "2026-10-30T14:00:00"
    assert records[0].initial_price is None and records[0].currency is None
    assert records[1].initial_price == 3369670.50 and records[1].currency == "RUB"
    assert records[1].customer == 'ООО "ТД "ПОЛИМИР"'
    assert all(not row.url.endswith("#") and "#" not in row.url for row in records)
    assert all(row.source == "b2b_center" and row.origin == "first_party" for row in records)
    assert parse_next_market(FIXTURE, limit=1)[0].identity == records[0].identity


@pytest.mark.parametrize("replacement", [
    b'https://another-site.example/market/item/tender-4646931/',
    b'https://www.b2b-center.ru.evil.invalid/market/item/tender-4646931/',
    b'http://www.b2b-center.ru/market/item/tender-4646931/',
    b'//www.b2b-center.ru/app/market-next/slug/tender-4646931/',
    b'/app/market-next/slug/tender-4646931/?token=1',
    b'/app/market-next/slug/tender-4646931/#evil',
    b'/app/market-next/slug/tender-4646932/',
    b'/app/market-next/slug/tender-4646931/#btid=2&sqh=abcd&tsid=4646931458',
])
def test_unapproved_number_and_provenance_rejected(replacement):
    first = b'/app/market-next/postavka-smennogo-burovogo-instrumenta-i-osnastki-dlia-nuzhd/tender-4646931/#btid=2&amp;sqh=77d89240a1e0f4efb423b256d22182d01f8b6c4f&amp;tsid=4646931458'
    if replacement.startswith(b'/app/') and b'#btid=' in replacement:
        replacement = replacement.replace(b'&', b'&amp;')
    with pytest.raises(SourceError):
        parse_next_market(FIXTURE.replace(first, replacement, 1))


def test_conflicting_number_vs_card_link_fails_batch():
    sample = FIXTURE.replace(b'\xe2\x84\x96 4646931', b'\xe2\x84\x96 4646932', 1)
    with pytest.raises(SourceError):
        parse_next_market(sample)


@pytest.mark.parametrize("payload", [b"", b"<html>captcha</html>", b"\xff", b"x" * (2 * 1024 * 1024 + 1)], ids=["empty", "captcha", "invalid_utf8", "oversize_2mib"])
def test_missing_challenge_or_oversize_fails_closed(payload):
    with pytest.raises(SourceError):
        parse_next_market(payload)


def test_native_analytics_fragment_canonicalized_only_for_same_original_procedure():
    url, number = native_url(
        "/app/market-next/gofrokorob-profil-s/tender-4646888/"
        "#btid=2&sqh=77d89240a1e0f4efb423b256d22182d01f8b6c4f&tsid=4646888458"
    )
    assert number == "4646888"
    assert url == "https://www.b2b-center.ru/app/market-next/gofrokorob-profil-s/tender-4646888/"


def test_fetch_uses_only_official_new_ssr_list_without_unverified_fallback(monkeypatch):
    import app.sources.b2b_center as adapter
    calls = []
    policies = []
    def reply(request):
        calls.append(str(request.url))
        policies.append(_policy.get())
        return httpx.Response(200, content=FIXTURE, headers={"content-type": "text/html"})
    monkeypatch.setattr(adapter, "source_client",
                        lambda **kwargs: source_client(**kwargs, transport=httpx.MockTransport(reply)))
    result = asyncio.run(B2BCenterSource(timeout=10).fetch(limit=10))
    assert len(result) == 2
    assert calls == [B2B_CENTER_NEXT_LIST_URL]
    assert policies[0].hosts == frozenset({"www.b2b-center.ru"})
    assert policies[0].max_requests == 2
    assert policies[0].max_bytes == 2 * 1024 * 1024


def test_bad_ssr_response_does_not_downgrade_to_foreign_aggregate(monkeypatch):
    import app.sources.b2b_center as adapter
    calls = []
    def reply(request):
        calls.append(str(request.url))
        return httpx.Response(200, content=b"<html>Authentication required</html>")
    monkeypatch.setattr(adapter, "source_client",
                        lambda **kwargs: source_client(**kwargs, transport=httpx.MockTransport(reply)))
    with pytest.raises(SourceError):
        asyncio.run(B2BCenterSource().fetch())
    assert calls == [B2B_CENTER_NEXT_LIST_URL, B2B_CENTER_NEXT_LIST_URL]


def test_explicit_standard_tls_port_cannot_change_canonical_notice_identity():
    raw = ("https://WWW.B2B-CENTER.RU:443/app/market-next/slug/tender-4646888/"
           "#btid=2&sqh=77d89240a1e0f4efb423b256d22182d01f8b6c4f&tsid=4646888458")
    normalized, number = native_url(raw)
    assert normalized == "https://www.b2b-center.ru/app/market-next/slug/tender-4646888/"
    assert number == "4646888"



def test_changed_official_ssr_shape_retries_once_same_pinned_native_page(monkeypatch):
    import app.sources.b2b_center as adapter
    calls, policies = [], []
    def reply(request):
        calls.append(str(request.url))
        policies.append(_policy.get())
        assert "cookie" not in request.headers
        html = b"<html>temporarily changed link fragment</html>" if len(calls) == 1 else FIXTURE
        return httpx.Response(200, content=html, headers={"content-type": "text/html",
                                                         "set-cookie": "opaque=none; Path=/"})
    monkeypatch.setattr(adapter, "source_client",
                        lambda **kwargs: source_client(**kwargs, transport=httpx.MockTransport(reply)))
    notices = asyncio.run(B2BCenterSource().fetch(limit=10))
    assert len(notices) == 2
    assert calls == [B2B_CENTER_NEXT_LIST_URL] * 2
    assert policies[0] is policies[1]
    assert policies[0].max_requests == policies[0].requests == 2
    assert policies[0].hosts == frozenset({"www.b2b-center.ru"})
    assert policies[0].max_bytes == 2 * 1024 * 1024


def test_two_official_unverified_html_responses_stay_red_without_third_request(monkeypatch):
    import app.sources.b2b_center as adapter
    calls = []
    def reply(request):
        calls.append(str(request.url))
        return httpx.Response(200, content=b"<html>not actual source notices</html>")
    monkeypatch.setattr(adapter, "source_client",
                        lambda **kwargs: source_client(**kwargs, transport=httpx.MockTransport(reply)))
    with pytest.raises(SourceError):
        asyncio.run(B2BCenterSource().fetch(limit=10))
    assert calls == [B2B_CENTER_NEXT_LIST_URL] * 2


def test_one_hostile_card_then_proven_original_ssr_retries_whole_batch(monkeypatch):
    import app.sources.b2b_center as adapter
    calls = []
    hostile = FIXTURE.replace(
        b"/app/market-next/postavka-smennogo-burovogo-instrumenta-i-osnastki-dlia-nuzhd/tender-4646931/",
        b"https://outside.invalid/app/market-next/fake/tender-4646931/",
        1,
    )
    assert hostile != FIXTURE
    def reply(request):
        calls.append(str(request.url))
        return httpx.Response(200, content=hostile if len(calls) == 1 else FIXTURE)
    monkeypatch.setattr(adapter, "source_client",
                        lambda **kwargs: source_client(**kwargs, transport=httpx.MockTransport(reply)))
    output = asyncio.run(B2BCenterSource().fetch())
    assert len(output) == 2
    assert all(x.url.startswith("https://www.b2b-center.ru/") for x in output)
    assert calls == [B2B_CENTER_NEXT_LIST_URL] * 2
