"""Synthetic Lenobl procurement HTML contracts, never reported as live proof."""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.sources.lenobl_small_public import (
    HOST, LIST_URL, LenoblSmallPublicSource, parse_lenobl_detail, parse_lenobl_listing,
)

IDENT = "35217482"
URL = "https://" + HOST + "/ProductRequestGroup/Index/" + IDENT
TITLE = "Поставка компьютерной техники и расходных материалов"


def listing(link=URL, title=TITLE):
    return (f"<html><main><a href='{link}'><span>{title}</span></a>"
            "</main></html>").encode("utf-8")


def detail(number=IDENT, title="Закупка: поставка компьютерной техники и расходных материалов"):
    return (f"<html><body><h1>{title}</h1>"
            f"<div>Группа закупок № {number}</div></body></html>").encode("utf-8")


def test_real_shape_normalizes_canonical_original_url_without_made_up_number():
    assert parse_lenobl_listing(listing()) == [(IDENT, URL, TITLE)]
    item = parse_lenobl_detail(detail(), identity=IDENT, url=URL, listing_title=TITLE)
    assert item.identity == ("lenobl_small_public", IDENT)
    assert item.url == URL
    assert item.tender_number is None
    assert item.deadline is None
    assert "компьютерной техники" in item.title


@pytest.mark.parametrize("bad", [
    b"", b"<html>no procedures</html>",
    listing(link="http://" + HOST + "/ProductRequestGroup/Index/" + IDENT),
    listing(link="https://" + HOST + ".invalid/ProductRequestGroup/Index/" + IDENT),
    listing(link=URL + "?token=secret"),
    listing(link=URL + "#fragment"),
    listing(link=URL + "/other"),
    listing(link="https://different.example/ProductRequestGroup/Index/" + IDENT),
    listing(title=""),
    listing(title="<script>unsafe</script>"),
])
def test_listing_rejects_invalid_or_external_card(bad):
    with pytest.raises(ValueError):
        parse_lenobl_listing(bad)


@pytest.mark.parametrize("body", [
    detail(number="35217483"),
    " <html><script>35217482</script><h1>Поставка компьютерной техники и расходных материалов</h1></html>".strip().encode("utf-8"),
    detail(title="Совершенно другой предмет закупки"),
    "<html>Группа 35217482, но нет заголовка</html>".encode("utf-8"),
    b"",
])
def test_independent_detail_required(body):
    with pytest.raises(ValueError):
        parse_lenobl_detail(body, identity=IDENT, url=URL, listing_title=TITLE)


def test_conflicting_listing_identity_rejected():
    data = listing() + listing(link=URL + "/", title="Другая закупка")
    with pytest.raises(ValueError):
        parse_lenobl_listing(data)


@pytest.mark.parametrize("url", [
    URL + "?id=1", URL + "#tracking",
    URL.replace("https://", "http://"),
    URL.replace(HOST, HOST + ".evil.test"),
])
def test_noncanonical_detail_link_rejected(url):
    with pytest.raises(ValueError):
        parse_lenobl_detail(detail(), identity=IDENT, url=url, listing_title=TITLE)


def test_fetch_only_expected_two_https_urls(monkeypatch):
    calls = []

    class Client:
        async def get(self, url):
            calls.append(url)
            return SimpleNamespace(
                content=listing() if url == LIST_URL else detail(),
                headers={"content-type": "text/html;charset=utf-8"},
                raise_for_status=lambda: None,
            )

    @asynccontextmanager
    async def client(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        assert kwargs["headers"]["User-Agent"] == "Mozilla/5.0"
        assert kwargs["headers"]["Accept"] == "text/html"
        yield Client()

    import app.sources.lenobl_small_public as module
    monkeypatch.setattr(module, "source_client", client)
    rows = asyncio.run(LenoblSmallPublicSource().fetch(1))
    assert [r.identity for r in rows] == [("lenobl_small_public", IDENT)]
    assert calls == [LIST_URL, URL]


@pytest.mark.parametrize("limit", [0, 4, True, "3"])
def test_listing_limit_strict(limit):
    with pytest.raises(ValueError):
        parse_lenobl_listing(listing(), limit=limit)
