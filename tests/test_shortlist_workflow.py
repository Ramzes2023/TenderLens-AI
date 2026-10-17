"""Real SQLite lifecycle, membership, revision and audit security tests."""
from contextlib import closing

import pytest

from app.auth import AuthRepository
from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.organizations import OrganizationRepository
from app.workspaces.lifecycle import SavedTenderWorkflow, WorkflowConflict, WorkflowDenied, WorkflowMissing


def fixture(tmp_path):
    db = Database(DatabaseSettings("", tmp_path / "saved-workflow.sqlite"))
    db.migrate()
    accounts = AuthRepository(db)
    alice = accounts.create_account("saved-alice@example.test", "safe-hash")
    bob = accounts.create_account("saved-bob@example.test", "safe-hash")
    viewer = accounts.create_account("saved-viewer@example.test", "safe-hash")
    org = OrganizationRepository(db).default_for_account(alice.id)
    with closing(db.connect()) as conn:
        with conn:
            conn.execute("INSERT INTO organization_members(organization_id,account_id,role,created_at)"
                         " VALUES (?,?,?,?)", (org.id, viewer.id, "viewer", "2026-10-17T00:00:00Z"))
            conn.execute("INSERT INTO saved_opportunities "
                         "(organization_id,company_id,source,external_id,snapshot_json,created_at,updated_at) "
                         "VALUES (?,?,?,?,?,?,?)",
                         (org.id, 73, "eis", "real-id", "{}", "now", "now"))
            saved_id = conn.execute("SELECT id FROM saved_opportunities").fetchone()["id"]
    return db, alice, bob, viewer, org, saved_id


def call(service, account, org, saved_id, **extra):
    return dict(dict(account_id=account.id, organization_id=org.id, company_id=73,
                     saved_id=saved_id), **extra)


def test_lifecycle_persists_and_revisions_audited_without_note_copy(tmp_path):
    db, alice, bob, viewer, org, saved_id = fixture(tmp_path)
    service = SavedTenderWorkflow(db)
    scope = call(service, alice, org, saved_id)
    assert service.get(**scope)["revision"] == 0
    updated = service.update(**scope, stage="preparing", note="Confidential", expected_revision=0)
    assert (updated["stage"], updated["revision"]) == ("preparing", 1)
    assert service.update(**scope, stage="preparing", note="Confidential", expected_revision=1)["revision"] == 1
    with pytest.raises(WorkflowConflict):
        service.update(**scope, stage="submitted", note="", expected_revision=0)
    current = service.update(**scope, stage="submitted", note="", expected_revision=1)
    assert current["revision"] == 2
    assert len(service.events(**scope)) == 2
    assert service.events(**scope)[0]["note_changed"] == 1
    assert "Confidential" not in repr(service.events(**scope))
    assert service.get(**call(service, viewer, org, saved_id))["stage"] == "submitted"
    with pytest.raises(WorkflowDenied):
        service.update(**call(service, viewer, org, saved_id), stage="won", note="", expected_revision=2)
    with pytest.raises(WorkflowDenied):
        service.get(**call(service, bob, org, saved_id))
    with pytest.raises(WorkflowMissing):
        service.get(**call(service, alice, org, saved_id, company_id=74))
    with closing(db.connect()) as conn:
        with conn:
            conn.execute("DELETE FROM saved_opportunities WHERE id=?", (saved_id,))
        assert conn.execute("SELECT COUNT(*) FROM saved_opportunity_workflow_events").fetchone()[0] == 0
    db.close()


def test_lifecycle_refuses_unbounded_note_and_invalid_stage(tmp_path):
    db, alice, _, _, org, saved_id = fixture(tmp_path)
    svc = SavedTenderWorkflow(db)
    scope = call(svc, alice, org, saved_id)
    with pytest.raises(ValueError):
        svc.update(**scope, stage="fake", note="", expected_revision=0)
    with pytest.raises(ValueError):
        svc.update(**scope, stage="reviewing", note="x"*2001, expected_revision=0)
    assert svc.get(**scope)["revision"] == 0
    db.close()
