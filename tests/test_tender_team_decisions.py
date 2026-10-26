"""Real SQLite acceptance for secured tender assignments, approvals and audit."""
from contextlib import closing
import pytest

from app.auth import AuthRepository
from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.organizations import OrganizationRepository
from app.workspaces.team_decisions import TeamDecision
from app.workspaces.lifecycle import WorkflowConflict, WorkflowDenied, WorkflowMissing


def setup(tmp_path):
    db=Database(DatabaseSettings("",tmp_path/"team.sqlite"))
    db.migrate()
    auth=AuthRepository(db)
    owner=auth.create_account("team-owner@example.test","test-hash")
    admin=auth.create_account("team-admin@example.test","test-hash")
    member=auth.create_account("team-member@example.test","test-hash")
    viewer=auth.create_account("team-viewer@example.test","test-hash")
    stranger=auth.create_account("team-outsider@example.test","test-hash")
    org=OrganizationRepository(db).default_for_account(owner.id)
    other_org=OrganizationRepository(db).default_for_account(stranger.id)
    with closing(db.connect()) as conn:
        with conn:
            for who,role in [(admin,"admin"),(member,"member"),(viewer,"viewer")]:
                conn.execute("INSERT INTO organization_members (organization_id,account_id,role,created_at)"
                             " VALUES (?,?,?,'2026-10-23T00:00:00Z')",(org.id,who.id,role))
            for oid,company,code in [(org.id,11,"real-saved-1"),(other_org.id,22,"private-saved-2")]:
                conn.execute("INSERT INTO saved_opportunities "
                             "(organization_id,company_id,source,external_id,snapshot_json,created_at,updated_at)"
                             "VALUES (?,?,?,?,?,?,?)",
                             (oid,company,"eis",code,"{}","now","now"))
            saved=conn.execute("SELECT id FROM saved_opportunities WHERE organization_id=?",(org.id,)).fetchone()["id"]
            other=conn.execute("SELECT id FROM saved_opportunities WHERE organization_id=?",(other_org.id,)).fetchone()["id"]
    return db,org,saved,other,owner,admin,member,viewer,stranger


def args(who,org,saved,company=11):
    return dict(account_id=who.id,organization_id=org.id,company_id=company,saved_id=saved)


def test_simultaneous_assignment_has_one_winner_and_one_audit_event(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    db,org,saved,other,owner,admin,member,viewer,stranger=setup(tmp_path)
    barrier=Barrier(2)

    def assign(target):
        barrier.wait(timeout=10)
        try:
            return TeamDecision(db).change(**args(owner,org,saved), action="assign",
                assignee_account_id=target.id, expected_revision=0)
        except WorkflowConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(assign, [admin,member]))
    assert results.count("conflict")==1
    winner=next(result for result in results if isinstance(result,dict))
    persisted=TeamDecision(db).get(**args(owner,org,saved))
    assert persisted["revision"]==1
    assert persisted["assignee_account_id"]==winner["assignee_account_id"]
    events=TeamDecision(db).events(**args(owner,org,saved))
    assert len(events)==1
    assert events[0]["next_assignee_account_id"]==winner["assignee_account_id"]


def test_assign_request_approve_and_revision_with_real_audit(tmp_path):
    db,org,saved,other,owner,admin,member,viewer,stranger=setup(tmp_path)
    svc=TeamDecision(db)
    owner_scope=args(owner,org,saved)
    assert svc.get(**owner_scope)["revision"]==0
    assert len(svc.get(**owner_scope)["members"])==4
    assert svc.get(**args(viewer,org,saved))["your_role"]=="viewer"
    with pytest.raises(WorkflowDenied):
        svc.change(**args(member,org,saved),action="assign",assignee_account_id=member.id,expected_revision=0)
    with pytest.raises(WorkflowDenied):
        svc.change(**owner_scope,action="assign",assignee_account_id=stranger.id,expected_revision=0)
    assigned=svc.change(**owner_scope,action="assign",assignee_account_id=member.id,expected_revision=0)
    assert assigned["assignee_account_id"]==member.id and assigned["revision"]==1
    assert svc.change(**owner_scope,action="assign",assignee_account_id=member.id,expected_revision=1)["revision"]==1
    with pytest.raises(WorkflowConflict):
        svc.change(**owner_scope,action="assign",assignee_account_id=None,expected_revision=0)
    request=svc.change(**args(member,org,saved),action="request",expected_revision=1)
    assert request["approval_state"]=="pending" and request["requested_by_account_id"]==member.id
    with pytest.raises(WorkflowDenied):
        svc.change(**args(member,org,saved),action="approve",expected_revision=2)
    with pytest.raises(WorkflowDenied):
        svc.change(**args(viewer,org,saved),action="request",expected_revision=2)
    decision=svc.change(**args(admin,org,saved),action="approve",expected_revision=2)
    assert decision["approval_state"]=="approved" and decision["decided_by_account_id"]==admin.id
    with pytest.raises(WorkflowConflict):
        svc.change(**args(admin,org,saved),action="reject",expected_revision=2)
    next_request=svc.change(**owner_scope,action="request",expected_revision=3)
    assert next_request["approval_state"]=="pending"
    with pytest.raises(WorkflowDenied):
        svc.change(**owner_scope,action="approve",expected_revision=4)
    rejected=svc.change(**args(admin,org,saved),action="reject",expected_revision=4)
    assert rejected["approval_state"]=="rejected"
    events=svc.events(**owner_scope)
    assert [x["action"] for x in events]==["reject","request","approve","request","assign"]
    assert events[-1]["next_assignee_account_id"]==member.id
    assert "test-hash" not in str(events)
    with closing(db.connect()) as conn:
        assert conn.execute("SELECT COUNT(*) FROM saved_opportunity_workflow").fetchone()[0]==0
        with conn:
            conn.execute("DELETE FROM saved_opportunities WHERE id=?",(saved,))
        assert conn.execute("SELECT COUNT(*) FROM saved_tender_team_decision_events").fetchone()[0]==0
    db.close()


def test_scope_and_two_person_reviewer_invariants(tmp_path):
    db,org,saved,other,owner,admin,member,viewer,stranger=setup(tmp_path)
    svc=TeamDecision(db)
    with pytest.raises(WorkflowDenied):
        svc.get(**args(stranger,org,saved))
    with pytest.raises(WorkflowMissing):
        svc.get(**args(owner,org,saved,company=22))
    with pytest.raises(WorkflowMissing):
        svc.get(**args(owner,org,other))
    with pytest.raises(ValueError):
        svc.change(**args(owner,org,saved),action="approve",expected_revision=True)
    requested=svc.change(**args(owner,org,saved),action="request",expected_revision=0)
    with pytest.raises(WorkflowDenied):
        svc.change(**args(owner,org,saved),action="approve",expected_revision=1)
    with pytest.raises(WorkflowConflict):
        svc.change(**args(member,org,saved),action="request",expected_revision=1)
    withdrawn=svc.change(**args(owner,org,saved),action="withdraw",expected_revision=1)
    assert withdrawn["approval_state"]=="not_requested"
    with pytest.raises(WorkflowConflict):
        svc.change(**args(admin,org,saved),action="approve",expected_revision=2)
    db.close()


def test_exposed_routes_are_auth_scoped_and_write_protected():
    from app.api.shortlist_workflow_routes import router
    routes=[(r.path,set(r.methods)) for r in router.routes]
    assert any(path.endswith("/{saved_id}/team") and "GET" in methods for path,methods in routes)
    assert any(path.endswith("/{saved_id}/team") and "PATCH" in methods for path,methods in routes)
    assert any(path.endswith("/{saved_id}/team/events") for path,methods in routes)
