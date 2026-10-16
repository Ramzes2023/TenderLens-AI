"""No-network contracts for official opt-in Japanese JETRO bid RSS."""
import asyncio

import pytest

from app.sources.eis_rss import SourceError
from app.sources.jp_jetro_bid_rss import (
    JetroBidRssSource, RSS_URL, SOURCE_ID, parse_jetro_bid_rss,
)
from app.sources.opportunities import validate_notice

DETAIL = "https://www.jetro.go.jp/procurement/bid/adj/c0e1075bbfa85c33.html"


def rss(link=DETAIL, title="機器保守サービス業務の一般競争入札"):
    return (f'<?xml version="1.0" encoding="utf-8"?>'
            f'<rss version="2.0"><channel>'
            f'<item><title>{title}</title><link>{link}</link>'
            f'<pubDate>Thu, 15 Oct 2026 05:00:00 GMT</pubDate>'
            f'<description>一般競争入札の公告</description></item>'
            f'</channel></rss>').encode("utf-8")


def test_real_shaped_jetro_bid_notice_is_valid_and_stable():
    notice = parse_jetro_bid_rss(rss())[0]
    validate_notice(notice, SOURCE_ID)
    assert notice.url == DETAIL
    assert notice.customer == "Japan External Trade Organization (JETRO)"
    assert notice.region == "Japan"
    assert notice.deadline is None and notice.initial_price is None
    assert notice.external_id == parse_jetro_bid_rss(rss())[0].external_id


@pytest.mark.parametrize("url", [
    "http://evil.example/procurement/bid/adj/c0e1075bbfa85c33.html",
    "https://www.jetro.go.jp.evil.example/procurement/bid/adj/c0e1075bbfa85c33.html",
    "https://www.jetro.go.jp:8080/procurement/bid/adj/c0e1075bbfa85c33.html",
    "https://www.jetro.go.jp/procurement/bid/2026.html",
    "https://www.jetro.go.jp/procurement/bidtop",
    "https://www.jetro.go.jp/rss/news.xml",
    "https://www.jetro.go.jp/procurement/bid/adj/c0e1075bbfa85c33.html#hack",
])
def test_rejects_other_origins_and_non_detail_urls(url):
    with pytest.raises(SourceError, match="no verified"):
        parse_jetro_bid_rss(rss(link=url))


@pytest.mark.parametrize("title", [
    "入札結果のお知らせ", "落札者の決定", "Cancelled tender", "Contract Award",
])
def test_rejects_awards_results_and_cancellations(title):
    with pytest.raises(SourceError, match="no verified"):
        parse_jetro_bid_rss(rss(title=title))


def test_rejects_xml_bombs_non_feed_and_no_notices():
    for xml in (
        b'<!DOCTYPE foo [<!ENTITY x SYSTEM "file:///etc/passwd">]><rss/>',
        b"<html>news</html>",
        b"<rss><channel /></rss>",
        b"<rss",
        b"X" * (1024 * 1024 + 1),
    ):
        with pytest.raises(SourceError):
            parse_jetro_bid_rss(xml)


def test_http_legacy_link_is_only_upgraded_not_fetched():
    value = parse_jetro_bid_rss(rss(link=DETAIL.replace("https:", "http:")))[0]
    assert value.url == DETAIL


def test_network_contract_is_one_fixed_official_request(monkeypatch):
    calls = []

    async def fake_fetch(url, timeout, accept):
        calls.append((url, timeout, accept))
        return rss()

    monkeypatch.setattr("app.sources.jp_jetro_bid_rss._fetch", fake_fetch)
    result = asyncio.run(JetroBidRssSource().fetch(3))
    assert len(result) == 1
    assert calls == [(RSS_URL, 25.0, "application/rss+xml,application/xml,text/xml")]


def test_registry_is_separate_opt_in_and_six_hong_kong_keys_unchanged(monkeypatch):
    from scripts.asia_six_live_acceptance import settings
    from app.sources.catalog import build_source_catalog
    from app.sources.asia_public import ASIA_RSS_FEEDS

    monkeypatch.delenv("VALYQON_ASIA_JETRO_BID_ENABLED", raising=False)
    monkeypatch.setenv("VALYQON_ASIA_SOURCES_ENABLED", "1")
    assert SOURCE_ID not in build_source_catalog(settings()).registry.keys()
    assert len(ASIA_RSS_FEEDS) == 6
    monkeypatch.setenv("VALYQON_ASIA_JETRO_BID_ENABLED", "1")
    catalog = build_source_catalog(settings())
    assert SOURCE_ID in catalog.enabled_keys
    assert all(key in catalog.enabled_keys for key in ASIA_RSS_FEEDS)
