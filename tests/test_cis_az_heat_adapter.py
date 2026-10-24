"""Strict offline contracts of the verified AZ public state-agency adapter.

Fixtures do NOT prove upstream availability: CI must separately run live
official list, detail, leased worker, SQLite storage, and real saved search.
"""
import unittest

from app.monitoring.config import MonitoringSettings
from app.sources.catalog import build_source_catalog
from app.sources.eis_rss import SourceError
from app.sources.ingestion import HOSTS
from app.sources.az_azeristilik import (
    AzerbaijanHeatSource, INDEX_URL, MAX_DETAILS, SOURCE,
    approved_detail_url, discover_official_posts, parse_public_detail,
)

TITLE = "İş yerlərinin attestasiyasının keçirilməsi xidmətinin satınalınmasına dair kotirovka sorğusu elan edir"
URL = "https://azeristilik.gov.az/post/is-yerlerinin-attestasiyasinin-kecirilmesi-xidmetinin-satinalinmasina-dair-kotirovka-sorgusu-elan-edir"


def listing():
    return (
        '<html><script><a href="/post/fake-procurement-notice">Fake satınalınmasına</a></script>'
        '<a href="/post/is-yerlerinin-attestasiyasinin-kecirilmesi-xidmetinin-satinalinmasina-dair-kotirovka-sorgusu-elan-edir">'
        + TITLE + '</a><a href="https://evil.example/post/fake-procurement-notice">Untrusted satınalınmasına</a></html>'
    )


def detail(deadline="22.10.2026", buyer=True, listed_title=TITLE):
    return (
        "<main><h1>" + listed_title + "</h1>"
        + ('<div>Satınalan təşkilatın adı: "Azəristiliktəchizat" ASC</div>' if buyer else
           "<div>Satınalan təşkilatın adı: OTHER</div>")
        + '<table><tr><td>Müsabiqənin başlanma tarixi və vaxtı:</td><td>07.10.2026</td></tr>'
        + '<tr><td>Təkliflərin son təqdim olunma tarixi və vaxtı:</td><td>' + deadline + '</td></tr>'
        + '<tr><td>Müsabiqədə iştirak haqqı: 43,86 AZN</td></tr></table></main>'
    )


class AZHeatContracts(unittest.TestCase):
    def test_real_public_shape_without_mislabeling_participation_fee(self):
        notice = parse_public_detail(detail(), url=URL, listed_title=TITLE)
        self.assertEqual(notice.source, SOURCE)
        self.assertEqual(notice.url, URL)
        self.assertEqual(notice.external_id, URL.rsplit("/", 1)[-1])
        self.assertEqual(notice.title, TITLE)
        self.assertEqual(notice.customer, "Azəristiliktəchizat ASC")
        self.assertEqual(notice.published_at, "2026-10-07")
        self.assertEqual(notice.deadline, "2026-10-22")
        self.assertIsNone(notice.initial_price)
        self.assertIsNone(notice.currency)

    def test_only_same_origin_visible_listing_titles(self):
        self.assertEqual(discover_official_posts(listing()), ((URL, TITLE),))
        with self.assertRaises(SourceError):
            discover_official_posts("<html><script><a href='" + URL + "'>" + TITLE + "</a></script></html>")

    def test_buyer_title_dates_and_origin_fail_closed(self):
        for bad_html in (
            detail(buyer=False),
            detail(deadline="01.10.2026"),
            detail(deadline="22.19.2026"),
            detail(listed_title="Completely different procurement heading"),
            "<html>Loading...</html>",
        ):
            with self.subTest(html=bad_html[:60]), self.assertRaises(SourceError):
                parse_public_detail(bad_html, url=URL, listed_title=TITLE)
        for bad_url in (
            "http://azeristilik.gov.az/post/test-procurement-notice",
            "https://other.example/post/test-procurement-notice",
            URL + "?access_token=fake",
            "https://evil.example@" + URL.removeprefix("https://"),
        ):
            with self.subTest(url=bad_url), self.assertRaises(SourceError):
                parse_public_detail(detail(), url=bad_url, listed_title=TITLE)

    def test_official_agency_registered_disabled_and_bounded(self):
        settings = MonitoringSettings(False, 600, 20, 5, 12, (), None)
        r = build_source_catalog(settings).registry.get(SOURCE)
        self.assertFalse(r.enabled)
        self.assertTrue(r.official)
        self.assertEqual(r.jurisdictions, ("AZ",))
        self.assertEqual(r.homepage_url, INDEX_URL)
        self.assertEqual(HOSTS[SOURCE], frozenset({"azeristilik.gov.az"}))
        self.assertEqual(MAX_DETAILS, 5)
        self.assertEqual(AzerbaijanHeatSource().name, SOURCE)



def test_one_unreachable_post_does_not_discard_other_verified_official_notice(monkeypatch):
    import asyncio
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    import httpx
    import app.sources.az_azeristilik as adapter

    other = "https://azeristilik.gov.az/post/diger-satinalinmasina-dair-tender-elani"
    index = (
        '<html><a href="' + URL + '">' + TITLE + '</a>'
        '<a href="' + other + '">Digər satınalınmasına dair tender elanı</a></html>'
    )
    seen = []

    class FakeClient:
        async def get(self, url, **kwargs):
            seen.append(url)
            if url == INDEX_URL:
                return SimpleNamespace(
                    text=index, headers={"content-type": "text/html"},
                    raise_for_status=lambda: None)
            if url == URL:
                return SimpleNamespace(
                    text=detail(), headers={"content-type": "text/html"},
                    raise_for_status=lambda: None)
            if url == other:
                raise httpx.ReadTimeout("simulated single stale details")
            raise AssertionError("Unexpected request")

    @asynccontextmanager
    async def fake_client(**kwargs):
        assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        yield FakeClient()

    monkeypatch.setattr(adapter, "source_client", fake_client)
    items = asyncio.run(AzerbaijanHeatSource().fetch(5))
    assert len(items) == 1 and items[0].url == URL
    assert seen == [INDEX_URL, URL, other]


def test_all_unreachable_details_remain_live_source_failure(monkeypatch):
    import asyncio
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    import httpx
    import app.sources.az_azeristilik as adapter
    from app.sources.transport_errors import SourceTransportError

    class FakeClient:
        async def get(self, url, **kwargs):
            if url == INDEX_URL:
                return SimpleNamespace(text=listing(), headers={"content-type": "text/html"},
                                       raise_for_status=lambda: None)
            raise httpx.ReadTimeout("simulated inaccessible detail")

    @asynccontextmanager
    async def fake_client(**kwargs):
        yield FakeClient()

    monkeypatch.setattr(adapter, "source_client", fake_client)
    with __import__("pytest").raises(SourceTransportError):
        asyncio.run(AzerbaijanHeatSource().fetch(5))


def test_official_second_locale_index_only_after_network_failure(monkeypatch):
    import asyncio
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    import httpx
    import app.sources.az_azeristilik as adapter
    from app.sources.az_azeristilik import INDEX_FALLBACK_URL

    seen = []

    class Client:
        async def get(self, url, **kwargs):
            seen.append(url)
            if url == INDEX_URL:
                raise httpx.ConnectError("simulated first public locale down")
            if url == INDEX_FALLBACK_URL:
                return SimpleNamespace(
                    text=listing(), headers={"content-type": "text/html"},
                    raise_for_status=lambda: None)
            if url == URL:
                return SimpleNamespace(
                    text=detail(), headers={"content-type": "text/html"},
                    raise_for_status=lambda: None)
            raise AssertionError("Unexpected or untrusted URL")

    @asynccontextmanager
    async def fake_client(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        yield Client()

    monkeypatch.setattr(adapter, "source_client", fake_client)
    result = asyncio.run(AzerbaijanHeatSource().fetch(1))
    assert len(result) == 1 and result[0].url == URL
    assert seen == [INDEX_URL, INDEX_FALLBACK_URL, URL]


def test_official_language_fallback_does_not_create_fake_success(monkeypatch):
    import asyncio
    from contextlib import asynccontextmanager
    import httpx
    import pytest
    import app.sources.az_azeristilik as adapter
    from app.sources.transport_errors import SourceTransportError

    class Client:
        async def get(self, url, **kwargs):
            raise httpx.ReadTimeout("simulated full host outage")

    @asynccontextmanager
    async def fake_client(**kwargs):
        yield Client()

    monkeypatch.setattr(adapter, "source_client", fake_client)
    with pytest.raises(SourceTransportError):
        asyncio.run(AzerbaijanHeatSource().fetch(1))


def test_worker_safe_stage_diagnostic_only_uses_hardcoded_error_codes():
    from app.jobs.worker import PermanentJobError, RetryableJobError
    from scripts.ci_cis_az_heat_live_acceptance import _safe_worker_source_stage

    assert _safe_worker_source_stage(
        PermanentJobError("Invalid connector storage data.")
    ) == "SQL_INTEGRITY_REJECTED"
    assert _safe_worker_source_stage(
        PermanentJobError("Connector schema/configuration failed.")
    ) == "SOURCE_SCHEMA_OR_CONFIG_FAILED"
    assert _safe_worker_source_stage(
        RetryableJobError("Connector unavailable.")
    ) == "OFFICIAL_TRANSPORT_UNAVAILABLE"
    assert _safe_worker_source_stage(
        PermanentJobError("private upstream detail token=X")
    ) == "UNKNOWN"
    assert _safe_worker_source_stage(ValueError("secret")) == "UNKNOWN"


if __name__ == "__main__":
    unittest.main()
