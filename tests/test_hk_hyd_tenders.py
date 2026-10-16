"""No-network regression and security gate for official HyD RSS."""
import asyncio

import pytest
from app.sources.hk_hyd_tenders import (
    HighwaysTendersSource, SOURCE_ID, RSS_URL, parse_hyd_tenders,
)
from app.sources.eis_rss import SourceError
from app.sources.opportunities import validate_notice

DETAIL = "https://www.hyd.gov.hk/en/tender_notices/contracts/prequalifications_and_tender_notices/2026/04HY2026.html"


def rss(url=DETAIL, title="04/HY2026 Highways Department Term Contract"):
    return (f'<rss version="2.0"><channel><item><title>{title}</title>'
            f'<link>{url}</link><pubDate>Fri, 16 Oct 2026 05:00:00 GMT</pubDate>'
            f'<description>Maintenance of public roads 2027-2032</description>'
            f'</item></channel></rss>').encode()


def test_published_official_single_notice_normalizes_and_preserves_unknown_fields():
    item = parse_hyd_tenders(rss())[0]
    validate_notice(item, SOURCE_ID)
    assert item.url == DETAIL
    assert item.title.startswith("04/HY2026")
    assert item.customer == "Hong Kong Highways Department"
    assert item.region == "Hong Kong"
    assert item.published_at is not None
    assert item.deadline is None and item.initial_price is None
    assert parse_hyd_tenders(rss())[0].external_id == item.external_id


@pytest.mark.parametrize("url", [
    "https://www.hyd.gov.hk.evil.example/en/tender_notices/contracts/test.html",
    "http://evil.example/en/tender_notices/contracts/test.html",
    "https://www.hyd.gov.hk:8080/en/tender_notices/contracts/test.html",
    "https://www.hyd.gov.hk/en/tender_notices/index.html",
    "https://www.hyd.gov.hk/en/information_corner/whats_new/",
    "https://www.hyd.gov.hk/en/tender_notices/contracts/awards/index.html",
    "https://www.hyd.gov.hk/en/tender_notices/forecasts/forecast.html",
    "https://www.hyd.gov.hk/en/tender_notices/contracts/test.html#fragment",
])
def test_unapproved_or_not_detail_url_fails_closed(url):
    with pytest.raises(SourceError, match="no verified"):
        parse_hyd_tenders(rss(url=url))


@pytest.mark.parametrize("title", [
    "Contracts Awarded in Past 12 Months", "Tender Awards", "Forecast of Invitations to Tenders",
    "Online Briefing Sessions for Upcoming Engineering Contracts",
])
def test_non_current_research_not_misrepresented_as_open_tender(title):
    with pytest.raises(SourceError, match="no verified"):
        parse_hyd_tenders(rss(title=title))


def test_invalid_xml_bomb_html_and_empty_are_rejected():
    for value in (b"", b"<!DOCTYPE X><rss/>", b"<html></html>", b"<rss",
                  b"x" * (1024 * 1024 + 1)):
        with pytest.raises(SourceError):
            parse_hyd_tenders(value)


def test_official_http_only_upgraded_no_unsafe_remote_fetch():
    item = parse_hyd_tenders(rss(url=DETAIL.replace("https:", "http:")))[0]
    assert item.url == DETAIL


def test_fixed_network_route(monkeypatch):
    called = []

    async def fetch(url, timeout, accept):
        called.append((url, timeout, accept))
        return rss()
    monkeypatch.setattr("app.sources.hk_hyd_tenders._fetch", fetch)
    notices = asyncio.run(HighwaysTendersSource().fetch(limit=5))
    assert len(notices) == 1
    assert called == [(RSS_URL, 25.0, "application/rss+xml,application/xml,text/xml")]


def test_independent_opt_in_and_six_plus_jetro_unchanged(monkeypatch):
    from scripts.asia_six_live_acceptance import settings
    from app.sources.catalog import build_source_catalog
    from app.sources.asia_public import ASIA_RSS_FEEDS
    monkeypatch.delenv("VALYQON_ASIA_HYD_ENABLED", raising=False)
    monkeypatch.setenv("VALYQON_ASIA_SOURCES_ENABLED", "1")
    monkeypatch.setenv("VALYQON_ASIA_JETRO_BID_ENABLED", "1")
    assert SOURCE_ID not in build_source_catalog(settings()).registry.keys()
    assert len(ASIA_RSS_FEEDS) == 6
    monkeypatch.setenv("VALYQON_ASIA_HYD_ENABLED", "1")
    c = build_source_catalog(settings())
    assert SOURCE_ID in c.enabled_keys
    assert all(x in c.enabled_keys for x in ASIA_RSS_FEEDS)
    assert "jp_jetro_bid" in c.enabled_keys
