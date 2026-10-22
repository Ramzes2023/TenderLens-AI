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


if __name__ == "__main__":
    unittest.main()


def test_live_index_can_keep_verified_az_notice_when_one_detail_is_stale(monkeypatch):
    """Offline: never seed fake success; valid first-party detail still required."""
    import asyncio
    from contextlib import asynccontextmanager
    import httpx
    import app.sources.az_azeristilik as source

    second = "https://azeristilik.gov.az/post/obsolete-procurement-announcement-2026"
    index = ("<html><a href='" + URL + "'>" + TITLE +
             "</a><a href='" + second + "'>" +
             "Təchizat xidməti satınalınmasına dair tender elan edir" +
             "</a></html>")
    seen = []

    def respond(request):
        url = str(request.url)
        seen.append(url)
        if url == INDEX_URL:
            return httpx.Response(200, text=index, headers={"content-type": "text/html"})
        if url == URL:
            return httpx.Response(200, text=detail(), headers={"content-type": "text/html"})
        if url == second:
            return httpx.Response(404)
        raise AssertionError("Unapproved source URL")

    @asynccontextmanager
    async def offline_client(**kwargs):
        assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond), **kwargs) as client:
            yield client

    monkeypatch.setattr(source, "source_client", offline_client)
    verified = asyncio.run(source.AzerbaijanHeatSource().fetch(limit=2))
    assert len(verified) == 1
    assert verified[0].url == URL
    assert verified[0].customer == "Azəristiliktəchizat ASC"
    assert seen == [INDEX_URL, URL, second]


def test_no_az_detail_verification_never_becomes_success(monkeypatch):
    """Even all-404 current cards cannot yield an invented source result."""
    import asyncio
    from contextlib import asynccontextmanager
    import httpx
    import pytest
    import app.sources.az_azeristilik as source

    def respond(request):
        if str(request.url) == INDEX_URL:
            return httpx.Response(200, text=listing(), headers={"content-type": "text/html"})
        return httpx.Response(404)

    @asynccontextmanager
    async def offline_client(**kwargs):
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond), **kwargs) as client:
            yield client

    monkeypatch.setattr(source, "source_client", offline_client)
    with pytest.raises(SourceError, match="complete notice batch empty"):
        asyncio.run(source.AzerbaijanHeatSource().fetch(limit=1))
