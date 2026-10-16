"""Offline safety and integration contracts for TWO anonymous GeBIZ RSS sources."""
import asyncio
from html import escape

import pytest

from app.sources.sg_gebiz_rss import FEEDS, SingaporeGeBizRssSource, parse_gebiz_business_rss
from app.sources.eis_rss import SourceError
from app.sources.opportunities import validate_notice

CODE = "PAS000ETT26000100"
URL = ("https://www.gebiz.gov.sg/ptn/opportunity/opportunityDetails.xhtml?"
       "code=" + CODE + "&status=OPEN&type=TENDER&OPPORTUNITY_ID=AB12CD34EF&origin=rss")


def rss(link=URL, title="Supply and maintenance of equipment"):
    return ("<rss version='2.0'><channel><item><title>" + escape(title) +
            "</title><link>" + escape(link) + "</link>"
            "<pubDate>Fri, 16 Oct 2026 12:00:00 GMT</pubDate>"
            "<description>Opportunity for government supplies</description></item>"
            "</channel></rss>").encode("utf-8")


@pytest.mark.parametrize("source", list(FEEDS))
def test_official_business_opportunity_normalizes_and_deduplicates(source):
    rows = parse_gebiz_business_rss(rss(), source=source)
    assert len(rows) == 1
    item = rows[0]
    validate_notice(item, source)
    assert item.source == source and item.tender_number == CODE
    assert item.url == URL
    assert item.region == "Singapore"
    assert item.initial_price is None and item.deadline is None
    assert item.identity == parse_gebiz_business_rss(rss(), source=source)[0].identity


@pytest.mark.parametrize("url", [
    "https://www.gebiz.gov.sg.attacker.example/ptn/opportunity/opportunityDetails.xhtml?code=PAS000ETT26000100",
    "https://evil.example/ptn/opportunity/opportunityDetails.xhtml?code=PAS000ETT26000100",
    "https://www.gebiz.gov.sg:8080/ptn/opportunity/opportunityDetails.xhtml?code=PAS000ETT26000100",
    "https://www.gebiz.gov.sg/ptn/opportunity/BOListing.xhtml?code=PAS000ETT26000100",
    "https://www.gebiz.gov.sg/ptn/opportunity/opportunityDetails.xhtml?code=PAS000ETT26000100",
    URL + "&token=secret",
    URL + "#fragment",
])
def test_rejects_cross_origin_index_unknown_query_and_missing_id(url):
    with pytest.raises(SourceError, match="no verified"):
        parse_gebiz_business_rss(rss(link=url), source="sg_gebiz_professional")


def test_rejects_awards_even_when_link_masquerades_as_business_opportunity():
    with pytest.raises(SourceError):
        parse_gebiz_business_rss(rss(title="Tender Awards"), source="sg_gebiz_misc")


def test_invalid_xml_and_oversized_responses_fail_closed():
    for payload in (
        b"", b"<html />", b"<rss", b'<!DOCTYPE a [<!ENTITY x SYSTEM "file:///etc/passwd">]><rss/>',
        b"X" * (1024 * 1024 + 1),
    ):
        with pytest.raises(SourceError):
            parse_gebiz_business_rss(payload, source="sg_gebiz_professional")


def test_one_official_immutable_rss_request(monkeypatch):
    calls = []
    async def fake(url, timeout, accept):
        calls.append((url, timeout, accept))
        return rss()
    monkeypatch.setattr("app.sources.sg_gebiz_rss._fetch", fake)
    for source in FEEDS:
        assert len(asyncio.run(SingaporeGeBizRssSource(source).fetch())) == 1
    assert [x[0] for x in calls] == list(FEEDS.values())


def test_independent_opt_in_does_not_change_hk_japan(monkeypatch):
    from scripts.asia_six_live_acceptance import settings
    from app.sources.catalog import build_source_catalog
    from app.sources.asia_public import ASIA_RSS_FEEDS

    monkeypatch.delenv("VALYQON_ASIA_GEBIZ_ENABLED", raising=False)
    monkeypatch.setenv("VALYQON_ASIA_SOURCES_ENABLED", "1")
    monkeypatch.setenv("VALYQON_ASIA_JETRO_BID_ENABLED", "1")
    monkeypatch.setenv("VALYQON_ASIA_HYD_ENABLED", "1")
    before = build_source_catalog(settings())
    assert not set(FEEDS) & set(before.registry.keys())
    monkeypatch.setenv("VALYQON_ASIA_GEBIZ_ENABLED", "1")
    after = build_source_catalog(settings())
    assert set(FEEDS) <= set(after.enabled_keys)
    assert set(before.enabled_keys) <= set(after.enabled_keys)
    assert len(ASIA_RSS_FEEDS) == 6
