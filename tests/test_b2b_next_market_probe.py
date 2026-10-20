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


@pytest.mark.parametrize("payload", [b"", b"z" * (2 * 1024 * 1024 + 1), bytes((255,))], ids=["empty", "oversize_2mib", "invalid_utf8"])
def test_offline_probe_fails_closed_on_unsafe_or_invalid_html(payload):
    with pytest.raises((ValueError, UnicodeDecodeError)):
        analyze_official_html(payload)


def test_route_with_query_is_diagnosed_but_not_accepted_as_verified_notice():
    html = b'<a href="/app/market-next/procedure/tender-4644426/?ref=untrusted">Tender</a>'
    evidence = analyze_official_html(html)
    assert evidence["native_path_candidates"] == 1
    assert evidence["native_path_candidates_with_query"] == 1
    assert evidence["first_party_native_detail_links"] == 0
    assert evidence["embedded_tender_id_markers"] == 1


def test_non_anchor_embedded_id_is_not_counted_as_verified_native_link():
    html = b'<script>var route="/app/market-next/slug/tender-4644426/";</script>'
    evidence = analyze_official_html(html)
    assert evidence["embedded_tender_id_markers"] == 1
    assert evidence["first_party_native_detail_links"] == 0


def test_live_shape_fixture_diagnostic_uses_production_ssr_parser_not_legacy_anchor_guess():
    from pathlib import Path
    fixture = (Path(__file__).parent / "fixtures" / "ru08" / "b2b_next_ssr.html").read_bytes()
    report = analyze_official_html(fixture)
    assert report["ssr_native_schema"] == "verified"
    assert report["ssr_verified_native_count"] == 2
    assert report["ssr_verified_native_count"] > report["first_party_native_detail_links"]
    assert not any("tender_url" in key or "notice_title" in key for key in report)


def test_diagnostic_cannot_count_syntactic_unverified_native_anchors():
    payload = b'<a href="/app/market-next/slug/tender-4644426/">Not a verified SSR card</a>'
    report = analyze_official_html(payload)
    assert report["first_party_native_detail_links"] == 1
    assert report["ssr_native_schema"] == "rejected"
    assert report["ssr_verified_native_count"] == 0
