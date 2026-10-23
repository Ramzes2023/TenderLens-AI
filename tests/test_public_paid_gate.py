"""Before billing, public source-detail access must fail CLOSED at server boundary.

These tests exercise all public routes in source-data API families, including
unauthenticated calls and users trying direct URLs. This is a prelaunch gate,
NOT proof that a real subscription service or webhook exists.
"""
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.api.runtime import ApiRuntime
from app.api.paid_content_gate import requires_verified_paid_entitlement


RESTRICTED = (
    "/api/v1/monitoring/scan",
    "/api/v1/monitoring/status",
    "/api/v1/organizations/6/discover/tenders",
    "/api/v1/organizations/6/discovery/history",
    "/api/v1/organizations/6/discovery/history/99",
    "/api/v1/organizations/6/discovery/source-health",
    "/api/v1/organizations/6/shortlist",
    "/api/v1/organizations/6/shortlist/export",
    "/api/v1/organizations/6/shortlist/3/workflow",
    "/api/v1/organizations/6/shortlist/3/workflow/events",
    "/api/v1/organizations/6/activity",
    "/api/v1/organizations/6/monitoring/scan",
    "/api/v1/organizations/6/monitoring/status",
    "/api/v1/organizations/6/scoring/evaluate",
    "/api/v1/organizations/6/companies/23/discovery/history-page",
    "/api/v1/organizations/6/companies/23/discovery/history-snapshots",
    "/api/v1/organizations/6/companies/23/analytics/v1/history/rows",
    "/api/v1/organizations/6/companies/23/scoring/runs",
    "/api/v1/organizations/6/companies/23/scoring/runs/77",
)
SAFE = (
    "/", "/register", "/login",
    "/api/v1/public/opportunities",
    "/api/v1/public/market-pulse",
    "/api/v1/organizations/6/billing",
    "/api/v1/organizations/6/companies",
    "/api/v1/organizations/6/companies/4",
    "/api/v1/tenders/1",
    "/api/v1/organizations/6/tenders/1",
    "/api/v1/support/tickets",
)


def test_public_source_data_route_groups_are_locked():
    assert all(requires_verified_paid_entitlement(route) for route in RESTRICTED)
    assert not any(requires_verified_paid_entitlement(route) for route in SAFE)
    assert not requires_verified_paid_entitlement("/api/v1/organizations/invalid/shortlist")


def test_opted_in_launch_denies_even_direct_authenticated_detail_paths(monkeypatch):
    monkeypatch.setenv("VALYQON_RESTRICT_PAID_SOURCE_DETAILS", "true")
    with TestClient(create_app(runtime=ApiRuntime())) as client:
        for route in RESTRICTED:
            # Read requests to both real and candidate sensitive API paths:
            result = client.get(route)
            assert result.status_code == 403, (route, result.status_code)
            assert result.json()["code"] == "PAID_SOURCE_DETAILS_LOCKED"
            assert result.headers["cache-control"] == "private, no-store"
        response = client.post("/api/v1/organizations/6/discover/tenders", json={})
        assert response.status_code == 403
        assert client.get("/").status_code == 200
        assert client.get("/api/v1/organizations/6/tenders/1").status_code != 403 or (
            client.get("/api/v1/organizations/6/tenders/1").json().get("code") != "PAID_SOURCE_DETAILS_LOCKED"
        )


def test_local_existing_operations_unchanged_when_guard_not_enabled(monkeypatch):
    monkeypatch.delenv("VALYQON_RESTRICT_PAID_SOURCE_DETAILS", raising=False)
    with TestClient(create_app(runtime=ApiRuntime())) as client:
        # No session => existing auth behavior, not the commercial launch gate.
        response = client.get("/api/v1/organizations/6/discovery/history")
        assert response.status_code in {401, 403, 404, 409, 503}
        assert response.json().get("code") != "PAID_SOURCE_DETAILS_LOCKED"
