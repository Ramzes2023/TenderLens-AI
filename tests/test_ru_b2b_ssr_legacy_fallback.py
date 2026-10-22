"""OFFLINE contracts for a fail-closed B2B SSR URL-drift recovery path.

These fixtures never prove live ingestion; mandatory GitHub live Worker, SQL
search, scorer and source-health jobs remain the release gate.
"""
import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.sources.b2b_center import (
    B2BCenterSource, B2B_CENTER_LIST_URL, B2B_CENTER_NEXT_LIST_URL,
)
from app.sources.eis_rss import SourceError
from app.sources.http import _policy
import app.sources.b2b_center as module


BAD_SSR = (
    b'<div class="panel-procedure__card">'
    b'<a class="panel-procedure__number-link"'
    b' href="https://evil.invalid/market/false/tender-99999999/">'
    b'No 99999999</a></div>'
)
GOOD_LEGACY = (
    b'<div class="cards" itemtype="https://schema.org/ListItem">'
    b'<div itemtype="https://schema.org/Demand">'
    b'<meta itemprop="businessFunction" content="http://purl.org/goodrelations/v1#Buy">'
    b'<link itemprop="url" href="https://www.b2b-center.ru/search/number/99999999/">'
    b'<meta itemprop="name" content="Synthetic offline B2B equipment">'
    b'<a href="https://www.b2b-center.ru/market/equipment/tender-99999999/">'
    b'&#1047;&#1072;&#1082;&#1091;&#1087;&#1082;&#1072; &#8470;99999999</a>'
    b'</div></div>'
)
FOREIGN_LEGACY = GOOD_LEGACY.replace(
    b'https://www.b2b-center.ru/market/equipment/tender-99999999/',
    b'https://www.rts-tender.ru/notices/99999999',
)


def fake_official_client(monkeypatch, initial, legacy):
    calls = []

    class Client:
        from httpx import Cookies
        cookies = Cookies()

        async def get(self, url):
            calls.append(url)
            if url == B2B_CENTER_NEXT_LIST_URL:
                data = initial
            elif url == B2B_CENTER_LIST_URL:
                data = legacy
            else:
                raise AssertionError("Unapproved source URL")
            return SimpleNamespace(
                status_code=200, content=data, raise_for_status=lambda: None
            )

    @asynccontextmanager
    async def factory(**kwargs):
        assert kwargs["follow_redirects"] is False
        assert kwargs["trust_env"] is False
        policy = _policy.get()
        assert policy is not None
        assert policy.max_requests == 2
        assert policy.hosts == module.B2B_CENTER_HOSTS
        yield Client()

    monkeypatch.setattr(module, "source_client", factory)
    return calls


def test_unsafe_ssr_href_requires_independently_verified_official_legacy(monkeypatch):
    calls = fake_official_client(monkeypatch, BAD_SSR, GOOD_LEGACY)
    rows = asyncio.run(B2BCenterSource().fetch(limit=10))
    assert calls == [B2B_CENTER_NEXT_LIST_URL, B2B_CENTER_LIST_URL]
    assert len(rows) == 1
    assert rows[0].tender_number == "99999999"
    assert rows[0].origin == "first_party"
    assert rows[0].listing_url == B2B_CENTER_LIST_URL
    summary = json.loads(rows[0].summary)
    assert summary["coverage_scope"] == "aggregate"
    assert summary["listing_url"] == B2B_CENTER_LIST_URL


def test_legacy_foreign_aggregate_cannot_be_relabelled_native(monkeypatch):
    calls = fake_official_client(monkeypatch, BAD_SSR, FOREIGN_LEGACY)
    with pytest.raises(SourceError, match="no usable procurement records"):
        asyncio.run(B2BCenterSource().fetch(limit=10))
    assert calls == [B2B_CENTER_NEXT_LIST_URL, B2B_CENTER_LIST_URL]


def test_other_ssr_parser_failures_do_not_silently_trigger_fallback(monkeypatch):
    calls = fake_official_client(monkeypatch, b'<html>No SSR cards</html>', GOOD_LEGACY)
    with pytest.raises(SourceError, match="no usable procurement records"):
        asyncio.run(B2BCenterSource().fetch(limit=10))
    assert calls == [B2B_CENTER_NEXT_LIST_URL]
