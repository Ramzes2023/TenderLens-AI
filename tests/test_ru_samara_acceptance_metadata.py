"""Offline tests of the live acceptance gate; fixtures are not source evidence."""
from dataclasses import replace

import pytest

from app.sources.models import TenderNotice
from scripts.ci_ru_samara_three_page_worker_sql import require_complete_metadata


def complete_rows():
    return [TenderNotice(
        source="ru_samara_public_list", external_id=str(5600000 + i),
        title="Offline fixture title", url="https://webtorgi.samregion.ru/",
        customer="Offline fixture buyer", initial_price=100.0, currency="RUB",
        published_at="19.10.2026", deadline="20.10.2026",
    ) for i in range(30)]


@pytest.mark.parametrize("field,value", [
    ("initial_price", None), ("currency", None), ("published_at", None),
    ("deadline", None), ("title", " "), ("customer", ""),
])
@pytest.mark.parametrize("index", [0, 15, 29])
def test_one_incomplete_row_cannot_pass_thirty_record_gate(field, value, index):
    rows = complete_rows()
    rows[index] = replace(rows[index], **{field: value})
    with pytest.raises(AssertionError, match="Incomplete original"):
        require_complete_metadata(rows)


def test_all_thirty_records_required_and_date_only_values_preserved():
    rows = complete_rows()
    assert set(require_complete_metadata(rows).values()) == {30}
    with pytest.raises(AssertionError, match="Exactly thirty"):
        require_complete_metadata(rows[:29])
