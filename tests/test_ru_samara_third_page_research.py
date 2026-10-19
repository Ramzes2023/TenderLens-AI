"""Offline hostile third-page Samara contracts; never imply live proof."""
from copy import deepcopy

import pytest

from scripts.research_ru_samara_third_page import verify_three_pages


def sample_pages():
    result = []
    for page in range(3):
        rows = []
        for offset in range(10):
            n = page * 10 + offset + 1
            rows.append({
                "link": f"/smallpurchases/GzwSP/{5400000 + n}",
                "number": f"ИМЗ-2026-0-223-{n:06d}",
                "name": f"Муниципальная поставка оборудования номер {n}",
                "uchr_sname": "Бюджетное учреждение Самарской области",
                "pub_date": "19.10.2026",
                "summa": "1000,00",
            })
        result.append({"items": rows, "totalRows": 30})
    return result


def test_third_page_unique_and_metadata_presence_is_not_verification():
    outcome = verify_three_pages(sample_pages())
    assert outcome["native_pages"] == 3
    assert outcome["native_unique_list_notices"] == 30
    assert outcome["distinct_native_numbers"] == 30
    assert outcome["optional_field_presence_counts_only"]["summa"] == 30
    assert outcome["optional_field_presence_counts_only"]["collecting_endDate"] == 0
    assert outcome["independent_detail_pages_verified"] is False
    assert outcome["production_activation"] is False


@pytest.mark.parametrize("bad", [
    "missing_second",
    "duplicate_identity",
    "duplicate_number",
    "foreign_link",
    "missing_buyer",
    "too_few_rows",
    "wrong_total",
    "missing_items",
])
def test_hostile_third_page_never_counts_as_verified(bad):
    pages = sample_pages()
    if bad == "missing_second":
        pages.pop(1)
    elif bad == "duplicate_identity":
        pages[2]["items"][0]["link"] = pages[0]["items"][0]["link"]
    elif bad == "duplicate_number":
        pages[2]["items"][0]["number"] = pages[0]["items"][0]["number"]
    elif bad == "foreign_link":
        pages[2]["items"][0]["link"] = "https://other.example/smallpurchases/GzwSP/5400021"
    elif bad == "missing_buyer":
        pages[2]["items"][0]["uchr_sname"] = ""
    elif bad == "too_few_rows":
        pages[2]["items"] = pages[2]["items"][:9]
    elif bad == "wrong_total":
        pages[2]["totalRows"] = 1
    elif bad == "missing_items":
        del pages[2]["items"]
    with pytest.raises((ValueError, KeyError, TypeError)):
        verify_three_pages(deepcopy(pages))


def test_metadata_shape_diagnostic_never_exposes_native_values():
    from scripts.research_ru_samara_third_page import public_metadata_shape
    assert public_metadata_shape(15000.5, kind="money") == "finite_number"
    assert public_metadata_shape("15 000,50", kind="money") == "grouped_space_money"
    assert public_metadata_shape("15000.50", kind="money") == "plain_number"
    assert public_metadata_shape("<html>", kind="money") == "unknown_money_format"
    assert public_metadata_shape("2026-10-19T13:40:00", kind="date") == "iso_date_time"
    assert public_metadata_shape("19.10.2026 13:40:00", kind="date") == "russian_dot_datetime"
    assert public_metadata_shape("19.10.2026", kind="date") == "russian_dot_date"
    assert public_metadata_shape("/Date(1792400000000)/", kind="date") == "asp_net_json_date"
    assert public_metadata_shape(None, kind="date") == "absent"
    assert public_metadata_shape(False, kind="money") == "absent"
