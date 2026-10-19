"""Offline source-origin and malformed-link checks; NOT real B2B evidence."""
import pytest

from scripts.diagnose_ru_b2b_next_market import analyze_official_html, NEXT_MARKET_URL


def test_genuine_next_market_url_is_first_party_pinned_https():
    assert NEXT_MARKET_URL == "https://www.b2b-center.ru/app/next/market-search/?from=0"


def test_original_native_detail_paths_only_and_never_foreign_or_malformed():
    html = b"""<html><a href="/app/market-next/real-thing/tender-4644426/">First</a>
<a href="https://www.b2b-center.ru/app/market-next/another/tender-4644396/">Second</a>
<a href="https://outside.example/app/market-next/another/tender-4644396/">Foreign</a>
<a href="//outside.example/app/market-next/fake/tender-4644111/">Foreign</a>
<a href="/app/market-next/invalid/tender-4/?key=1">Query</a>
<a href="/search/number/12345/">Legacy</a>
<a href="/app/market-next/real-thing/tender-4644426/">Duplicate</a></html>"""
    report = analyze_official_html(html)
    assert report["first_party_native_detail_links"] == 2
    assert report["anchor_count"] == 7


@pytest.mark.parametrize("payload", [b"", b"z" * (2 * 1024 * 1024 + 1), bytes((255,))])
def test_offline_probe_fails_closed_on_unsafe_or_invalid_html(payload):
    with pytest.raises((ValueError, UnicodeDecodeError)):
        analyze_official_html(payload)
