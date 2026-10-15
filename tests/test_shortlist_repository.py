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
            (
                7,
                101,
                "member",
            ),
        )

        conn.execute(
            """INSERT INTO company_workspaces(
                id,
                organization_id
            ) VALUES (?, ?)""",
            (
                33,
                7,
            ),
        )

        conn.execute(
            """INSERT INTO company_workspaces(
                id,
                organization_id
            ) VALUES (?, ?)""",
            (
                44,
                7,
            ),
        )

    return repository


def test_shortlist_save_is_idempotent_and_scoped(
    tmp_path,
):
    path = tmp_path / "shortlist.db"

    repository = _prepare_scope(
        path
    )

    first = (
        repository
        .save_opportunity_for_organization(
            account_id=101,
            organization_id=7,
            company_id=33,
            source="eis",
            external_id="0372200163326000019",
            snapshot_json='{"version":1}',
        )
    )

    second = (
        repository
        .save_opportunity_for_organization(
            account_id=101,
            organization_id=7,
            company_id=33,
            source="eis",
            external_id="0372200163326000019",
            snapshot_json='{"version":2}',
        )
    )

    assert first.id == second.id
    assert second.snapshot_json == (
        '{"version":2}'
    )

    other_company = (
        repository
        .save_opportunity_for_organization(
            account_id=101,
            organization_id=7,
            company_id=44,
            source="eis",
            external_id="0372200163326000019",
            snapshot_json='{"version":3}',
        )
    )

    assert (
        other_company.id
        != first.id
    )

    company_33 = (
        repository
        .list_saved_opportunities_for_organization(
            101,
            7,
            33,
        )
    )

    company_44 = (
        repository
        .list_saved_opportunities_for_organization(
            101,
            7,
            44,
        )
    )

    assert len(company_33) == 1
    assert len(company_44) == 1

    assert (
        company_33[0].company_id
        == 33
    )

    assert (
        company_44[0].company_id
        == 44
    )


def test_shortlist_delete_is_company_scoped(
    tmp_path,
):
    path = tmp_path / "shortlist.db"

    repository = _prepare_scope(
        path
    )

    saved = (
        repository
        .save_opportunity_for_organization(
            account_id=101,
            organization_id=7,
            company_id=33,
            source="nz_gets",
            external_id="35108951",
            snapshot_json='{"title":"Valves"}',
        )
    )

    wrong_company_removed = (
        repository
        .delete_saved_opportunity_for_organization(
            account_id=101,
            organization_id=7,
            company_id=44,
            saved_id=saved.id,
        )
    )

    assert (
        wrong_company_removed
        is False
    )

    removed = (
        repository
        .delete_saved_opportunity_for_organization(
            account_id=101,
            organization_id=7,
            company_id=33,
            saved_id=saved.id,
        )
    )

    assert removed is True

    remaining = (
        repository
        .list_saved_opportunities_for_organization(
            101,
            7,
            33,
        )
    )

    assert remaining == []


def test_shortlist_requires_membership(
    tmp_path,
):
    path = tmp_path / "shortlist.db"

    repository = _prepare_scope(
        path
    )

    with pytest.raises(
        DatabaseAuthorizationError
    ):
        repository.list_saved_opportunities_for_organization(
            999,
            7,
            33,
        )


def test_shortlist_rejects_company_from_other_org(
    tmp_path,
):
    path = tmp_path / "shortlist.db"

    repository = _prepare_scope(
        path
    )

    with sqlite3.connect(path) as conn:
        conn.execute(
            """INSERT INTO company_workspaces(
                id,
                organization_id
            ) VALUES (?, ?)""",
            (
                55,
                8,
            ),
        )

    with pytest.raises(
        DatabaseAuthorizationError
    ):
        repository.save_opportunity_for_organization(
            account_id=101,
            organization_id=7,
            company_id=55,
            source="eis",
            external_id="test-55",
            snapshot_json='{"title":"Wrong org"}',
        )
