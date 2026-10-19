"""Adversarial OFFLINE pagination shape, not real procurement evidence."""
import pytest

from scripts.research_ru_samara_native_pagination import distinct_two_pages


def page(start):
    return {"items":[{"number":f"ИМЗ-2026-{n:07d}"} for n in range(start,start+10)]}


def test_two_synthetic_offline_native_pages_require_20_distinct_numbers():
    assert distinct_two_pages(page(0),page(10)) == {
        "page0_native": 10, "page1_native": 10, "distinct":20,
    }


@pytest.mark.parametrize("left,right", [
    (page(0),page(0)),
    (page(0),page(1)),
    (page(0),page(9)),
    (page(0),{"items":[]}),
    (page(0),{"items":[{"number":"fake"}]*10}),
    ({"items":[{"number":"ИМЗ-2026-123456"}]},page(10)),
    ({"items":"not a list"},page(10)),
    (page(0),{"items":[{"number":"ИМЗ-2026-123456"}]*10}),
])
def test_repeat_missing_and_fabricated_offline_page_not_validated(left,right):
    with pytest.raises(ValueError):
        distinct_two_pages(left,right)
