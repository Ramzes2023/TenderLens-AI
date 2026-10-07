"""Reproducible rule-based tender/profile fit scoring."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.currency import normalize_currency_code
from app.models.tender import TenderAnalysis

from .models import CompanyProfile, CriterionResult, ScoringResult

# These weights intentionally sum to 100. Missing facts are excluded from the
# denominator rather than silently counted as a failure.
WEIGHTS = {
    "category": 30,
    "region": 15,
    "budget": 20,
    "bid_security": 10,
    "contract_security": 10,
    "documents": 15,
}


def _norm(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold().replace("ё", "е")
    value = re.sub(r"[^0-9a-zа-я]+", " ", value, flags=re.IGNORECASE)
    return " ".join(value.split())


def _has_phrase(haystack: str, needle: str) -> bool:
    n = _norm(needle)
    return bool(n) and n in _norm(haystack)


def _criterion(code: str, label: str, status: str, explanation: str,
               evidence: list[str] | None = None, ratio: float = 0.0) -> CriterionResult:
    weight = WEIGHTS[code]
    ratio = max(0.0, min(1.0, ratio))
    return CriterionResult(
        code=code,
        label=label,
        weight=weight,
        earned_points=round(weight * ratio, 2),
        status=status,
        explanation=explanation,
        evidence=evidence or [],
    )


def _category(analysis: TenderAnalysis, profile: CompanyProfile) -> CriterionResult:
    if not profile.product_keywords:
        return _criterion(
            "category",
            "Product relevance",
            "not_scored",
            "No product categories are configured in the company profile.",
        )

    source = "\n".join(
        filter(
            None,
            [
                analysis.title,
                analysis.procurement_object,
                *analysis.technical_requirements,
            ],
        )
    )

    if not source.strip():
        return _criterion(
            "category",
            "Product relevance",
            "not_scored",
            "The extracted tender data does not contain enough information about the procurement subject.",
        )

    matched = [
        keyword
        for keyword in profile.product_keywords
        if _has_phrase(source, keyword)
    ]

    if matched:
        return _criterion(
            "category",
            "Product relevance",
            "matched",
            "The procurement subject matches the company profile.",
            matched[:10],
            1.0,
        )

    return _criterion(
        "category",
        "Product relevance",
        "failed",
        "No product-category match was found for the company profile.",
        [],
        0.0,
    )


def _region(analysis: TenderAnalysis, profile: CompanyProfile) -> CriterionResult:
    if not profile.allowed_regions:
        return _criterion(
            "region",
            "Region",
            "not_scored",
            "No regional restrictions are configured in the company profile.",
        )

    location = " ".join(
        filter(
            None,
            [
                analysis.delivery_region,
                analysis.delivery_address,
            ],
        )
    )

    if not location:
        return _criterion(
            "region",
            "Region",
            "not_scored",
            "The delivery region or address was not extracted from the tender data.",
        )

    matched = [
        region
        for region in profile.allowed_regions
        if _has_phrase(location, region)
    ]

    if matched:
        return _criterion(
            "region",
            "Region",
            "matched",
            "The delivery location is within the company profile regions.",
            matched[:10],
            1.0,
        )

    return _criterion(
        "region",
        "Region",
        "failed",
        "The delivery location does not match the company profile regions.",
        [location],
        0.0,
    )


def _budget(
    analysis: TenderAnalysis,
    profile: CompanyProfile,
) -> tuple[CriterionResult, list[str]]:
    stops: list[str] = []

    if (
        profile.max_contract_value is None
        and profile.min_contract_value is None
    ):
        return (
            _criterion(
                "budget",
                "Budget",
                "not_scored",
                "No contract value range is configured in the company profile.",
            ),
            stops,
        )

    if analysis.initial_price is None:
        return (
            _criterion(
                "budget",
                "Budget",
                "not_scored",
                "The contract value was not extracted from the tender data.",
            ),
            stops,
        )

    tender_currency = normalize_currency_code(
        analysis.currency
    )

    accepted = {
        normalize_currency_code(value)
        for value in profile.accepted_currencies
    }

    if accepted and tender_currency is None:
        return (
            _criterion(
                "budget",
                "Budget",
                "not_scored",
                "The tender currency was not extracted, so the budget limit cannot be evaluated.",
            ),
            stops,
        )

    if (
        accepted
        and tender_currency not in accepted
    ):
        message = (
            f"Tender currency {tender_currency} "
            "is not included in the company profile currencies."
        )

        if profile.hard_stop_on_currency:
            stops.append(message)

        return (
            _criterion(
                "budget",
                "Budget",
                "failed",
                message,
                [str(tender_currency)],
                0.0,
            ),
            stops,
        )

    if (
        profile.min_contract_value is not None
        and analysis.initial_price
        < profile.min_contract_value
    ):
        message = (
            f"Contract value {analysis.initial_price:,.2f} "
            "is below the minimum profile value "
            f"{profile.min_contract_value:,.2f}."
        ).replace(",", " ")

        if profile.hard_stop_on_budget:
            stops.append(message)

        return (
            _criterion(
                "budget",
                "Budget",
                "failed",
                message,
                [],
                0.0,
            ),
            stops,
        )

    if (
        profile.max_contract_value is None
        or analysis.initial_price
        <= profile.max_contract_value
    ):
        if profile.max_contract_value is None:
            explanation = (
                f"Contract value {analysis.initial_price:,.2f} "
                "meets the minimum profile threshold."
            ).replace(",", " ")
        else:
            explanation = (
                f"Contract value {analysis.initial_price:,.2f} "
                "does not exceed the profile limit "
                f"{profile.max_contract_value:,.2f}."
            ).replace(",", " ")

        return (
            _criterion(
                "budget",
                "Budget",
                "matched",
                explanation,
                [],
                1.0,
            ),
            stops,
        )

    message = (
        f"Contract value {analysis.initial_price:,.2f} "
        "exceeds the profile limit "
        f"{profile.max_contract_value:,.2f}."
    ).replace(",", " ")

    if profile.hard_stop_on_budget:
        stops.append(message)

    return (
        _criterion(
            "budget",
            "Budget",
            "failed",
            message,
            [],
            0.0,
        ),
        stops,
    )


def _security(
    code: str,
    label: str,
    actual: float | None,
    maximum: float | None,
    hard_stop: bool,
) -> tuple[CriterionResult, list[str]]:
    stops: list[str] = []

    if maximum is None:
        return (
            _criterion(
                code,
                label,
                "not_scored",
                "No allowed threshold is configured in the company profile.",
            ),
            stops,
        )

    if actual is None:
        return (
            _criterion(
                code,
                label,
                "not_scored",
                "The security percentage was not extracted from the tender data.",
            ),
            stops,
        )

    if actual <= maximum:
        return (
            _criterion(
                code,
                label,
                "matched",
                (
                    f"{actual:g}% does not exceed "
                    f"the allowed threshold of {maximum:g}%."
                ),
                [],
                1.0,
            ),
            stops,
        )

    message = (
        f"{actual:g}% exceeds "
        f"the allowed threshold of {maximum:g}%."
    )

    if hard_stop:
        stops.append(
            f"{label}: {message}"
        )

    return (
        _criterion(
            code,
            label,
            "failed",
            message,
            [],
            0.0,
        ),
        stops,
    )


def _documents(
    analysis: TenderAnalysis,
    profile: CompanyProfile,
) -> CriterionResult:
    required = analysis.required_documents

    if not required:
        return _criterion(
            "documents",
            "Documents",
            "not_scored",
            "No list of required documents was found in the extracted tender data.",
        )

    if not profile.available_document_keywords:
        return _criterion(
            "documents",
            "Documents",
            "not_scored",
            "No available documents or certificates are configured in the company profile.",
        )

    matched_docs: list[str] = []
    missing_docs: list[str] = []

    for requirement in required:
        if any(
            _has_phrase(
                requirement,
                keyword,
            )
            or _has_phrase(
                keyword,
                requirement,
            )
            for keyword
            in profile.available_document_keywords
        ):
            matched_docs.append(
                requirement
            )
        else:
            missing_docs.append(
                requirement
            )

    ratio = (
        len(matched_docs)
        / len(required)
    )

    if ratio == 1:
        status = "matched"
    elif ratio == 0:
        status = "failed"
    else:
        status = "partial"

    explanation = (
        "Keyword matching confirms "
        f"{len(matched_docs)} of {len(required)} "
        "required documents."
    )

    evidence = (
        [
            "Available: " + item
            for item in matched_docs[:8]
        ]
        + [
            "Not confirmed: " + item
            for item in missing_docs[:8]
        ]
    )

    return _criterion(
        "documents",
        "Documents",
        status,
        explanation,
        evidence,
        ratio,
    )


def _completeness(analysis: TenderAnalysis) -> int:
    groups = [
        bool(analysis.title or analysis.tender_number or analysis.customer),
        analysis.initial_price is not None,
        bool(analysis.submission_deadline),
        bool(analysis.contract_term),
        bool(analysis.delivery_region or analysis.delivery_address),
        any(value is not None for value in (
            analysis.bid_security_amount, analysis.bid_security_percent,
            analysis.contract_security_amount, analysis.contract_security_percent,
        )),
        bool(analysis.procurement_object or analysis.quantity),
        bool(analysis.participant_requirements),
        bool(analysis.required_documents),
        bool(analysis.technical_requirements),
    ]
    return round(100 * sum(groups) / len(groups))


def score_tender(analysis: TenderAnalysis, profile: CompanyProfile) -> ScoringResult:
    """Score compatibility against explicit rules; never estimate win probability."""
    criteria: list[CriterionResult] = []
    stop_factors: list[str] = []

    criteria.append(_category(analysis, profile))
    criteria.append(_region(analysis, profile))

    budget, stops = _budget(analysis, profile)
    criteria.append(budget)
    stop_factors.extend(stops)

    bid, stops = _security(
        "bid_security", "Bid security", analysis.bid_security_percent,
        profile.max_bid_security_percent, profile.hard_stop_on_bid_security,
    )
    criteria.append(bid)
    stop_factors.extend(stops)

    contract, stops = _security(
        "contract_security", "Contract security", analysis.contract_security_percent,
        profile.max_contract_security_percent, profile.hard_stop_on_contract_security,
    )
    criteria.append(contract)
    stop_factors.extend(stops)

    criteria.append(_documents(analysis, profile))

    region_result = next(item for item in criteria if item.code == "region")
    if region_result.status == "failed" and profile.hard_stop_on_region:
        stop_factors.append(region_result.explanation)

    scorable = [item for item in criteria if item.status != "not_scored"]
    scorable_weight = sum(item.weight for item in scorable)
    earned = sum(item.earned_points for item in scorable)
    fit_score = round(earned / scorable_weight * 100, 1) if scorable_weight else None

    return ScoringResult(
        profile_name=profile.company_name,
        profile_version=profile.profile_version,
        fit_score=fit_score,
        scorable_weight=scorable_weight,
        completeness_percent=_completeness(analysis),
        criteria=criteria,
        stop_factors=list(dict.fromkeys(stop_factors)),
        document_risks=list(analysis.risks),
        missing_information=list(analysis.missing_information),
    )
