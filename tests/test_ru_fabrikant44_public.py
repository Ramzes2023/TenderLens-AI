"""Synthetic offline Fabrikant 44-FZ contracts, not actual tender evidence."""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.sources.fabrikant_44_public import (
    HOST, LIST_URL, Fabrikant44PublicSource,
    parse_fabrikant44_detail, parse_fabrikant44_listing,
)

ID = "0358400002426000046"
URL = "https://soap4.fabrikant.ru/44/procedure/ea21/" + ID
TITLE = "Поставка медицинского оборудования"


def listing(href=URL+"?&backurl=LzQ0L2NhdGFsb2c", title=TITLE):
    return f"<html><a href='{href}'><span>{title}</span></a></html>".encode("utf-8")


def detail(number=ID, title=TITLE):
    return (f"<html><h1>Сведения о закупке {number}</h1>"
            f"<main><label>Наименование закупки</label><div>{title}</div></main></html>").encode("utf-8")


def test_public_backurl_is_not_sent_and_independent_detail_is_mandatory():
    items = parse_fabrikant44_listing(listing())
    assert items == [(ID, URL, TITLE)]
    notice = parse_fabrikant44_detail(detail(), identity=ID, url=URL, title=TITLE)
    assert notice.identity == ("fabrikant_44_public", ID)
    assert notice.tender_number == ID
    assert notice.title == TITLE
    assert notice.deadline is None
    assert notice.url == URL


@pytest.mark.parametrize("payload", [
    b"", b"<html>empty</html>",
    listing(href="http://soap4.fabrikant.ru/44/procedure/ea21/" + ID),
    listing(href="https://soap4.fabrikant.ru.evil.invalid/44/procedure/ea21/" + ID),
    listing(href="https://soap4.fabrikant.ru/44/procedure/ea21/" + ID + "?token=xyz"),
    listing(href=URL + "#fragment"),
    listing(href=URL + "/documents"),
    listing(href=URL + "?&backurl=x&extra=1"),
    listing(title=""),
    listing(title="<script>unsafe</script>"),
])
def test_invalid_source_cards_rejected(payload):
    with pytest.raises(ValueError):
        parse_fabrikant44_listing(payload)


@pytest.mark.parametrize("bad", [
    detail(number="0358400002426000047"),
    detail(title="Совсем другое наименование"),
    "<html><h1>Сведения о закупке 0358400002426000046</h1></html>".encode("utf-8"),
    b"<html><h1>Wrong</h1></html>",
    b"",
])
def test_official_detail_disagreement_rejected(bad):
    with pytest.raises(ValueError):
        parse_fabrikant44_detail(bad, identity=ID, url=URL, title=TITLE)


@pytest.mark.parametrize("url", [
    URL + "?&backurl=test",
    URL.replace("https", "http"),
    URL.replace("soap4.fabrikant.ru", "soap4.fabrikant.ru.evil.test"),
])
def test_detail_url_must_be_exact_canonical_host(url):
    with pytest.raises(ValueError):
        parse_fabrikant44_detail(detail(), identity=ID, url=url, title=TITLE)


@pytest.mark.parametrize("limit", [0, True, "3", 4])
def test_invalid_listing_limit(limit):
    with pytest.raises(ValueError):
        parse_fabrikant44_listing(listing(), limit=limit)


def test_live_source_transport_contract_offline(monkeypatch):
    urls = []

    class Fake:
        async def get(self, url):
            urls.append(url)
            return SimpleNamespace(
                content=listing() if url == LIST_URL else detail(),
                headers={"content-type": "text/html;charset=utf-8"},
                raise_for_status=lambda: None,
            )

    @asynccontextmanager
    async def client(**kwargs):
        assert kwargs["follow_redirects"] is False
        assert kwargs["trust_env"] is False
        assert kwargs["headers"]["Accept"] == "text/html"
        assert kwargs["headers"]["User-Agent"] == "Mozilla/5.0"
        yield Fake()

    import app.sources.fabrikant_44_public as mod
    monkeypatch.setattr(mod, "source_client", client)
    notices = asyncio.run(Fabrikant44PublicSource().fetch(1))
    assert len(notices) == 1
    assert notices[0].identity == ("fabrikant_44_public", ID)
    assert urls == [LIST_URL, URL]


def test_conflicting_duplicate_ids_rejected():
    page = (listing() + listing(
        href="https://soap4.fabrikant.ru/44/procedure/ezk21/" + ID,
        title="Иное название закупки",
    ))
    with pytest.raises(ValueError):
        parse_fabrikant44_listing(page, limit=3)
