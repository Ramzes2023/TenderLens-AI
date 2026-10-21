"""Offline strict public Gazprombank procurement source contracts."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.monitoring.config import MonitoringSettings
from app.sources.catalog import build_source_catalog
from app.sources.gpb_etp_public import (
    GpbEtpPublicSource, HOST, LIST_URL, parse_gpb_public_links,
    parse_gpb_verified_detail,
)

URL = "https://etpgpb.ru/procedures/etp/1299761-postavka-oborudovaniya/"
TITLE = "Поставка оборудования по техническому заданию"


def listing(url=URL):
    return f"<html><a href='{url}'>Закупка</a></html>".encode("utf-8")


def detail(identity="1299761", title=TITLE):
    return f"<html><title>Процедура {identity}</title><h1>{title}</h1></html>".encode("utf-8")


def settings(enabled=False):
    return MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=10,
        max_notifications_per_cycle=5, request_timeout=15,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
        gpb_etp_public_enabled=enabled,
    )


def test_gpb_disabled_by_default_and_explicit_opt_in():
    assert "gpb_etp_public" not in build_source_catalog(settings()).enabled_keys
    assert "gpb_etp_public" in build_source_catalog(settings(True)).enabled_keys


def test_observed_numeric_only_gpb_firstparty_route_without_synthetic_slug():
    original = "https://etpgpb.ru/procedures/etp/1240053/"
    assert parse_gpb_public_links(listing(original)) == [("1240053", original)]
    notice = parse_gpb_verified_detail(detail("1240053"), "1240053", original)
    assert notice.external_id == "1240053"
    assert notice.url == original
    for bad in (
        "https://etpgpb.ru/procedures/etp/1240053/?access_token=hidden",
        "https://etpgpb.ru/procedures/etp/1240053.evil/",
        "https://etpgpb.ru.evil.example/procedures/etp/1240053/",
    ):
        with pytest.raises(ValueError):
            parse_gpb_public_links(listing(bad))


def test_exact_public_notice_and_independent_title():
    assert parse_gpb_public_links(listing()) == [("1299761", URL)]
    notice = parse_gpb_verified_detail(detail(), "1299761", URL)
    assert notice.identity == ("gpb_etp_public", "1299761")
    assert notice.title == TITLE
    assert notice.url == URL
    assert notice.deadline is None


@pytest.mark.parametrize("bad", [
    b"", b"<html>No notices</html>",
    listing("https://etpgpb.ru.evil.invalid/procedures/etp/1299761-x/"),
    listing("http://etpgpb.ru/procedures/etp/1299761-x/"),
    listing("https://etpgpb.ru/procedures/etp/1299761-x/?token=x"),
    listing("https://etpgpb.ru/procedures/etp/1299761-x/#fragment"),
])
def test_bad_public_listing_fails_closed(bad):
    with pytest.raises(ValueError):
        parse_gpb_public_links(bad)


@pytest.mark.parametrize("bad", [
    detail(identity="2222222"),
    detail(title=""),
    b"<html>No heading</html>",
])
def test_bad_detail_identity_and_heading_fails_closed(bad):
    with pytest.raises(ValueError):
        parse_gpb_verified_detail(bad, "1299761", URL)


def test_exact_public_transport_and_bounded_requests(monkeypatch):
    requested = []
    class Fake:
        async def get(self, url):
            requested.append(url)
            return SimpleNamespace(
                content=listing() if url == LIST_URL else detail(),
                headers={"content-type": "text/html;charset=utf-8"},
                raise_for_status=lambda: None,
            )
    @asynccontextmanager
    async def source(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        assert kwargs["headers"]["User-Agent"] == "Mozilla/5.0"
        assert kwargs["headers"]["Accept"] == "text/html"
        yield Fake()
    import app.sources.gpb_etp_public as module
    monkeypatch.setattr(module, "source_client", source)
    notices = asyncio.run(GpbEtpPublicSource().fetch(1))
    assert len(notices) == 1
    assert requested == [LIST_URL, URL]


def test_real_job_fence_and_sqlite_roundtrip_with_offline_source(monkeypatch):
    """Synthetic notice exercises real JobRepository lease and Worker, not live network."""
    async def fixture_fetch(self, limit=20):
        return [parse_gpb_verified_detail(detail(), "1299761", URL)]

    monkeypatch.setattr(GpbEtpPublicSource, "fetch", fixture_fetch)
    from scripts.ci_ru_gpb_public_worker import proof
    evidence = proof()
    assert evidence["real_detail_verified"] == 1
    assert evidence["worker_inserted"] == 1
    assert evidence["sqlite_search_verified"] == 1
    assert evidence["idempotent_replay"]


def test_bounded_public_gpb_skips_stale_original_and_returns_next_verified(monkeypatch):
    """Never allow one deleted/stale first-party card to starve a current feed.

    This is a MockTransport-style offline test, not live acceptance.
    """
    candidates = [
        f"https://{HOST}/procedures/etp/123450{i}-procedure/"
        for i in (1, 2, 3, 4)
    ]
    raw_index = "<html>" + "".join(
        f"<a href='{url}'>First-party procedure</a>"
        for url in candidates
    ) + "</html>"
    seen = []

    class Reply:
        def __init__(self, payload):
            self.content = payload
            self.headers = {"content-type": "text/html"}
        def raise_for_status(self):
            return None

    class Fake:
        async def get(self, url):
            seen.append(url)
            if url == LIST_URL:
                return Reply(raw_index.encode("utf-8"))
            if url == candidates[0]:
                # Rejected: H1 present but no independently visible ID.
                return Reply(b"<html><h1>Deleted</h1></html>")
            if url == candidates[1]:
                return Reply(detail("1234502"))
            raise AssertionError("Unbounded extra GPB request")

    @asynccontextmanager
    async def client(**kwargs):
        assert kwargs["follow_redirects"] is False
        assert kwargs["trust_env"] is False
        yield Fake()

    import app.sources.gpb_etp_public as mod
    monkeypatch.setattr(mod, "source_client", client)
    received = asyncio.run(GpbEtpPublicSource().fetch(1))
    assert len(received) == 1
    assert received[0].external_id == "1234502"
    assert received[0].url == candidates[1]
    assert seen == [LIST_URL, candidates[0], candidates[1]]

