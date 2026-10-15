"""Offline guard tests for strict host-only EIS scoring proof.

No network is used here. Real source evidence must come from running the
separate strict acceptance command on the operator's Windows host.
"""
import pytest

from scripts.ci_ru_eis_user_scoring import (
    EIS_KEYS, LIMIT_PER_SOURCE, matching_keyword, strict_acceptance,
)


def test_eis_exact_source_selection_and_limit():
    assert EIS_KEYS == ("eis", "eis_223")
    assert LIMIT_PER_SOURCE == 10


@pytest.mark.parametrize("title,expected", [
    ("Поставка медицинского оборудования", "Поставка"),
    ("Закупка автомобилей", "Закупка"),
    ("alpha-supply contract", "alpha-supply"),
])
def test_keyword_is_derived_from_real_title(title, expected):
    assert matching_keyword(title) == expected


@pytest.mark.parametrize("title", ["", "..!", "a b 12"])
def test_empty_or_non_searchable_title_fails_closed(title):
    with pytest.raises(ValueError):
        matching_keyword(title)


def test_no_fake_root_can_trigger_live_scoring(monkeypatch):
    import scripts.ci_ru_eis_user_scoring as script
    def forbidden(*args, **kwargs):
        raise AssertionError("Unexpected source catalog was initialized")
    monkeypatch.setattr(script, "build_source_catalog", forbidden)
    with pytest.raises(ValueError):
        strict_acceptance(b"invalid certificate")
