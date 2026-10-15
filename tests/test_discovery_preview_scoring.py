
from app.api.organization_workflow_routes import (
    _metadata_preview_scoring,
)
from app.scoring.models import (
    CompanyProfile,
)
from app.services.tender_analysis import (
    analysis_from_notice,
)
from app.sources.models import (
    TenderNotice,
)


def profile():
    return CompanyProfile(
        profile_version="preview-v3",
        company_name="Industrial Supplier",
        product_keywords=[
            "electrical equipment",
            "valves",
            "pumps",
            "\u043d\u0430\u0441\u043e\u0441\u044b",
        ],
        search_keywords=[
            "electrical equipment",
            "valves",
            "pumps",
            "\u043d\u0430\u0441\u043e\u0441\u044b",
        ],
    )


def score(
    title,
    summary,
):
    notice = TenderNotice(
        source="test",
        external_id=title,
        title=title,
        url="https://example.test/tender",
        summary=summary,
    )

    analysis = analysis_from_notice(
        notice
    )

    return _metadata_preview_scoring(
        analysis,
        profile(),
    )


def test_valves_project_scores_high():
    result = score(
        "Parkside Steam Safety Valves Project",
        (
            "The works include the supply, "
            "installation, testing and "
            "commissioning of new steam safety "
            "valve assemblies."
        ),
    )

    assert result.fit_score >= 75


def test_direct_pump_supply_scores_high():
    result = score(
        "\u0417\u0430\u043f\u0440\u043e\u0441 "
        "\u043a\u043e\u0442\u0438\u0440\u043e\u0432\u043e\u043a",
        (
            "\u041f\u043e\u0441\u0442\u0430\u0432\u043a\u0430 "
            "\u043d\u0430\u0441\u043e\u0441\u043e\u0432 "
            "\u0434\u043b\u044f "
            "\u0442\u0435\u043f\u043b\u043e\u0432\u043e\u0433\u043e "
            "\u043f\u0443\u043d\u043a\u0442\u0430"
        ),
    )

    assert result.fit_score >= 65


def test_incidental_building_assessment_scores_low():
    result = score(
        (
            "Central Stories - Full Building "
            "Condition Assessment"
        ),
        (
            "Consultants are required to undertake "
            "a comprehensive building condition "
            "assessment including roof, walls, "
            "windows, floors and building systems. "
            + ("x " * 220)
            + "Review electrical equipment where "
            "visible as part of the assessment."
        ),
    )

    assert result.fit_score <= 20


def test_metadata_preview_never_claims_100():
    result = score(
        "Supply of valves and pumps",
        (
            "Supply and delivery of valves "
            "and pumps."
        ),
    )

    assert result.fit_score <= 90



def test_bilingual_product_synonyms_do_not_add_bonus():
    bilingual_profile = CompanyProfile(
        profile_version="preview-v3-bilingual",
        company_name="Industrial Supplier",
        product_keywords=[
            "pumps",
            "\u043d\u0430\u0441\u043e\u0441\u044b",
        ],
        search_keywords=[
            "pumps",
            "\u043d\u0430\u0441\u043e\u0441\u044b",
        ],
    )

    notice = TenderNotice(
        source="eis",
        external_id="bilingual-pumps",
        title=(
            "\u0417\u0430\u043f\u0440\u043e\u0441 "
            "\u043a\u043e\u0442\u0438\u0440\u043e\u0432\u043e\u043a"
        ),
        url="https://example.test/bilingual-pumps",
        summary=(
            "\u041f\u043e\u0441\u0442\u0430\u0432\u043a\u0430 "
            "\u043d\u0430\u0441\u043e\u0441\u043e\u0432 "
            "\u0442\u043e\u0440\u0433\u043e\u0432\u043e\u0439 "
            "\u043c\u0430\u0440\u043a\u0438 IPM PUMPS "
            "\u0434\u043b\u044f "
            "\u0442\u0435\u043f\u043b\u043e\u0432\u043e\u0433\u043e "
            "\u043f\u0443\u043d\u043a\u0442\u0430"
        ),
    )

    analysis = analysis_from_notice(
        notice
    )

    result = _metadata_preview_scoring(
        analysis,
        bilingual_profile,
    )

    assert result.fit_score == 70.0


def test_multiple_keywords_do_not_inflate_metadata_fit():
    multi_profile = CompanyProfile(
        profile_version="preview-v3-multi",
        company_name="Industrial Supplier",
        product_keywords=[
            "pumps",
            "valves",
        ],
        search_keywords=[
            "pumps",
            "valves",
        ],
    )

    notice = TenderNotice(
        source="test",
        external_id="pumps-valves",
        title="Industrial equipment procurement",
        url="https://example.test/pumps-valves",
        summary=(
            "Supply and delivery of pumps and valves."
        ),
    )

    analysis = analysis_from_notice(
        notice
    )

    result = _metadata_preview_scoring(
        analysis,
        multi_profile,
    )

    assert result.fit_score == 70.0
