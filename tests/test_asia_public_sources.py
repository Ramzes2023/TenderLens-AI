"""Strict, network-free tests for six staged Asian procurement adapters."""
import asyncio

import pytest

from app.monitoring.config import MonitoringSettings
from app.sources.asia_public import (
    ASIA_RSS_FEEDS, JETRO_LISTS, AsiaPublicSource,
    parse_asia_rss, parse_jetro_html,
)
from app.sources.catalog import build_source_catalog
from app.sources.eis_rss import SourceError
from app.sources.ingestion import HOSTS, validate_payload, connector_version
from app.sources.opportunities import validate_notice
from app.jobs.worker import PermanentJobError


RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<title>Tender notices</title>
<item><title> Public contract for engineering services </title>
<link>https://www.housingauthority.gov.hk/en/tenders/example-123.html</link>
<guid>hk-123</guid><pubDate>Thu, 15 Oct 2026 08:00:00 +0800</pubDate>
<description>Engineering tender</description></item>
</channel></rss>"""

JETRO = b"""<html><table>
<tr><th>Publishing date</th><th>Procurement entity</th><th>Type</th><th>Title</th></tr>
<tr><td>Oct 15, 2026</td><td>Ministry of Finance</td>
<td>Notice of Procurement (Goods &amp; Services)</td>
<td><a href="/en/database/procurement/national/articles/420001/2026101500010000.html">
Procurement of a secure IT system, 1 set</a></td></tr>
</table></html>"""


def _settings():
    return MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=20,
        max_notifications_per_cycle=5, request_timeout=15.0,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
        profile_feed_limit=5,
    )


def test_important_sources_remain_disabled_by_default(monkeypatch):
    monkeypatch.delenv("VALYQON_ASIA_SOURCES_ENABLED", raising=False)
    catalog = build_source_catalog(_settings())
    assert all(key not in catalog.registry.keys()
               for key in (*ASIA_RSS_FEEDS, *JETRO_LISTS))


def test_exact_six_sources_opt_in_to_existing_catalog_and_worker(monkeypatch):
    monkeypatch.setenv("VALYQON_ASIA_SOURCES_ENABLED", "1")
    catalog = build_source_catalog(_settings())
    assert set((*ASIA_RSS_FEEDS, *JETRO_LISTS)) <= set(catalog.enabled_keys)
    for key in (*ASIA_RSS_FEEDS, *JETRO_LISTS):
        registration = catalog.registry.get(key)
        assert registration.official is True
        assert registration.jurisdictions == (("HK",) if key.startswith("hk_") else ("JP",))
        assert registration.source.name == key
        assert key in HOSTS
        assert len(HOSTS[key]) == 1
        assert connector_version(key) == f"connector-sync-v1:{key}:adapter-r1"


def test_hong_kong_feed_has_real_tender_fields():
    notice = parse_asia_rss(RSS, source="hk_ha_works")[0]
    assert notice.source == "hk_ha_works"
    assert notice.title == "Public contract for engineering services"
    assert notice.published_at == "2026-10-15T08:00:00+08:00"
    assert notice.deadline is None
    assert notice.initial_price is None
    validate_notice(notice, "hk_ha_works")
    assert parse_asia_rss(RSS, source="hk_ha_works")[0].identity == notice.identity


@pytest.mark.parametrize("url", [
    "http://evil.example/en/notice",
    "https://evil.example/notice",
    "https://www.housingauthority.gov.hk.evil.example/tender",
    "https://www.housingauthority.gov.hk:444/tenders/a",
    "https://secret@www.housingauthority.gov.hk/tenders/a",
    "https://127.0.0.1/tenders/a",
    "file:///etc/passwd",
])
def test_rss_rejects_unsafe_item_url_without_persisting(url):
    payload = RSS.replace(b"https://www.housingauthority.gov.hk/en/tenders/example-123.html", url.encode())
    with pytest.raises(SourceError, match="no verifiable"):
        parse_asia_rss(payload, source="hk_ha_works")


def test_official_legacy_http_notice_links_upgrade_to_https():
    legacy = RSS.replace(
        b"https://www.housingauthority.gov.hk/en/tenders/example-123.html",
        b"http://www.housingauthority.gov.hk/en/tenders/example-123.html",
    )
    notice = parse_asia_rss(legacy, source="hk_ha_works")[0]
    assert notice.url == "https://www.housingauthority.gov.hk/en/tenders/example-123.html"
    validate_notice(notice, "hk_ha_works")


def test_official_relative_notice_link_is_resolved_against_feed():
    relative = RSS.replace(
        b"https://www.housingauthority.gov.hk/en/tenders/example-123.html",
        b"/en/tenders/example-123.html",
    )
    notice = parse_asia_rss(relative, source="hk_ha_works")[0]
    assert notice.url == "https://www.housingauthority.gov.hk/en/tenders/example-123.html"


@pytest.mark.parametrize("url", [
    "http://www.housingauthority.gov.hk.evil.example/en/tenders/item",
    "http://username@www.housingauthority.gov.hk/en/tenders/item",
    "http://www.housingauthority.gov.hk:80/en/tenders/item",
    "https://www.housingauthority.gov.hk/en/tenders/item#injected",
    "//evil.example/en/tenders/item",
    "/en/tenders/item\\evil",
    "https://www.housingauthority.gov.hk/en/tenders/item%0Aevil",
])
def test_rss_unsafe_notice_hosts_and_link_syntax_fail_closed(url):
    xml = RSS.replace(
        b"https://www.housingauthority.gov.hk/en/tenders/example-123.html",
        url.encode(),
    )
    with pytest.raises(SourceError):
        parse_asia_rss(xml, source="hk_ha_works")


def test_rss_fails_closed_on_markup_entity_and_empty_entries():
    for payload in (b"<html>Access denied</html>", b'<rss><channel></channel></rss>',
                    b'<!DOCTYPE rss [<!ENTITY x "secret">]><rss/>', b"<rss"):
        with pytest.raises(SourceError):
            parse_asia_rss(payload, source="hk_ha_works")


def test_standard_rss1_rdf_notice_parses_with_utc_timestamp():
    payload = b"""<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
 xmlns="http://purl.org/rss/1.0/"
 xmlns:dc="http://purl.org/dc/elements/1.1/">
 <item rdf:about="https://www.emsd.gov.hk/en/tender/123">
  <title>Public ventilation maintenance services</title>
  <link>https://www.emsd.gov.hk/en/tender/123</link>
  <dc:date>2026-10-15T08:00:00Z</dc:date>
  <description>Invitation to tender</description>
 </item>
</rdf:RDF>"""
    notice = parse_asia_rss(payload, source="hk_emsd_tenders")[0]
    assert notice.published_at == "2026-10-15T08:00:00+00:00"
    assert notice.source == "hk_emsd_tenders"
    validate_notice(notice, notice.source)


def test_atom_updated_timestamp_and_safe_relative_link():
    payload = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>tag:emsd.gov.hk,2026:abc123</id>
    <title>Public servicing of ventilation systems</title>
    <link href="/en/tender/notices/abc123" rel="alternate"/>
    <updated>2026-10-15T08:00:00+08:00</updated>
    <summary>Annual servicing procurement</summary>
  </entry>
</feed>"""
    notice = parse_asia_rss(payload, source="hk_emsd_tenders")[0]
    assert notice.published_at == "2026-10-15T08:00:00+08:00"
    assert notice.url == "https://www.emsd.gov.hk/en/tender/notices/abc123"
    validate_notice(notice, notice.source)


def test_asia_diagnostic_does_not_log_untrusted_html(monkeypatch):
    from app.sources import asia_public
    from scripts import asia_six_upstream_diagnostic as diag

    async def fake_fetch(*args):
        return b'<html><table><tr><td>PRIVATE-UNTRUSTED-PAGE</td></tr></table></html>'

    monkeypatch.setattr(diag, "_fetch", fake_fetch)
    result = asyncio.run(diag._one(
        "jp_jetro_national", asia_public.JETRO_LISTS["jp_jetro_national"],
    ))
    assert result["stage"] == "HTML_VALID_BUT_NO_QUALIFIED_NOTICES"
    assert "PRIVATE-UNTRUSTED-PAGE" not in repr(result)
    assert result["records"] == 0


def test_asia_diagnostic_classifies_safe_http_error(monkeypatch):
    from scripts import asia_six_upstream_diagnostic as diag

    async def fake_fetch(*args):
        raise SourceError("Asian procurement upstream HTTP 403.")

    monkeypatch.setattr(diag, "_fetch", fake_fetch)
    result = asyncio.run(diag._one(
        "hk_ha_works", ASIA_RSS_FEEDS["hk_ha_works"],
    ))
    assert result["stage"] == "UPSTREAM_HTTP_403"
    assert result["response_bytes"] == 0


def test_jetro_national_link_and_date_retain_no_fabricated_deadline():
    notice = parse_jetro_html(JETRO, source="jp_jetro_national")[0]
    validate_notice(notice, "jp_jetro_national")
    assert notice.external_id == "420001:2026101500010000"
    assert notice.published_at == "2026-10-15"
    assert notice.customer == "Ministry of Finance"
    assert notice.deadline is None


def test_awards_and_noncompetitive_jetro_notices_do_not_create_tenders():
    award = RSS.replace(b"Public contract for engineering services",
                        b"Contract Award for engineering services")
    with pytest.raises(SourceError, match="no verifiable"):
        parse_asia_rss(award, source="hk_ha_leasing")
    comment = JETRO.replace(
        b"Notice of Procurement (Goods &amp; Services)",
        b"Notice of request for comments",
    )
    with pytest.raises(SourceError, match="no verifiable"):
        parse_jetro_html(comment, source="jp_jetro_national")


def test_jetro_local_is_separate_feed_and_rejects_national_rows():
    with pytest.raises(SourceError, match="no verifiable"):
        parse_jetro_html(JETRO, source="jp_jetro_local")
    local = JETRO.replace(b"/national/articles/", b"/local/articles/")
    assert parse_jetro_html(local, source="jp_jetro_local")[0].source == "jp_jetro_local"


def test_jetro_disallows_other_host_and_unrelated_non_tender_links():
    bad = JETRO.replace(
        b"/en/database/procurement/national/articles/420001/2026101500010000.html",
        b"https://evil.example/en/database/procurement/national/articles/420001/2026101500010000.html",
    )
    with pytest.raises(SourceError, match="no verifiable"):
        parse_jetro_html(bad, source="jp_jetro_national")


def test_all_six_sources_fetch_through_safe_single_page_transport(monkeypatch):
    calls = []
    async def fake_fetch(url, timeout, accept):
        calls.append((url, timeout, accept))
        if url in ASIA_RSS_FEEDS.values():
            payload = RSS.replace(
                b"www.housingauthority.gov.hk/en/tenders/example-123.html",
                (b"www.emsd.gov.hk/en/tenders/example-123.html"
                 if "emsd" in url else b"www.housingauthority.gov.hk/en/tenders/example-123.html"))
            return payload
        section = b"local" if "local" in url else b"national"
        return JETRO.replace(b"/national/articles/", b"/" + section + b"/articles/")

    monkeypatch.setattr("app.sources.asia_public._fetch", fake_fetch)
    async def run():
        results = []
        for key in (*ASIA_RSS_FEEDS, *JETRO_LISTS):
            notices = await AsiaPublicSource(key).fetch(limit=5)
            assert notices and notices[0].source == key
            validate_notice(notices[0], key)
            results.extend(notices)
        return results
    notices = asyncio.run(run())
    assert len(notices) == 6
    assert len(calls) == 6
    assert all(timeout == 30.0 for _, timeout, _ in calls)


def test_six_source_catalog_connects_to_real_worker_and_sqlite(monkeypatch, tmp_path):
    """Exercise the actual connector queue, worker handler and snapshot search.

    HTTP is fixture-backed in this test; this is *not* a live network claim.
    """
    from app.database.backend import Database
    from app.database.config import DatabaseSettings
    from app.jobs import HandlerRegistry, JobRepository, JobService
    from app.jobs.worker import Worker
    from app.sources.ingestion import JOB_TYPE, ConnectorSyncHandler, ConnectorSyncService
    from app.sources.opportunities import OpportunityRepository
    from app.sources.snapshots import snapshot_catalog

    monkeypatch.setenv("VALYQON_ASIA_SOURCES_ENABLED", "1")

    async def fake_fetch(url, timeout, accept):
        assert url == ASIA_RSS_FEEDS["hk_emsd_consultancy"]
        return RSS.replace(
            b"www.housingauthority.gov.hk/en/tenders/example-123.html",
            b"www.emsd.gov.hk/en/tenders/example-123.html",
        )

    monkeypatch.setattr("app.sources.asia_public._fetch", fake_fetch)
    db = Database(DatabaseSettings("", tmp_path / "asia-worker.sqlite"))
    try:
        jobs = JobRepository(db)
        jobs.initialize()
        opportunities = OpportunityRepository(db)
        opportunities.initialize()
        catalog = build_source_catalog(_settings())
        source = "hk_emsd_consultancy"
        service = ConnectorSyncService(JobService(jobs), catalog)
        handlers = HandlerRegistry()
        handlers.register(JOB_TYPE, ConnectorSyncHandler(catalog, opportunities))
        service.enqueue(source)
        assert Worker(jobs, handlers, job_types=(JOB_TYPE,)).run_once() is True
        stored = opportunities.read(source, search_terms=("engineering",))
        assert len(stored) == 1
        assert stored[0].source == source
        assert stored[0].title == "Public contract for engineering services"
        report = asyncio.run(snapshot_catalog(catalog, opportunities).fetch(
            source_keys=(source,), search_terms=("engineering",)
        ))
        assert not report.failures
        assert len(report.notices) == 1
        assert report.notices[0].identity == stored[0].identity
    finally:
        db.close()


def test_jetro_fallback_performs_only_two_fixed_official_requests(monkeypatch):
    from app.sources.asia_public import JETRO_SEARCH_URLS
    calls = []

    async def fake_fetch(url, timeout, accept):
        calls.append(url)
        assert timeout == 30.0
        assert accept == "text/html"
        if len(calls) == 1:
            return b"<html><table></table></html>"
        return JETRO

    monkeypatch.setattr("app.sources.asia_public._fetch", fake_fetch)
    notices = asyncio.run(AsiaPublicSource("jp_jetro_national").fetch(5))
    assert len(notices) == 1
    assert calls == [
        JETRO_LISTS["jp_jetro_national"],
        JETRO_SEARCH_URLS["jp_jetro_national"],
    ]
    validate_notice(notices[0], "jp_jetro_national")


def test_jetro_fallback_fails_closed_when_both_queries_are_empty(monkeypatch):
    from app.sources.asia_public import JETRO_SEARCH_URLS
    calls = []

    async def fake_fetch(url, timeout, accept):
        calls.append(url)
        return b"<html><body>no procurement notices</body></html>"

    monkeypatch.setattr("app.sources.asia_public._fetch", fake_fetch)
    with pytest.raises(SourceError, match="no verifiable"):
        asyncio.run(AsiaPublicSource("jp_jetro_local").fetch(5))
    assert calls == [JETRO_LISTS["jp_jetro_local"],
                     JETRO_SEARCH_URLS["jp_jetro_local"]]


def test_bounded_timeout_and_unknown_source_fail_closed():
    with pytest.raises(ValueError):
        AsiaPublicSource("private_webhook")
    with pytest.raises(ValueError):
        AsiaPublicSource("jp_jetro_local", timeout=-2)
