import json
from types import SimpleNamespace

import pytest
import tests.test_organization_companies as company_tests

from app.api.schemas import (
    SourceHealthItem,
    TenderDiscoveryResponse,
)
from app.database.repository import (
    TenderRepository,
)
from app.sources import (
    SourceCapabilities,
    SourceRegistration,
    SourceRegistry,
    SourceTransport,
)


class NeverFetchSource:
    def __init__(self, name):
        self.name = name
        self.calls = 0

    async def fetch(
        self,
        limit=20,
    ):
        self.calls += 1

        raise AssertionError(
            "Source Health must not "
            "probe procurement sources."
        )


@pytest.fixture
def workspace():
    helper = (
        company_tests
        .OrganizationCompanyApiTests()
    )

    helper.setUp()

    try:
        repository = TenderRepository(
            helper.path
        )

        repository.initialize()

        ted = NeverFetchSource(
            "ted"
        )

        sam = NeverFetchSource(
            "sam_gov"
        )

        registry = SourceRegistry(
            [
                SourceRegistration(
                    key="ted",
                    display_name=(
                        "Tenders Electronic Daily"
                    ),
                    source=ted,
                    transport=(
                        SourceTransport.API
                    ),
                    jurisdictions=(
                        "EU",
                    ),
                    languages=(
                        "en",
                    ),
                    homepage_url=(
                        "https://ted.europa.eu/"
                    ),
                    official=True,
                    enabled=True,
                ),
                SourceRegistration(
                    key="sam_gov",
                    display_name="SAM.gov",
                    source=sam,
                    transport=(
                        SourceTransport.API
                    ),
                    jurisdictions=(
                        "US",
                    ),
                    languages=(
                        "en",
                    ),
                    homepage_url=(
                        "https://sam.gov/"
                    ),
                    official=True,
                    enabled=False,
                    capabilities=(
                        SourceCapabilities(
                            authentication_required=True,
                        )
                    ),
                ),
            ]
        )

        runtime = (
            helper.client
            .app.state.runtime
        )

        runtime.tender_repository = (
            repository
        )

        runtime.source_catalog = (
            SimpleNamespace(
                registry=registry
            )
        )

        helper.as_account(
            helper.owner
        )

        yield (
            helper,
            repository,
            ted,
            sam,
        )

    finally:
        helper.doCleanups()


def _create_company(w):
    response = w.client.post(
        w.url(),
        json={
            "name": (
                "Source Health Company"
            ),
            "profile": w.profile(
                "Source Health Company"
            ),
        },
    )

    assert (
        response.status_code
        == 201
    )

    return response.json()


def test_source_health_uses_saved_discovery_telemetry_only(
    workspace,
):
    (
        w,
        repository,
        ted,
        sam,
    ) = workspace

    company = _create_company(
        w
    )

    snapshot = (
        TenderDiscoveryResponse(
            items=[],
            source_statuses=[
                SourceHealthItem(
                    source="ted",
                    display_name=(
                        "Tenders Electronic Daily"
                    ),
                    transport="api",
                    jurisdictions=[
                        "EU",
                    ],
                    languages=[
                        "en",
                    ],
                    homepage_url=(
                        "https://ted.europa.eu/"
                    ),
                    official=True,
                    enabled=True,
                    authentication_required=False,
                    state="healthy",
                    notice_count=17,
                    duration_ms=321,
                )
            ],
            attempted_sources=[
                "ted",
            ],
            successful_sources=[
                "ted",
            ],
            failed_sources=[],
            partial_failure=False,
            total_failure=False,
        )
    )

    record = (
        repository
        .record_discovery_search_for_organization(
            account_id=w.owner.id,
            organization_id=(
                w.organization.id
            ),
            company_id=(
                company["id"]
            ),
            result_count=0,
            scored_count=0,
            attempted_sources_json=(
                json.dumps(
                    ["ted"]
                )
            ),
            successful_sources_json=(
                json.dumps(
                    ["ted"]
                )
            ),
            failed_sources_json="[]",
            partial_failure=False,
            total_failure=False,
            snapshot_json=(
                snapshot
                .model_dump_json()
            ),
        )
    )

    response = w.client.get(
        (
            f"/api/v1/organizations/"
            f"{w.organization.id}"
            "/discovery/source-health"
        )
    )

    assert (
        response.status_code
        == 200
    )

    assert (
        response.headers[
            "cache-control"
        ]
        == "no-store"
    )

    body = response.json()

    assert (
        body["company_id"]
        == company["id"]
    )

    assert (
        body["history_id"]
        == record.id
    )

    assert (
        body["last_checked"]
        == record.created_at
    )

    sources = {
        item["source"]:
        item
        for item
        in body["sources"]
    }

    assert (
        sources["ted"]["state"]
        == "healthy"
    )

    assert (
        sources["ted"]["notice_count"]
        == 17
    )

    assert (
        sources["ted"]["duration_ms"]
        == 321
    )

    assert (
        sources["sam_gov"]["state"]
        == "disabled"
    )

    assert (
        sources["sam_gov"]
        ["authentication_required"]
        is True
    )

    assert ted.calls == 0
    assert sam.calls == 0


def test_source_health_without_history_is_not_checked(
    workspace,
):
    (
        w,
        repository,
        ted,
        sam,
    ) = workspace

    company = _create_company(
        w
    )

    response = w.client.get(
        (
            f"/api/v1/organizations/"
            f"{w.organization.id}"
            "/discovery/source-health"
        )
    )

    assert (
        response.status_code
        == 200
    )

    body = response.json()

    assert body["history_id"] is None
    assert body["last_checked"] is None

    sources = {
        item["source"]:
        item
        for item
        in body["sources"]
    }

    assert (
        sources["ted"]["state"]
        == "not_checked"
    )

    assert (
        sources["sam_gov"]["state"]
        == "disabled"
    )

    assert ted.calls == 0
    assert sam.calls == 0


def test_source_health_is_company_scoped(
    workspace,
):
    (
        w,
        repository,
        ted,
        sam,
    ) = workspace

    first = _create_company(
        w
    )

    snapshot = (
        TenderDiscoveryResponse(
            items=[],
            source_statuses=[
                SourceHealthItem(
                    source="ted",
                    display_name="TED",
                    transport="api",
                    jurisdictions=[],
                    languages=[],
                    homepage_url=None,
                    official=True,
                    enabled=True,
                    authentication_required=False,
                    state="healthy",
                    notice_count=2,
                    duration_ms=100,
                )
            ],
            attempted_sources=[
                "ted",
            ],
            successful_sources=[
                "ted",
            ],
            failed_sources=[],
            partial_failure=False,
            total_failure=False,
        )
    )

    repository.record_discovery_search_for_organization(
        account_id=w.owner.id,
        organization_id=(
            w.organization.id
        ),
        company_id=first["id"],
        result_count=0,
        scored_count=0,
        attempted_sources_json='["ted"]',
        successful_sources_json='["ted"]',
        failed_sources_json="[]",
        partial_failure=False,
        total_failure=False,
        snapshot_json=(
            snapshot.model_dump_json()
        ),
    )

    second_response = w.client.post(
        w.url(),
        json={
            "name": "Second Health Company",
            "profile": w.profile(
                "Second Health Company"
            ),
        },
    )

    assert (
        second_response.status_code
        == 201
    )

    second = second_response.json()

    assert (
        w.client.post(
            w.url(
                f"/{second['id']}/activate"
            )
        ).status_code
        == 200
    )

    body = w.client.get(
        (
            f"/api/v1/organizations/"
            f"{w.organization.id}"
            "/discovery/source-health"
        )
    ).json()

    assert body["history_id"] is None

    sources = {
        item["source"]:
        item
        for item
        in body["sources"]
    }

    assert (
        sources["ted"]["state"]
        == "not_checked"
    )

    assert ted.calls == 0
    assert sam.calls == 0
