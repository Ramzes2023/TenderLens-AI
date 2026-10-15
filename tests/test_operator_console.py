"""Read-only operator authorization/HTML regression; no real customer data."""
import hashlib
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api import operator_routes as routes

EMAIL = "readonly.operator@example.test"
IDENTITY = {
    "VALYQON_OPERATOR_PANEL_ENABLED": "1",
    "VALYQON_SUPERADMIN_ACCOUNT_ID": "11",
    "VALYQON_SUPERADMIN_EMAIL_SHA256": hashlib.sha256(EMAIL.encode()).hexdigest(),
}


def account(**changes):
    value = {"id": 11, "email": EMAIL, "is_active": True, "email_verified": True}
    value.update(changes)
    return SimpleNamespace(**value)


def test_feature_closed_unless_exact_id_digest_and_verified_session():
    assert not routes.authorized(account(), {})
    assert routes.authorized(account(), IDENTITY)
    assert not routes.authorized(account(id=12), IDENTITY)
    assert not routes.authorized(account(email="impostor@example.test"), IDENTITY)
    assert not routes.authorized(account(email_verified=False), IDENTITY)
    assert not routes.authorized(account(is_active=False), IDENTITY)
    assert not routes.authorized(account(), {**IDENTITY, "VALYQON_SUPERADMIN_EMAIL_SHA256": "not-a-hash"})
    assert not routes.authorized(account(), {**IDENTITY, "VALYQON_SUPERADMIN_ACCOUNT_ID": "-11"})
    assert not routes.authorized(account(), {"VALYQON_SUPPORT_OPERATOR_EMAILS": EMAIL})


class FakeCursor:
    def __init__(self, amount):
        self.amount = amount

    def fetchone(self):
        return (self.amount,)


class FakeConnection:
    def __init__(self, fail=False):
        self.queries = []
        self.closed = False
        self.fail = fail

    def execute(self, sql):
        self.queries.append(sql)
        if self.fail:
            raise RuntimeError("secret=never-reflect")
        return FakeCursor(10 + len(self.queries))

    def close(self):
        self.closed = True


class FakeDatabase:
    def __init__(self, fail=False):
        self.connection = FakeConnection(fail=fail)

    def connect(self):
        return self.connection


def test_overview_performs_only_readonly_aggregates_and_closes():
    database = FakeDatabase()
    snapshot = routes.overview(database)
    assert set(snapshot) == set(routes.FIELDS)
    assert database.connection.closed
    assert all(sql.startswith("SELECT COUNT(") for sql in database.connection.queries)
    assert all(type(v) is int for v in snapshot.values())


def client(monkeypatch, actor, *, fail=False):
    async def current_account(_request, *, touch=False):
        assert touch is False
        return actor
    monkeypatch.setattr(routes, "current_account", current_account)
    app = FastAPI()
    app.state.runtime = SimpleNamespace(database=FakeDatabase(fail=fail))
    app.include_router(routes.router)
    return TestClient(app)


def test_default_disabled_is_404_even_with_active_session(monkeypatch):
    for name in IDENTITY:
        monkeypatch.delenv(name, raising=False)
    c = client(monkeypatch, account())
    assert c.get("/operator").status_code == 404
    assert c.get("/api/v1/operator/overview").status_code == 404


def test_login_and_wrong_operator_identity_blocked(monkeypatch):
    for k, v in IDENTITY.items():
        monkeypatch.setenv(k, v)
    c = client(monkeypatch, None)
    assert c.get("/operator").status_code == 401
    c = client(monkeypatch, account(email="another@example.test"))
    assert c.get("/operator").status_code == 403
    assert c.get("/api/v1/operator/overview").status_code == 403


def test_verified_operator_reads_no_pii_and_no_cache(monkeypatch):
    for k, v in IDENTITY.items():
        monkeypatch.setenv(k, v)
    c = client(monkeypatch, account())
    page = c.get("/operator")
    assert page.status_code == 200
    assert "Operator overview" in page.text
    assert "Subscriber" not in page.text
    assert EMAIL not in page.text
    assert "no-store" in page.headers["cache-control"]
    assert page.headers["x-frame-options"] == "DENY"
    assert "default-src 'none'" in page.headers["content-security-policy"]
    api = c.get("/api/v1/operator/overview")
    assert api.status_code == 200
    assert api.json()["billing_controls"] == "not_implemented"
    assert api.json()["scope"] == "aggregate_only"
    assert set(api.json()["counts"]) == set(routes.FIELDS)
    assert EMAIL not in api.text


def test_storage_failure_redacted_and_never_200(monkeypatch):
    for k, v in IDENTITY.items():
        monkeypatch.setenv(k, v)
    c = client(monkeypatch, account(), fail=True)
    error = c.get("/api/v1/operator/overview")
    assert error.status_code == 503
    assert "secret=never-reflect" not in error.text
