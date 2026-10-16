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
        yield Fake()
    import app.sources.gpb_etp_public as module
    monkeypatch.setattr(module, "source_client", source)
    notices = asyncio.run(GpbEtpPublicSource().fetch(1))
    assert len(notices) == 1
    assert requested == [LIST_URL, URL]
