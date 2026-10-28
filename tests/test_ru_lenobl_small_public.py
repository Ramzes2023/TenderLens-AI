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


@pytest.mark.parametrize("limit", [0, 7, True, "3"])
def test_listing_limit_strict(limit):
    with pytest.raises(ValueError):
        parse_lenobl_listing(listing(), limit=limit)


@pytest.mark.parametrize("container", [
    "head", "template", "noscript", "svg",
])
def test_hidden_original_list_anchor_is_not_an_advertised_procurement(container):
    malicious = (
        f"<html><{container}><a href='{URL}'>{TITLE}</a></{container}>"
        "<main><p>No public tender available</p></main></html>"
    ).encode("utf-8")
    with pytest.raises(ValueError, match="No public Lenobl"):
        parse_lenobl_listing(malicious)


def test_hidden_template_duplicate_does_not_replace_visible_original_card():
    hidden = (f"<template><a href='{URL}'>Несовпадающий предмет закупки</a>"
              "</template>").encode("utf-8")
    verified = parse_lenobl_listing(hidden + listing())
    assert verified == [(IDENT, URL, TITLE)]


@pytest.mark.parametrize("payload", [
    (f"<html><head><title>Запрос № {IDENT}</title></head><body>"
     f"<h1>Закупка: {TITLE}</h1></body></html>").encode("utf-8"),
    (f"<html><body><template>Группа {IDENT}</template>"
     f"<h1>Закупка: {TITLE}</h1></body></html>").encode("utf-8"),
    (f"<html><body><p>1352174820</p>"
     f"<h1>Закупка: {TITLE}</h1></body></html>").encode("utf-8"),
])
def test_hidden_or_embedded_native_group_id_not_verified_original_detail(payload):
    with pytest.raises(ValueError, match="not visible"):
        parse_lenobl_detail(payload, identity=IDENT, url=URL, listing_title=TITLE)


def test_visible_native_detail_keeps_verified_number_even_with_hidden_metadata():
    payload = (f"<head><title>Other unrelated metadata</title></head>"
               f"<body><p>Группа закупок № {IDENT}</p>"
               f"<h1>Закупка: {TITLE}</h1></body>").encode("utf-8")
    notice = parse_lenobl_detail(payload, identity=IDENT, url=URL, listing_title=TITLE)
    assert notice.external_id == IDENT and notice.url == URL


def test_official_russian_month_offer_deadline_is_source_date_only():
    from app.sources.lenobl_small_public import parse_official_offer_local_datetime
    number, url, title = IDENT, URL, TITLE
    payload=(
        "<html><body><h1>Закупка: "+title+"</h1>"
        "<p>Группа закупок № "+number+"</p>"
        "<p>Дата создания: 28 октября 2026 г. 10:00:00</p>"
        "<dl><dt>Срок окончания подачи оферт:</dt>"
        "<dd>11 ноября 2026 г. 10:30:00</dd></dl>"
        "</body></html>"
    ).encode("utf8")
    notice=parse_lenobl_detail(payload,identity=number,url=url,listing_title=title)
    assert notice.deadline=="2026-11-11T10:30:00"
    assert parse_official_offer_local_datetime(
        "Срок окончания подачи оферт: 11 ноября 2026 г. 10:30:00"
    )=="2026-11-11T10:30:00"
    assert notice.initial_price is None
    assert notice.customer is None


def test_official_date_parser_rejects_hidden_conflicts_unknown_and_invalids():
    from app.sources.lenobl_small_public import parse_official_offer_local_datetime
    assert parse_official_offer_local_datetime(
        "Срок окончания подачи оферт: 31 февраля 2026 г. 10:30:00"
    ) is None
    assert parse_official_offer_local_datetime(
        "Срок окончания подачи оферт: 11 unknown 2026 г. 10:30:00"
    ) is None
    assert parse_official_offer_local_datetime(
        "Срок окончания подачи оферт: 11 ноября 2026 г. 26:30:00"
    ) is None
    assert parse_official_offer_local_datetime(
        "Срок окончания подачи оферт: 11 ноября 2026 г. 10:30:00 "
        "Срок окончания подачи оферт: 12 ноября 2026 г. 10:30:00"
    ) is None
    assert parse_official_offer_local_datetime("28 октября 2026 г. 10:30:00") is None
    hidden=(
        "<html><script>Срок окончания подачи оферт: 31 декабря 2099 г. 12:00:00</script>"
        "<template>Срок окончания подачи оферт: 31 декабря 2099 г. 12:00:00</template>"
        "<h1>Закупка: "+TITLE+"</h1><p>Группа закупок № "+IDENT+"</p>"
        "<p>Срок окончания подачи оферт: 29 октября 2026 г. 12:30:00</p></html>"
    ).encode("utf8")
    notice=parse_lenobl_detail(hidden,identity=IDENT,url=URL,listing_title=TITLE)
    assert notice.deadline=="2026-10-29T12:30:00"


def test_same_date_conflicting_publisher_closing_clocks_are_rejected():
    from app.sources.lenobl_small_public import parse_official_offer_local_datetime
    assert parse_official_offer_local_datetime(
        "Срок окончания подачи оферт: 29 октября 2026 г. 10:30:00 "
        "Срок окончания подачи оферт: 29 октября 2026 г. 11:30:00"
    ) is None
    assert parse_official_offer_local_datetime(
        "Срок окончания подачи оферт: 29 октября 2026 г. 10:30"
    ) == "2026-10-29T10:30"
