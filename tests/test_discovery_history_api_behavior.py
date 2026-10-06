import json

import pytest
import tests.test_organization_companies as company_tests

from app.database.repository import (
    TenderRepository,
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

        (
            helper.client
            .app.state.runtime
            .tender_repository
        ) = repository

        helper.as_account(
            helper.owner
        )

        yield helper, repository

    finally:
        helper.doCleanups()


def _snapshot():
    return json.dumps(
        {
            "items": [],
            "attempted_sources": [
                "eis",
                "ted",
            ],
            "successful_sources": [
                "eis",
            ],
            "failed_sources": [
                "ted",
            ],
            "partial_failure": True,
            "total_failure": False,
            "history_id": None,
        }
    )


def test_history_api_is_company_scoped_and_snapshot_backed(
    workspace,
):
    w, repository = workspace
    client = w.client

    company = client.post(
        w.url(),
        json={
            "name": "History Company",
            "profile": w.profile(
                "History Company"
            ),
        },
    )

    assert (
        company.status_code
        == 201
    )

    company_id = (
        company.json()["id"]
    )

    record = (
        repository
        .record_discovery_search_for_organization(
            account_id=w.owner.id,
            organization_id=(
                w.organization.id
            ),
            company_id=company_id,
            result_count=0,
            scored_count=0,
            attempted_sources_json=(
                '["eis","ted"]'
            ),
            successful_sources_json=(
                '["eis"]'
            ),
            failed_sources_json=(
                '["ted"]'
            ),
            partial_failure=True,
            total_failure=False,
            snapshot_json=_snapshot(),
        )
    )

    base = (
        f"/api/v1/organizations/"
        f"{w.organization.id}"
        "/discovery/history"
    )

    listed = client.get(
        base
    )

    assert (
        listed.status_code
        == 200
    )

    rows = listed.json()

    assert len(rows) == 1
    assert (
        rows[0]["id"]
        == record.id
    )

    assert (
        rows[0]["successful_sources"]
        == ["eis"]
    )

    detail = client.get(
        f"{base}/{record.id}"
    )

    assert (
        detail.status_code
        == 200
    )

    body = detail.json()

    assert (
        body["discovery"]["history_id"]
        == record.id
    )

    assert (
        body["discovery"]
        ["attempted_sources"]
        == ["eis", "ted"]
    )

    second = client.post(
        w.url(),
        json={
            "name": "Other Company",
            "profile": w.profile(
                "Other Company"
            ),
        },
    )

    assert (
        second.status_code
        == 201
    )

    second_id = (
        second.json()["id"]
    )

    assert (
        client.post(
            w.url(
                f"/{second_id}/activate"
            )
        ).status_code
        == 200
    )

    assert (
        client.get(
            base
        ).json()
        == []
    )

    assert (
        client.get(
            f"{base}/{record.id}"
        ).status_code
        == 404
    )

    assert (
        client.post(
            w.url(
                f"/{company_id}/activate"
            )
        ).status_code
        == 200
    )

    w.as_account(
        w.outsider
    )

    assert (
        client.get(
            base
        ).status_code
        == 403
    )
