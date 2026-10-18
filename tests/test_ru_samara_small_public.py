"""Offline hostile HTML fixtures never count as live procurement evidence."""
import pytest
from scripts.research_ru_samara_small_public import (
    HOST, INDEX, GRID_URL, listing, strict_original_link, original_detail,
)

A = "ИМЗ-2026-0-223-000399"
B = "ИМЗ-2026-0-223-000480"
X = "Поставка рулонных штор для школы"
Y = "Приобретение запасных частей для автотранспорта"
FIRST = "/public/notice/detail?id=399"
SECOND = "/public/notice/detail?id=480"


def synthetic_index():
    return (f"""<html><table>
        <tr><td>{A}</td><td><a href="{FIRST}">{X}</a></td></tr>
        <tr><td>{B}</td><td><a href="{SECOND}">{Y}</a></td></tr>
        </table></html>""").encode("utf-8")


def synthetic_detail(number, title):
    return (f"<html><h1>{title}</h1><table><tr><th>Номер</th><td>{number}</td></tr>"
            "<tr><th>Заказчик</th><td>Самарская организация</td></tr>"
            "<tr><th>Цена</th><td>135000 RUB</td></tr></table></html>").encode("utf-8")


def test_two_distinct_firstparty_original_details():
    verified = listing(synthetic_index())
    assert len(verified) == 2
    for number, title, url in verified:
        assert original_detail(synthetic_detail(number, title), number, title, url) == (number, title, url)


@pytest.mark.parametrize("href", [
    "http://webtorgi.samregion.ru/public/notice/detail?id=399",
    "https://webtorgi.samregion.ru.evil.example/public/notice/detail?id=399",
    "https://evil.example/public/notice/detail?id=399",
    "//evil.example/public/notice/detail?id=399",
    "https://user:password@webtorgi.samregion.ru/public/notice/detail?id=399",
    "/public/notice/detail?id=399&redirect=https://evil.example",
    "/public/notice/detail?id=399#fragment",
    "/login", "/",
    "/public/notice/detail?id=399%0d%0aLocation:",
])
def test_reject_untrusted_url(href):
    assert strict_original_link(href) is None


def test_login_scripts_and_single_offer_never_green():
    for raw in (
        b"<html>Login</html>",
        synthetic_index().replace(B.encode(), A.encode()),
        f'<script><tr><td>{A}</td><a href="{FIRST}">{X}</a></tr></script>'.encode(),
        f'<table><tr><td>{A}</td><a href="{FIRST}">{X}</a></tr></table>'.encode(),
    ):
        with pytest.raises(ValueError):
            listing(raw)


def test_independent_details_must_match_buyer_and_price():
    indexed = listing(synthetic_index())
    n, title, url = indexed[0]
    for html in (
        synthetic_detail("ИМЗ-2026-0-223-000111", title),
        synthetic_detail(n, "Другой предмет закупки"),
        synthetic_detail(n, title).replace("Заказчик".encode(), "Продавец".encode()),
        synthetic_detail(n, title).replace("Цена".encode(), "Статус".encode()),
        f"<script>{n} {title} Заказчик: ООО Цена: 1</script>".encode("utf-8"),
    ):
        with pytest.raises(ValueError):
            original_detail(html, n, title, url)


def test_exact_origin():
    assert HOST == "webtorgi.samregion.ru"
    assert INDEX == "https://webtorgi.samregion.ru/smallpurchases/Menu/Page/1"
    assert GRID_URL == "https://webtorgi.samregion.ru/smallpurchases/GzwSP/NoticesGrid"
