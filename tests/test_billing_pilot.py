"""Read-only billing view uses real tenant usage and refuses invented payments."""
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.api.runtime import ApiRuntime
from app.auth import AuthRepository
from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.api.billing_routes import billing_snapshot, BillingAccessDenied, BillingNeedsCompany


def fixture(tmp_path):
    db=Database(DatabaseSettings("",tmp_path/"billing.db"))
    db.migrate()
    auth=AuthRepository(db)
    owner=auth.create_account("bill-owner@example.test","synthetic")
    other=auth.create_account("bill-other@example.test","synthetic")
    with closing(db.connect()) as conn:
        with conn:
            conn.execute(
                "INSERT INTO organizations(name,created_at,updated_at,created_by_account_id) "
                "VALUES (?,?,?,?)",("Company Group","now","now",owner.id))
            org=conn.execute("SELECT id FROM organizations WHERE name='Company Group'").fetchone()[0]
            conn.execute("INSERT INTO organization_members(organization_id,account_id,role,created_at) "
                         "VALUES (?,?,?,?)",(org,owner.id,"owner","now"))
            conn.execute("INSERT INTO saved_opportunities "
                         "(organization_id,company_id,source,external_id,snapshot_json,created_at,updated_at) "
                         "VALUES (?,?,?,?,?,?,?)",(org,31,"eis","001","{}","now","now"))
    return db,owner,other,org


def test_billing_usage_is_real_and_never_fabricates_transactions(tmp_path):
    db,owner,other,org=fixture(tmp_path)
    result=billing_snapshot(db,owner.id,org)
    assert result["billing_status"]=="not_enabled"
    assert result["active_plan"] is None and result["next_charge_at"] is None
    assert result["payment_history"] == result["invoices"] == []
    assert result["upgrade_available"] is False
    assert result["usage"]["saved_opportunities"]==1
    assert result["usage"]["team_seats"]==1
    assert result["usage"]["recorded_searches"]==0
    with pytest.raises(BillingAccessDenied):
        billing_snapshot(db,other.id,org)
    db.close()


def test_billing_noncommercial_personal_organization_is_rejected(tmp_path):
    db,owner,other,org=fixture(tmp_path)
    from app.organizations import OrganizationRepository
    personal=OrganizationRepository(db).default_for_account(owner.id)
    with pytest.raises(BillingNeedsCompany):
        billing_snapshot(db,owner.id,personal.id)
    db.close()


def test_billing_requires_session_before_db_access():
    with TestClient(create_app(runtime=ApiRuntime())) as c:
        assert c.get("/api/v1/organizations/4/billing").status_code==401
