"""Actual FastAPI handler calls with independent SQLite, authentication stubs and RBAC.

The database authorization is NOT mocked. Only the authenticated account/active
company selection is replaced with scoped test identities. No production data.
"""
import asyncio
import json
from contextlib import closing
from types import SimpleNamespace

from fastapi import HTTPException
from app.auth import AuthRepository
from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.organizations import OrganizationRepository
import app.api.shortlist_workflow_routes as routes


def test_team_handlers_persist_real_decisions_with_origin_checks(monkeypatch,tmp_path):
    db=Database(DatabaseSettings("",tmp_path/"http-decisions.sqlite"))
    db.migrate()
    auth=AuthRepository(db)
    owner=auth.create_account("api-team-owner@example.test","hash")
    admin=auth.create_account("api-team-admin@example.test","hash")
    stranger=auth.create_account("api-team-outsider@example.test","hash")
    org=OrganizationRepository(db).default_for_account(owner.id)
    with closing(db.connect()) as conn:
        with conn:
            conn.execute("INSERT INTO organization_members(organization_id,account_id,role,created_at) "
                         "VALUES (?,?,?,?)",(org.id,admin.id,"admin","now"))
            conn.execute("INSERT INTO saved_opportunities "
                "(organization_id,company_id,source,external_id,snapshot_json,created_at,updated_at)"
                " VALUES (?,?,?,?,?,?,?)",(org.id,71,"eis","proof-1","{}","now","now"))
            saved=conn.execute("SELECT id FROM saved_opportunities").fetchone()[0]
    current=[owner]
    origins=[]
    async def account(request):return current[0]
    async def company(request,account,organization_id):return SimpleNamespace(id=71)
    monkeypatch.setattr(routes,"_account",account)
    monkeypatch.setattr(routes,"_active_company",company)
    monkeypatch.setattr(routes,"require_same_origin_browser_request",lambda request:origins.append(True))
    request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(runtime=SimpleNamespace(database=db))))
    run=lambda coroutine:asyncio.run(coroutine)
    kwargs=dict(organization_id=org.id,saved_id=saved,request=request)
    initial=json.loads(run(routes.get_team(**kwargs)).body)
    assert initial["revision"]==0 and initial["approval_state"]=="not_requested"
    assignment=routes.TeamAction(action="assign",expected_revision=0,assignee_account_id=admin.id)
    assigned=json.loads(run(routes.update_team(**kwargs,payload=assignment)).body)
    assert assigned["assignee_account_id"]==admin.id and assigned["revision"]==1
    request_decision=routes.TeamAction(action="request",expected_revision=1)
    result=json.loads(run(routes.update_team(**kwargs,payload=request_decision)).body)
    assert result["approval_state"]=="pending"
    try:
        run(routes.update_team(**kwargs,payload=routes.TeamAction(action="approve",expected_revision=2)))
        raise AssertionError("Self-approval must be denied")
    except HTTPException as exc:
        assert exc.status_code==403
    current[0]=admin
    approved=json.loads(run(routes.update_team(**kwargs,payload=routes.TeamAction(action="approve",expected_revision=2))).body)
    assert approved["approval_state"]=="approved"
    events=json.loads(run(routes.team_events(**kwargs)).body)
    assert [x["action"] for x in events]==["approve","request","assign"]
    assert len(origins)==4
    current[0]=stranger
    try:
        run(routes.get_team(**kwargs))
        raise AssertionError("Cross-tenant access must fail")
    except HTTPException as exc:
        assert exc.status_code==403
    db.close()
