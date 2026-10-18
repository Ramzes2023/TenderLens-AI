"""Synthetic fixtures only test strict parsing, never qualify as real source."""
import pytest
from scripts.research_ru_stavropol_rts_small import (
    canonical, current_cards, verify_original, HOST, INDEX,
)

FIRST = "ИМЗ-2026-123456"
SECOND = "ИМЗ-2026-123457"
FIRST_TITLE = "Поставка медикаментов для районной больницы"
SECOND_TITLE = "Поставка канцелярских товаров в школу"


def list_html():
    return (f'<table><tr><td>{FIRST}</td><td><a href="/purchases/detail/123456">'
            f'{FIRST_TITLE}</a></td></tr><tr><td>{SECOND}</td>'
            f'<td><a href="/purchases/detail/123457">{SECOND_TITLE}</a></td>'
            '</tr></table>').encode("utf-8")


def detail_html(number, title):
    return (f'<table><tr><th>Номер извещения</th><td>{number}</td></tr>'
            f'<tr><th>Объект закупки</th><td>{title}</td></tr>'
            '<tr><th>Заказчик</th><td>ГБУ Ставропольского края</td></tr>'
            '<tr><th>Цена закупки</th><td>25000 рублей</td></tr></table>').encode("utf-8")


def test_two_original_same_host_notices_require_details():
    rows = current_cards(list_html())
    assert len(rows) == 2
    for number, title, url in rows:
        assert verify_original(detail_html(number, title), number, title, url) == (number, title, url)


@pytest.mark.parametrize("bad", [
    "https://fake.test/purchases/detail/123456",
    "https://market26.rts-tender.ru.evil.test/purchases/detail/123456",
    "http://market26.rts-tender.ru/purchases/detail/123456",
    "/login", "/account", "/",
    "/purchases/detail/123456#foo",
    "/purchases/detail/123456?redirect=https://evil.test",
    "/purchases/detail/123456?token=secret",
    "/purchases/detail/123456?id=abc",
    "https://user:pass@market26.rts-tender.ru/purchases/detail/123456",
])
def test_no_unsafe_cross_origin_query_or_login_links(bad):
    assert canonical(bad) is None


def test_historic_aggregate_and_single_notice_cannot_be_live_proof():
    with pytest.raises(ValueError):
        current_cards(b"<p>21255 completed purchases</p>")
    with pytest.raises(ValueError):
        current_cards(list_html().replace(SECOND.encode(), FIRST.encode()))


def test_original_details_require_subject_buyer_price_and_native_number():
    n, title, url = current_cards(list_html())[0]
    for bad in (
        detail_html("ИМЗ-2026-999999", title),
        detail_html(n, "Иной предмет закупки"),
        detail_html(n, title).replace("Заказчик".encode(), "Исполнитель".encode()),
        detail_html(n, title).replace("Цена закупки".encode(), "Срок закупки".encode()),
        f"<script>{n} {title} Заказчик ГБУ Цена 1</script>".encode("utf-8"),
    ):
        with pytest.raises(ValueError):
            verify_original(bad, n, title, url)


def test_official_pinned_stavropol_market():
    assert HOST == "market26.rts-tender.ru"
    assert INDEX == "https://market26.rts-tender.ru/"
