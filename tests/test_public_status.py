"""Public uptime surface does not claim live procurement or deliveries."""
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.api.runtime import ApiRuntime


class Database:
    def __init__(self, healthy=True):
        self.ok = healthy
        self.calls = 0

    def healthy(self):
        self.calls += 1
        return self.ok


def test_status_checks_database_but_not_sources():
    db = Database()
    runtime = ApiRuntime(database=db, source_catalog=object(), email_sender=object())
    with TestClient(create_app(runtime=runtime)) as client:
        result = client.get("/status.json")
        assert result.status_code == 200
        data = result.json()
        assert data["overall"] == "partial"
        assert data["uptime_percent"] is None
        states = {c["id"]: c["state"] for c in data["components"]}
        assert states == {
            "http": "operational", "database": "operational",
            "sources": "unverified", "alerts": "unverified",
            "payments": "not_enabled",
        }
        assert db.calls == 1
        assert result.headers["cache-control"].startswith("no-store")
        html = client.get("/status")
        assert html.status_code == 200
        assert "Unverified" in html.text and "No historical uptime" in html.text
        assert "http-equiv" not in html.text
        assert html.headers["x-frame-options"] == "DENY"


def test_db_failure_degrades_status_and_never_uses_false_success():
    db = Database(False)
    with TestClient(create_app(runtime=ApiRuntime(database=db))) as client:
        response = client.get("/status.json")
        assert response.json()["overall"] == "degraded"
        assert response.json()["components"][1]["state"] == "degraded"


def test_no_database_is_not_a_green_state():
    with TestClient(create_app(runtime=ApiRuntime())) as client:
        response = client.get("/status.json")
        assert response.json()["components"][1]["state"] == "degraded"
