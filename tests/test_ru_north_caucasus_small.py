"""Offline hostile fixtures are NOT live acceptance or source enablement."""
import pytest

from scripts.research_ru_north_caucasus_small import (
    REGIONS, listing_originals, parse_html, safe_detail, verify_original,
)

HOST = REGIONS["north_ossetia"]
NUMBERS = ("2026000011", "2026000012")
TITLES = ("Поставка канцтоваров для сельской школы", "Ремонт крыши сельского детского сада")


def listing():
    return ("<table>"
            + "".join(
                f'<tr><td>№ {number}</td><td><a href="/purchases/detail/{number}">'
                f'{title}</a></td></tr>'
                for number, title in zip(NUMBERS, TITLES)
            )
            + "</table>").encode("utf-8")


def original(number, title):
    return (
        f"<table><tr><th>Номер объявления</th><td>{number}</td></tr>"
        f"<tr><th>Предмет закупки</th><td>{title}</td></tr>"
        "<tr><th>Заказчик</th><td>ГБУ Северной Осетии</td></tr>"
        "<tr><th>Цена закупки</th><td>120 000 рублей</td></tr></table>"
    ).encode("utf-8")


def test_exact_host_and_two_independent_originals():
    cards = listing_originals(listing(), HOST)
    assert [number for number, _, _ in cards] == list(NUMBERS)
    for number, title, url in cards:
        assert verify_original(original(number, title), number, title, url, HOST) == (
            number, title, url,
        )


@pytest.mark.parametrize("url", [
    "http://15.portalregion.ru/purchases/detail/2026000011",
    "https://evil.test/purchases/detail/2026000011",
    "https://15.portalregion.ru.evil.test/purchases/detail/2026000011",
    "https://alice:password@15.portalregion.ru/purchases/detail/2026000011",
    "https://15.portalregion.ru:8443/purchases/detail/2026000011",
    "//evil.test/purchases/detail/2026000011",
    "/login", "/account", "/admin", "/news/2026000011",
    "/search/purchases/detail/2026000011",
    "/purchases/detail/2026000011#fragment",
    "/purchases/detail/2026000011?redirect=evil.test",
    "/purchases/detail/2026000011?token=secret",
    "/purchases/detail/2026000011?id=11",
    "/purchases/detail/2026000011?userId=2026000011",
    "https://15.portalregion.ru/purchases/detail/2026000011%0a",
    "/purchases/detail/2026000011\\@evil.test",
])
def test_reject_external_credential_auth_or_ambiguous_paths(url):
    assert safe_detail(url, HOST) is None


def test_unlinked_or_placeholder_or_one_row_fails():
    with pytest.raises(ValueError):
        listing_originals("<h1>Портал закупок малого объема</h1>".encode("utf-8"), HOST)
    with pytest.raises(ValueError):
        listing_originals(listing().replace(NUMBERS[1].encode(), NUMBERS[0].encode()), HOST)
    with pytest.raises(ValueError):
        listing_originals(b"<table><tr><td>123456</td><td>Без ссылки</td></tr></table>", HOST)


def test_script_text_not_original_proof():
    script_only = (
        f'<script>Заказчик ГБУ Цена закупки 120000 руб {NUMBERS[0]} {TITLES[0]}</script>'
    ).encode("utf-8")
    assert not parse_html(script_only).text
    first_number, first_title, first_url = listing_originals(listing(), HOST)[0]
    with pytest.raises(ValueError):
        verify_original(script_only, first_number, first_title, first_url, HOST)


@pytest.mark.parametrize("bad", [
    lambda b: b.replace(b"2026000011", b"2026999999"),
    lambda b: b.replace("Поставка канцтоваров для сельской школы".encode("utf-8"),
                        "Поставка бумаги в районную школу".encode("utf-8")),
    lambda b: b.replace("Заказчик".encode("utf-8"), "Исполнитель".encode("utf-8")),
    lambda b: b.replace("Цена закупки".encode("utf-8"), "Дата закупки".encode("utf-8")),
    lambda b: b.replace("рублей".encode("utf-8"), "единиц".encode("utf-8")),
])
def test_original_is_not_accepted_without_independent_fields(bad):
    number, title, url = listing_originals(listing(), HOST)[0]
    with pytest.raises(ValueError):
        verify_original(bad(original(number, title)), number, title, url, HOST)


def test_public_candidate_hosts_are_fixed_and_not_authenticated():
    assert REGIONS == {
        "north_ossetia": "15.portalregion.ru",
        "kbr": "kbr.sberb2b.ru",
        "nalchik": "nalchik.sberb2b.ru",
        "kchr": "kchr.sberb2b.ru",
        "dagestan_vitrine": "dagestan.sberb2b.ru",
    }
