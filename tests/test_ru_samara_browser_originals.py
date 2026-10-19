"""OFFLINE adversarial tests; fabricated rows never establish live procurement."""
import json

import pytest

from scripts.research_ru_samara_browser_originals import choose_originals
from scripts.research_ru_samara_browser_grid import GRID


def item(n, *, link=None):
    return dict(
        number=f"ИМЗ-2026-{n:07d}",
        name=f"Синтетическая закупка оборудования номер {n}",
        uchr_sname=f"Муниципальный синтетический заказчик {n}",
        link=link or f"/smallpurchases/GzwSP/{5611000+n}",
    )


def payload(rows):
    return json.dumps({"items": rows}, ensure_ascii=False).encode()


def test_only_two_distinct_disclosed_same_host_numeric_original_links_qualify():
    a, b = choose_originals(payload([item(1), item(2), item(3)]))
    assert a == (
        "ИМЗ-2026-0000001",
        "Синтетическая закупка оборудования номер 1",
        "Муниципальный синтетический заказчик 1",
        "https://webtorgi.samregion.ru/smallpurchases/GzwSP/5611001",
    )
    assert b[3].startswith("https://webtorgi.samregion.ru/smallpurchases/GzwSP/")
    assert b[0] != a[0]
    assert b[3] != GRID


@pytest.mark.parametrize("rows", [
    [],
    [item(1)],
    [item(1), item(1)],
    [item(1), item(2, link="/smallpurchases/GzwSP/5611001")],
    [item(1), item(2, link="http://webtorgi.samregion.ru/smallpurchases/GzwSP/5611002")],
    [item(1), item(2, link="https://bad.invalid/smallpurchases/GzwSP/5611002")],
    [item(1), item(2, link="/smallpurchases/GzwSP/NoticesGrid")],
    [item(1), item(2, link="/smallpurchases/Login/Form")],
])
def test_no_unproven_duplicate_external_or_listing_links(rows):
    with pytest.raises(ValueError):
        choose_originals(payload(rows))
