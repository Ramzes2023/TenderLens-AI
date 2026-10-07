import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest
import tests.test_organization_companies as company_tests

from app.llm.models import LLMResponse
from app.parsers.pdf import PdfSummary
from app.scoring.models import CompanyProfile
from app.services.company_profile_analysis import (
    CompanySearchProfileDraft,
    ProfileDraftError,
    ProfileDraftResult,
    analyze_company_search_profile,
    merge_company_profile_draft,
)


class FakeProvider:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    async def generate(
        self,
        prompt,
        *,
        max_tokens=512,
    ):
        self.calls.append(
            (prompt, max_tokens)
        )

        return LLMResponse(
            text=json.dumps(self.payload),
            provider="fake",
            model="fake",
            finish_reason="stop",
        )


def test_profile_draft_preserves_protected_constraints():
    current = CompanyProfile(
        profile_version="existing-v1",
        company_name="Existing Company",
        business_mode="sell",
        product_keywords=["old"],
        search_keywords=["old"],
        excluded_keywords=["used"],
        accepted_currencies=["EUR"],
        min_contract_value=1000,
        max_contract_value=500000,
        hard_stop_on_budget=False,
        hard_stop_on_currency=False,
    )

    provider = FakeProvider(
        {
            "industry": "Industrial pumping systems",
            "product_keywords": [
                "centrifugal pumps",
                "pump spare parts",
            ],
            "search_keywords": [
                "centrifugal pump supply",
            ],
            "allowed_regions": [],
            "allowed_countries": [
                "Germany",
            ],
            "available_document_keywords": [
                "ISO 9001",
            ],
        }
    )

    result = asyncio.run(
        analyze_company_search_profile(
            (
                "Manufacturer of centrifugal pumps and "
                "pump spare parts. Supplies Germany. "
                "ISO 9001 certified."
            ),
            provider,
        )
    )

    assert len(provider.calls) == 1

    assert "untrusted data" in (
        provider.calls[0][0]
    )

    suggested = merge_company_profile_draft(
        current,
        result.draft,
    )

    assert suggested.product_keywords == [
        "centrifugal pumps",
        "pump spare parts",
    ]

    assert suggested.search_keywords == [
        "centrifugal pump supply",
    ]

    assert suggested.allowed_countries == [
        "Germany",
    ]

    assert (
        suggested.available_document_keywords
        == ["ISO 9001"]
    )

    assert suggested.company_name == (
        "Existing Company"
    )

    assert suggested.business_mode == "sell"

    assert suggested.accepted_currencies == [
        "EUR"
    ]

    assert suggested.excluded_keywords == [
        "used"
    ]

    assert suggested.min_contract_value == 1000
    assert suggested.max_contract_value == 500000
    assert suggested.hard_stop_on_budget is False
    assert suggested.hard_stop_on_currency is False


def test_ai_cannot_set_protected_profile_field():
    provider = FakeProvider(
        {
            "industry": "Industrial",
            "product_keywords": ["pump"],
            "search_keywords": ["pump supply"],
            "allowed_regions": [],
            "allowed_countries": [],
            "available_document_keywords": [],
            "accepted_currencies": ["USD"],
        }
    )

    with pytest.raises(
        ProfileDraftError
    ):
        asyncio.run(
            analyze_company_search_profile(
                "Pump manufacturer.",
                provider,
            )
        )


@pytest.fixture
def workspace():
    helper = (
        company_tests
        .OrganizationCompanyApiTests()
    )

    helper.setUp()

    helper.client.app.state.runtime.provider = (
        object()
    )

    try:
        yield helper
    finally:
        helper.doCleanups()


def create_company(w):
    w.as_account(w.owner)

    response = w.client.post(
        w.url(),
        json={
            "name": "PDF Profile Company",
            "profile": {
                "profile_version": "pdf-profile-test",
                "company_name": "PDF Profile Company",
                "business_mode": "sell",
                "product_keywords": ["aluminium"],
                "search_keywords": ["aluminium"],
                "excluded_keywords": ["used"],
                "accepted_currencies": ["EUR"],
                "max_contract_value": 250000,
            },
        },
    )

    assert response.status_code == 201

    return response.json()


def summary():
    return PdfSummary(
        "ok",
        2,
        180,
        0,
        (
            "Manufacturer of industrial pumps. "
            "ISO 9001 certified."
        ),
        (
            "Manufacturer of industrial pumps.",
            "ISO 9001 certified.",
        ),
    )


def draft_result():
    return ProfileDraftResult(
        draft=CompanySearchProfileDraft(
            industry="Industrial equipment",
            product_keywords=[
                "industrial pumps",
            ],
            search_keywords=[
                "industrial pump supply",
            ],
            allowed_countries=["Italy"],
            available_document_keywords=[
                "ISO 9001",
            ],
        ),
        truncated=False,
    )


def test_preview_does_not_mutate_company(
    workspace,
):
    w = workspace
    company = create_company(w)

    with (
        patch(
            "app.api.organization_company_routes.summarize_pdf",
            new=AsyncMock(
                return_value=summary()
            ),
        ),
        patch(
            "app.api.organization_company_routes.analyze_company_search_profile",
            new=AsyncMock(
                return_value=draft_result()
            ),
        ),
    ):
        response = w.client.post(
            w.url(
                f"/{company['id']}"
                "/profile-from-pdf/preview"
            ),
            files={
                "file": (
                    "catalog.pdf",
                    b"%PDF-company",
                    "application/pdf",
                )
            },
        )

    assert response.status_code == 200, (
        response.text
    )

    body = response.json()

    assert (
        body["suggested_profile"]
        ["product_keywords"]
        == ["industrial pumps"]
    )

    assert (
        body["suggested_profile"]
        ["accepted_currencies"]
        == ["EUR"]
    )

    assert (
        body["suggested_profile"]
        ["excluded_keywords"]
        == ["used"]
    )

    assert (
        body["suggested_profile"]
        ["max_contract_value"]
        == 250000
    )

    stored = w.client.get(
        w.url(
            f"/{company['id']}"
        )
    )

    assert stored.status_code == 200

    assert (
        stored.json()
        ["profile"]
        ["product_keywords"]
        == ["aluminium"]
    )


def test_viewer_blocked_before_pdf_or_ai(
    workspace,
):
    w = workspace
    company = create_company(w)

    w.as_account(w.viewer)

    parse_mock = AsyncMock(
        return_value=summary()
    )

    ai_mock = AsyncMock(
        return_value=draft_result()
    )

    with (
        patch(
            "app.api.organization_company_routes.summarize_pdf",
            new=parse_mock,
        ),
        patch(
            "app.api.organization_company_routes.analyze_company_search_profile",
            new=ai_mock,
        ),
    ):
        response = w.client.post(
            w.url(
                f"/{company['id']}"
                "/profile-from-pdf/preview"
            ),
            files={
                "file": (
                    "catalog.pdf",
                    b"%PDF-company",
                    "application/pdf",
                )
            },
        )

    assert response.status_code == 403
    assert parse_mock.await_count == 0
    assert ai_mock.await_count == 0


def test_non_pdf_rejected_before_ai(
    workspace,
):
    w = workspace
    company = create_company(w)

    ai_mock = AsyncMock(
        return_value=draft_result()
    )

    with patch(
        "app.api.organization_company_routes.analyze_company_search_profile",
        new=ai_mock,
    ):
        response = w.client.post(
            w.url(
                f"/{company['id']}"
                "/profile-from-pdf/preview"
            ),
            files={
                "file": (
                    "catalog.txt",
                    b"not pdf",
                    "text/plain",
                )
            },
        )

    assert response.status_code == 415
    assert ai_mock.await_count == 0
