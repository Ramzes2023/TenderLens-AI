from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_company_currency_help_separates_normalization_from_fx():
    text = (
        ROOT
        / "app"
        / "api"
        / "dashboard.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "Currency labels are normalized "
        "to standard currency codes."
        in text
    )

    assert (
        "No FX conversion is performed"
        in text
    )


def test_discovery_currency_filter_explains_no_fx():
    text = (
        ROOT
        / "app"
        / "api"
        / "discovery_ui.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "Values use normalized currency codes."
        in text
    )

    assert (
        "No FX conversion is performed."
        in text
    )


def test_discovery_filter_uses_api_currency_code_directly():
    js = (
        ROOT
        / "app"
        / "api"
        / "static"
        / "discovery.js"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "if(f.currency&&item.currency!==f.currency)"
        "return false;"
        in js
    )

    assert (
        "options('filterCurrency',"
        "items.map(i=>i.currency));"
        in js
    )
