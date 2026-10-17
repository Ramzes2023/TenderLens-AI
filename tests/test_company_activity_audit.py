"""True SQLite application audit ledger: atomicity, deletion evidence, roles and tenants."""
from contextlib import closing

import pytest

from app.auth import AuthRepository
from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.database.repository import DatabaseAuthorizationError, DatabaseError, TenderRepository
from app.organizations import OrganizationRepository


def fixture(tmp_path):
    database = Database(DatabaseSettings("", tmp_path / "audit.sqlite"))
    database.migrate()
    users = AuthRepository(database)
    owner = users.create_account("audit-owner@example.test", "test-password-hash")
    member = users.create_account("audit-member@example.test", "test-password-hash")
    viewer = users.create_account("audit-viewer@example.test", "test-password-hash")
    outsider = users.create_account("audit-outsider@example.test", "test-password-hash")
    organization = OrganizationRepository(database).default_for_account(owner.id)
    with closing(database.connect()) as conn:
        with conn:
            for actor, role in ((member, "member"), (viewer, "viewer")):
                conn.execute(
                    "INSERT INTO organization_members(organization_id,account_id,role,created_at) "
                    "VALUES (?,?,?,?)", (organization.id, actor.id, role, "now"),
                )
            for company_id in (73, 74):
                conn.execute(
                    "INSERT INTO company_workspaces "
                    "(id,owner_user_id,name,profile_json,created_at,updated_at,organization_id) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (company_id, owner.owner_user_id, "Company " + str(company_id),
                     "{}", "now", "now", organization.id),
                )
    return database, TenderRepository(database), owner, member, viewer, outsider, organization


def scope(actor, organization, company=73):
    return dict(account_id=actor.id, organization_id=organization.id, company_id=company)


def test_save_refresh_delete_export_logged_without_payload_or_credentials(tmp_path):
    db, repo, owner, member, viewer, outsider, org = fixture(tmp_path)
    a = repo.save_opportunity_for_organization(
        **scope(member, org), source="eis", external_id="off-001",
        snapshot_json='{"secret-note":"DO NOT STORE","api_token":"private"}',
    )
    same = repo.save_opportunity_for_organization(
        **scope(member, org), source="eis", external_id="off-001",
        snapshot_json='{"secret-note":"different"}',
    )
    assert a.id == same.id
    repo.record_shortlist_export_for_organization(**scope(owner, org), format="csv", item_count=1)
    assert not repo.delete_saved_opportunity_for_organization(
        **scope(owner, org, company=74), saved_id=a.id,
    )
    assert repo.delete_saved_opportunity_for_organization(**scope(member, org), saved_id=a.id)
    events = repo.list_organization_activity_for_company(**scope(owner, org))
    assert [x["action"] for x in events] == [
        "tender_removed", "export_csv_generated", "tender_refreshed", "tender_saved",
    ]
    assert len(events) == 4
    assert events[1]["item_count"] == 1
    assert events[0]["saved_opportunity_id"] == a.id
    assert "secret-note" not in repr(events) and "private" not in repr(events)
    assert repo.list_organization_activity_for_company(**scope(owner, org, company=74)) == []
    with pytest.raises(DatabaseAuthorizationError):
        repo.list_organization_activity_for_company(**scope(member, org))
    with pytest.raises(DatabaseAuthorizationError):
        repo.list_organization_activity_for_company(**scope(viewer, org))
    with pytest.raises(DatabaseAuthorizationError):
        repo.list_organization_activity_for_company(**scope(outsider, org))
    with pytest.raises(DatabaseAuthorizationError):
        repo.record_shortlist_export_for_organization(**scope(outsider, org),
                                                      format="xlsx", item_count=2)
    with pytest.raises(DatabaseError):
        repo.record_shortlist_export_for_organization(**scope(owner, org),
                                                      format="bad", item_count=1)
    db.close()


def test_activity_insertion_failure_rolls_back_saved_tender_mutation(tmp_path):
    db, repo, owner, _, _, _, org = fixture(tmp_path)
    a = repo.save_opportunity_for_organization(**scope(owner, org), source="eis",
                                               external_id="official", snapshot_json='{}')
    with closing(db.connect()) as conn:
        with conn:
            conn.execute("DROP TABLE organization_activity_events")
    with pytest.raises(DatabaseError):
        repo.delete_saved_opportunity_for_organization(**scope(owner, org), saved_id=a.id)
    with pytest.raises(DatabaseError):
        repo.save_opportunity_for_organization(**scope(owner, org), source="eis",
                                               external_id="new", snapshot_json='{}')
    saved = repo.list_saved_opportunities_for_organization(owner.id, org.id, 73)
    assert [s.id for s in saved] == [a.id]
    db.close()
