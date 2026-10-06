import sqlite3

import pytest

from app.database.repository import (
    DatabaseAuthorizationError,
    TenderRepository,
)


def _prepare_scope(path):
    repository = TenderRepository(path)
    repository.initialize()

    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS
            organization_members (
                organization_id INTEGER NOT NULL,
                account_id INTEGER NOT NULL,
                role TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS
            company_workspaces (
                id INTEGER PRIMARY KEY,
                organization_id INTEGER NOT NULL
            );
            """
        )

        conn.execute(
            """INSERT INTO organization_members(
                organization_id,
                account_id,
                role
            ) VALUES (?, ?, ?)""",
            (7, 101, "member"),
        )

        conn.execute(
            """INSERT INTO company_workspaces(
                id,
                organization_id
            ) VALUES (?, ?)""",
            (33, 7),
        )

        conn.execute(
            """INSERT INTO company_workspaces(
                id,
                organization_id
            ) VALUES (?, ?)""",
            (44, 7),
        )

    return repository


def _record(
    repository,
    *,
    company_id,
    result_count,
    snapshot,
):
    return (
        repository
        .record_discovery_search_for_organization(
            account_id=101,
            organization_id=7,
            company_id=company_id,
            result_count=result_count,
            scored_count=result_count,
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
            snapshot_json=snapshot,
        )
    )


def test_discovery_history_is_event_based_and_company_scoped(
    tmp_path,
):
    path = (
        tmp_path
        / "discovery-history.db"
    )

    repository = _prepare_scope(
        path
    )

    first = _record(
        repository,
        company_id=33,
        result_count=2,
        snapshot='{"run":1}',
    )

    second = _record(
        repository,
        company_id=33,
        result_count=3,
        snapshot='{"run":2}',
    )

    other = _record(
        repository,
        company_id=44,
        result_count=1,
        snapshot='{"run":3}',
    )

    assert first.id != second.id
    assert other.id not in {
        first.id,
        second.id,
    }

    company_33 = (
        repository
        .list_discovery_search_history_for_organization(
            101,
            7,
            33,
        )
    )

    assert [
        record.id
        for record in company_33
    ] == [
        second.id,
        first.id,
    ]

    assert (
        company_33[0]
        .result_count
        == 3
    )

    assert (
        company_33[0]
        .successful_sources_json
        == '["eis"]'
    )

    assert (
        repository
        .get_discovery_search_history_for_organization(
            101,
            7,
            33,
            first.id,
        )
        .snapshot_json
        == '{"run":1}'
    )

    assert (
        repository
        .get_discovery_search_history_for_organization(
            101,
            7,
            44,
            first.id,
        )
        is None
    )


def test_discovery_history_requires_membership(
    tmp_path,
):
    path = (
        tmp_path
        / "discovery-history-auth.db"
    )

    repository = _prepare_scope(
        path
    )

    with pytest.raises(
        DatabaseAuthorizationError
    ):
        (
            repository
            .list_discovery_search_history_for_organization(
                999,
                7,
                33,
            )
        )


def test_discovery_history_rejects_invalid_counts(
    tmp_path,
):
    path = (
        tmp_path
        / "discovery-history-counts.db"
    )

    repository = _prepare_scope(
        path
    )

    with pytest.raises(Exception):
        (
            repository
            .record_discovery_search_for_organization(
                account_id=101,
                organization_id=7,
                company_id=33,
                result_count=1,
                scored_count=2,
                attempted_sources_json="[]",
                successful_sources_json="[]",
                failed_sources_json="[]",
                partial_failure=False,
                total_failure=False,
                snapshot_json="{}",
            )
        )
