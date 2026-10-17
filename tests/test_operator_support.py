"""Operator support: read-only scoped tenant diagnostics and fail-closed flags."""
from contextlib import closing
import os

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.api.runtime import ApiRuntime
from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.auth import AuthRepository
from app.organizations import OrganizationRepository
from app.api.operator_support_routes import tenant_rows


def test_tenant_rows_real_sqlite_are_bounded_without_account_email_or_notes(tmp_path):
    db = Database(DatabaseSettings("", tmp_path / "operator.db"))
    db.migrate()
    auth = AuthRepository(db)
    a = auth.create_account("hidden-a@example.test", "synthetic")
    b = auth.create_account("hidden-b@example.test", "synthetic")
    org_a = OrganizationRepository(db).default_for_account(a.id)
    org_b = OrganizationRepository(db).default_for_account(b.id)
    with closing(db.connect()) as conn:
        with conn:
            conn.execute("INSERT INTO saved_opportunities "
                         "(organization_id,company_id,source,external_id,snapshot_json,created_at,updated_at) "
                         "VALUES (?,?,?,?,?,?,?)",
                         (org_a.id, 1, "eis", "secret-reference", '{"note":"secret"}', "now", "now"))
    first = tenant_rows(db, after_id=0)
    assert [x["id"] for x in first] == sorted([org_a.id, org_b.id])
    row = next(x for x in first if x["id"] == org_a.id)
    assert row["saved"] == 1 and row["subscription"] == "billing_not_implemented"
    assert "hidden-a" not in repr(first) and "secret-reference" not in repr(first)
    assert len(tenant_rows(db, after_id=org_a.id)) == 1
    db.close()


def test_tenant_route_not_exposed_when_feature_flag_disabled(monkeypatch):
    monkeypatch.delenv("VALYQON_OPERATOR_SUPPORT_ENABLED", raising=False)
    with TestClient(create_app(runtime=ApiRuntime())) as client:
        assert client.get("/operator/tenants").status_code == 404
        assert client.get("/api/v1/operator/tenants").status_code == 404


def test_enabled_support_still_requires_original_verified_operator_identity(monkeypatch):
    monkeypatch.setenv("VALYQON_OPERATOR_SUPPORT_ENABLED", "1")
    monkeypatch.setenv("VALYQON_OPERATOR_PANEL_ENABLED", "1")
    with TestClient(create_app(runtime=ApiRuntime())) as client:
        assert client.get("/api/v1/operator/tenants").status_code == 401
