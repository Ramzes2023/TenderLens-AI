"""Offline TEK-Torg public 223-FZ source contract; all fixtures synthetic."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.monitoring.config import MonitoringSettings
from app.sources.catalog import build_source_catalog
from app.sources.tektorg_public_html import (
    HOST, LIST_URL, SOURCE_ID, TekTorgPublicSource,
    parse_public_listing, validate_public_detail,
)
from app.scoring.runs import ScoringInputError, validate_configuration


def listing(title="Поставка стали", link="/223-fz/procedures/20000521"):
    return (f"<html><a href='{link}'><span>{title}</span></a></html>").encode()


def detail(title="Поставка стали", identity="20000521"):
    return (f"<html><title>Извещение о процедуре {identity}</title>"
            f"<h1><span>{title}</span></h1></html>").encode()


def settings(**changes):
    base = MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=10,
        max_notifications_per_cycle=5, request_timeout=15,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
    )
    return replace(base, **changes)


def test_default_disabled_and_source_scoring_selection():
    assert SOURCE_ID not in build_source_catalog(settings()).enabled_keys
    catalog = build_source_catalog(settings(tektorg_public_enabled=True))
    assert SOURCE_ID in catalog.enabled_keys
    assert catalog.registry.get(SOURCE_ID).metadata.official is False
    assert validate_configuration([SOURCE_ID], 10)["sources"] == [SOURCE_ID]


def test_public_listing_normalizes_id_and_title_with_real_path_shape():
    cards = parse_public_listing(listing())
    assert cards == [("20000521", f"https://{HOST}/223-fz/procedures/20000521",
                      "Поставка стали")]
    validate_public_detail(detail(), identity="20000521", title="Поставка стали")


@pytest.mark.parametrize("html", [
    b"",
    b"<html>No cards</html>",
    listing(link="https://www.tektorg.ru.evil.invalid/223-fz/procedures/20000521"),
    listing(link="https://www.tektorg.ru/223-fz/procedures/20000521?token=x"),
    listing(link="https://www.tektorg.ru/223-fz/procedures/20000521#fragment"),
    listing(link="http://www.tektorg.ru/223-fz/procedures/20000521"),
    listing(title=" "),
    listing(title="<script>alert(1)</script>"),
])
def test_incomplete_or_malformed_listing_fails_closed(html):
    with pytest.raises(ValueError):
        parse_public_listing(html)


def test_detail_requires_same_title_and_identity():
    for body in (detail(title="Другой тендер"),
                 detail(identity="20000522"),
                 b"<html><h1>Поставка стали</h1></html>"):
        with pytest.raises(ValueError):
            validate_public_detail(body, identity="20000521", title="Поставка стали")


def test_conflicting_duplicate_identity_fails_closed():
    body = listing() + listing(title="Иной товар")
    with pytest.raises(ValueError):
        parse_public_listing(body, limit=3)


def test_real_adapter_public_request_contract_offline(monkeypatch):
    seen = []
    class FakeClient:
        async def get(self, url):
            seen.append(url)
            content = listing() if url == LIST_URL else detail()
            return SimpleNamespace(
                content=content,
                headers={"content-type": "text/html; charset=utf-8"},
                raise_for_status=lambda: None,
            )
    @asynccontextmanager
    async def fake_source_client(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        assert kwargs["timeout"] == 15
        yield FakeClient()
    import app.sources.tektorg_public_html as module
    monkeypatch.setattr(module, "source_client", fake_source_client)
    notices = asyncio.run(TekTorgPublicSource(timeout=15).fetch(1))
    assert seen == [LIST_URL, f"https://{HOST}/223-fz/procedures/20000521"]
    assert len(notices) == 1
    assert notices[0].identity == (SOURCE_ID, "20000521")
    assert notices[0].title == "Поставка стали"


@pytest.mark.parametrize("limit", [0, True, 101, "5"])
def test_invalid_limit_rejected(limit):
    with pytest.raises(ValueError):
        asyncio.run(TekTorgPublicSource().fetch(limit))
