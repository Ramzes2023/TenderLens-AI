from app.api.schemas import MonitorNoticeResponse
from app.currency import normalize_currency_code
from app.models.tender import TenderAnalysis
from app.monitoring.service import prefilter_notice
from app.scoring.engine import score_tender
from app.scoring.models import CompanyProfile
from app.sources.models import TenderNotice


def profile(**overrides):
    data = {
        "profile_version": "currency-test",
        "company_name": "Currency Test",
        "accepted_currencies": ["EUR"],
    }

    data.update(overrides)

    return CompanyProfile.model_validate(
        data
    )


def test_common_currency_aliases_are_canonical():
    cases = {
        "\u20ac": "EUR",
        "euro": "EUR",
        "eur": "EUR",
        "\u00a3": "GBP",
        "gbp": "GBP",
        "\u20bd": "RUB",
        "\u0440\u0443\u0431\u043b\u044c (RUB)": "RUB",
        "\u20b8": "KZT",
        "a$": "AUD",
        "ca$": "CAD",
        "us$": "USD",
        "nz$": "NZD",
        "\u20b9": "INR",
        "\u20ba": "TRY",
        "\u20be": "GEL",
        "\u20bc": "AZN",
        "yuan": "CNY",
        "yen": "JPY",
        "zar": "ZAR",
        "chf": "CHF",
    }

    for raw, expected in cases.items():
        assert (
            normalize_currency_code(raw)
            == expected
        )


def test_ambiguous_currency_symbols_are_not_guessed():
    assert (
        normalize_currency_code("$")
        == "$"
    )

    assert (
        normalize_currency_code("\u00a5")
        == "\u00a5"
    )


def test_empty_currency_becomes_missing():
    assert normalize_currency_code(None) is None
    assert normalize_currency_code("   ") is None


def test_company_profile_normalizes_and_deduplicates():
    value = CompanyProfile.model_validate(
        {
            "profile_version": "1",
            "company_name": "Demo",
            "accepted_currencies": [
                "eur",
                "\u20ac",
                "EUR",
                "\u20bd",
                "rub",
            ],
        }
    )

    assert value.accepted_currencies == [
        "EUR",
        "RUB",
    ]


def test_tender_analysis_normalizes_legacy_currency_label():
    analysis = TenderAnalysis(
        title="Tender",
        initial_price=100.0,
        currency=(
            "\u0440\u0443\u0431\u043b\u044c "
            "(RUB)"
        ),
    )

    assert analysis.currency == "RUB"


def test_api_notice_response_normalizes_currency():
    item = MonitorNoticeResponse(
        source="test",
        external_id="1",
        title="Tender",
        url="https://example.test/1",
        initial_price=100.0,
        currency="euro",
        reasons=[],
    )

    assert item.currency == "EUR"


def test_monitoring_budget_uses_normalized_currency():
    company = profile(
        max_contract_value=100.0,
        hard_stop_on_budget=True,
    )

    notice = TenderNotice(
        source="test",
        external_id="1",
        title="Tender",
        url="https://example.test/1",
        initial_price=150.0,
        currency="euro",
    )

    assert (
        prefilter_notice(
            notice,
            company,
        )
        is None
    )


def test_monitoring_foreign_currency_is_not_compared():
    company = CompanyProfile(
        profile_version="1",
        company_name="Demo",
        accepted_currencies=["RUB"],
        max_contract_value=1.0,
    )

    notice = TenderNotice(
        source="test",
        external_id="foreign",
        title="Tender",
        url="https://example.test/foreign",
        initial_price=999999999.0,
        currency="EUR",
    )

    match = prefilter_notice(
        notice,
        company,
    )

    assert match is not None

    assert any(
        "\u0412\u0430\u043b\u044e\u0442\u0430"
        in reason
        for reason in match.reasons
    )


def test_scoring_budget_uses_normalized_currency():
    company = profile(
        max_contract_value=100.0,
    )

    analysis = TenderAnalysis(
        title="Tender",
        initial_price=50.0,
        currency="\u20ac",
    )

    result = score_tender(
        analysis,
        company,
    )

    budget = next(
        criterion
        for criterion in result.criteria
        if criterion.code == "budget"
    )

    assert budget.status == "matched"


def _legacy_discovery_item(
    raw_currency="euro",
):
    return {
        "source": "legacy-source",
        "external_id": "legacy-1",
        "title": "Legacy opportunity",
        "url": "https://example.test/legacy",
        "initial_price": 125000.0,
        "currency": raw_currency,
        "reasons": [],
        "published_at": None,
        "summary": None,
        "analysis_stage": "metadata_preview",
        "metadata_analysis": {
            "title": "Legacy opportunity",
            "initial_price": 125000.0,
            "currency": raw_currency,
        },
        "preliminary_scoring": {
            "profile_name": "Legacy Company",
            "profile_version": "1",
            "fit_score": None,
            "scorable_weight": 0,
            "completeness_percent": 0,
            "criteria": [],
            "stop_factors": [],
            "document_risks": [],
            "missing_information": [],
        },
        "full_ai_analyzed": False,
    }


def test_saved_legacy_snapshot_currency_is_normalized():
    import json
    from types import SimpleNamespace

    from app.api.organization_workflow_routes import (
        _saved_opportunity_response,
    )

    record = SimpleNamespace(
        id=7,
        organization_id=3,
        company_id=4,
        snapshot_json=json.dumps(
            _legacy_discovery_item(
                "euro"
            )
        ),
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )

    result = (
        _saved_opportunity_response(
            record
        )
    )

    assert (
        result.opportunity.currency
        == "EUR"
    )

    assert (
        result
        .opportunity
        .metadata_analysis
        .currency
        == "EUR"
    )


def test_history_legacy_snapshot_currency_is_normalized():
    import json
    from types import SimpleNamespace

    from app.api.organization_workflow_routes import (
        _discovery_history_detail,
    )

    snapshot = {
        "items": [
            _legacy_discovery_item(
                "euro"
            )
        ],
        "attempted_sources": [
            "legacy-source"
        ],
        "successful_sources": [
            "legacy-source"
        ],
        "failed_sources": [],
        "partial_failure": False,
        "total_failure": False,
        "history_id": None,
    }

    record = SimpleNamespace(
        id=11,
        organization_id=3,
        company_id=4,
        created_by_account_id=5,
        result_count=1,
        scored_count=0,
        attempted_sources_json=(
            '["legacy-source"]'
        ),
        successful_sources_json=(
            '["legacy-source"]'
        ),
        failed_sources_json="[]",
        partial_failure=False,
        total_failure=False,
        snapshot_json=json.dumps(
            snapshot
        ),
        created_at="2026-01-01T00:00:00Z",
    )

    result = (
        _discovery_history_detail(
            record
        )
    )

    item = (
        result
        .discovery
        .items[0]
    )

    assert item.currency == "EUR"

    assert (
        item
        .metadata_analysis
        .currency
        == "EUR"
    )


def test_legacy_profile_currency_is_normalized_on_read():
    value = CompanyProfile.model_validate_json(
        """
        {
          "profile_version": "1",
          "company_name": "Legacy Company",
          "accepted_currencies": [
            "euro",
            "rubles"
          ]
        }
        """
    )

    assert value.accepted_currencies == [
        "EUR",
        "RUB",
    ]
