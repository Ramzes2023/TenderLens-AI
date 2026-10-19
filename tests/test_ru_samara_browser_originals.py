"""OFFLINE adversarial tests; fabricated rows never establish live procurement."""
import json

import pytest

from scripts.research_ru_samara_browser_originals import choose_originals, classify_original_navigation
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



def test_native_detail_same_identity_canonicalization_is_not_blocked_blindly():
    numeric = "https://webtorgi.samregion.ru/smallpurchases/GzwSP/5611196"
    canonical = "https://webtorgi.samregion.ru/smallpurchases/GzwSP/Notice?noticeLink=5611196"
    assert classify_original_navigation(numeric, numeric) == "EXACT_ORIGINAL"
    assert classify_original_navigation(canonical, numeric) == "SAME_ID_CANONICAL_REDIRECT"
    assert classify_original_navigation(numeric, canonical) == "SAME_ID_CANONICAL_REDIRECT"


@pytest.mark.parametrize("final,expected", [
    ("https://webtorgi.samregion.ru/smallpurchases/Account/Login", "LOGIN_REQUIRED"),
    ("https://webtorgi.samregion.ru/smallpurchases/GzwSP/NoticesGrid", "RETURNED_TO_LIST"),
    ("https://webtorgi.samregion.ru/smallpurchases/GzwSP/Notice?noticeLink=5611197", "UNVERIFIED_REDIRECT"),
    ("https://evil.invalid/smallpurchases/GzwSP/5611196", "UNTRUSTED_ORIGIN"),
    ("http://webtorgi.samregion.ru/smallpurchases/GzwSP/5611196", "UNTRUSTED_ORIGIN"),
    ("https://webtorgi.samregion.ru/smallpurchases/GzwSP/Notice?noticeLink=5611196&admin=1", "UNVERIFIED_REDIRECT"),
])
def test_browser_rejects_login_and_mismatched_canonical_redirect(final,expected):
    requested="https://webtorgi.samregion.ru/smallpurchases/GzwSP/5611196"
    assert classify_original_navigation(requested,final)==expected
