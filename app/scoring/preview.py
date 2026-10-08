"""Existing Discover metadata formula, independent of HTTP and AI providers."""
from .engine import score_tender

def score_metadata_preview(
    metadata_analysis,
    profile,
):
    """
    Rank metadata opportunities by product relevance.

    Search prefilter and metadata scoring intentionally
    use the same keyword matcher.

    Full document scoring remains unchanged.
    """
    from app.monitoring.service import (
        _term_match,
    )

    result = score_tender(
        metadata_analysis,
        profile,
    )

    title = (
        metadata_analysis.title
        or ""
    )

    object_text = (
        metadata_analysis.procurement_object
        or ""
    )

    technical = " ".join(
        metadata_analysis.technical_requirements
        or []
    )

    full_text = " ".join(
        (
            title,
            object_text,
            technical,
        )
    )

    primary_object = (
        object_text[:350]
    )

    product_keywords = [
        keyword
        for keyword
        in profile.product_keywords
        if str(keyword).strip()
    ]

    all_matches = [
        keyword
        for keyword
        in product_keywords
        if _term_match(
            full_text,
            keyword,
        )
    ]

    title_matches = [
        keyword
        for keyword
        in all_matches
        if _term_match(
            title,
            keyword,
        )
    ]

    primary_matches = [
        keyword
        for keyword
        in all_matches
        if _term_match(
            primary_object,
            keyword,
        )
    ]

    if not all_matches:
        relevance = 0.0

    elif title_matches:
        relevance = 70.0

    elif primary_matches:
        relevance = 60.0

    else:
        relevance = 35.0

    lower_primary = (
        (
            title
            + " "
            + object_text[:700]
        )
        .casefold()
        .replace("?", "?")
    )

    supply_signals = (
        "supply",
        "purchase",
        "delivery of",
        "replacement of",
        "supply and install",
        "\u043f\u043e\u0441\u0442\u0430\u0432\u043a",
        "\u0437\u0430\u043a\u0443\u043f\u043a",
        "\u043f\u0440\u0438\u043e\u0431\u0440\u0435\u0442\u0435\u043d",
    )

    service_only_signals = (
        "condition assessment",
        "building assessment",
        "consultancy",
        "consulting services",
        "advisory services",
        "feasibility study",
        "audit services",
        "survey services",
        "inspection services",
        "design services",
        "\u043e\u0431\u0441\u043b\u0435\u0434\u043e\u0432\u0430\u043d\u0438",
        "\u043a\u043e\u043d\u0441\u0443\u043b\u044c\u0442\u0430\u0446",
        "\u0430\u0443\u0434\u0438\u0442",
    )

    has_supply_intent = any(
        signal in lower_primary
        for signal in supply_signals
    )

    service_only = any(
        signal in lower_primary
        for signal in service_only_signals
    )

    if (
        all_matches
        and has_supply_intent
    ):
        relevance += 10.0

    if (
        service_only
        and not has_supply_intent
        and not title_matches
    ):
        relevance = min(
            relevance,
            20.0,
        )

    relevance = round(
        min(
            90.0,
            max(
                0.0,
                relevance,
            ),
        ),
        1,
    )

    updated_criteria = []

    for criterion in result.criteria:
        if criterion.code != "category":
            updated_criteria.append(
                criterion
            )
            continue

        if relevance >= 65:
            status = "matched"
            explanation = (
                "Strong product relevance in "
                "tender metadata."
            )

        elif relevance > 0:
            status = "partial"
            explanation = (
                "Product evidence exists, but "
                "the metadata indicates only "
                "partial or contextual relevance."
            )

        else:
            status = "failed"
            explanation = (
                "No meaningful product match "
                "was found in tender metadata."
            )

        earned = round(
            criterion.weight
            * relevance
            / 100.0,
            1,
        )

        updated_criteria.append(
            criterion.model_copy(
                update={
                    "status": status,
                    "earned_points": earned,
                    "explanation": explanation,
                    "evidence": list(
                        all_matches[:10]
                    ),
                }
            )
        )

    return result.model_copy(
        update={
            "fit_score": relevance,
            "criteria": updated_criteria,
        }
    )
