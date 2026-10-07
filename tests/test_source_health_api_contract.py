from app.api.organization_workflow_routes import (
    SourceHealthResponse,
    router,
)
from app.api.schemas import (
    SourceHealthItem,
    TenderDiscoveryResponse,
)


PREFIX = (
    "/api/v1/organizations/"
    "{organization_id}"
)


def _routes():
    result = set()

    for route in router.routes:
        for method in (
            route.methods
            or set()
        ):
            result.add(
                (
                    route.path,
                    method,
                )
            )

    return result


def test_source_health_route_registered():
    assert (
        PREFIX
        + "/discovery/source-health",
        "GET",
    ) in _routes()


def test_source_health_contract():
    assert set(
        SourceHealthItem.model_fields
    ) == {
        "source",
        "display_name",
        "transport",
        "jurisdictions",
        "languages",
        "homepage_url",
        "official",
        "enabled",
        "authentication_required",
        "state",
        "notice_count",
        "duration_ms",
        "error_type",
        "message",
    }

    assert set(
        SourceHealthResponse.model_fields
    ) == {
        "organization_id",
        "company_id",
        "company_name",
        "history_id",
        "last_checked",
        "sources",
    }


def test_legacy_discovery_snapshot_remains_valid():
    response = (
        TenderDiscoveryResponse
        .model_validate(
            {
                "items": [],
                "attempted_sources": [
                    "ted",
                ],
                "successful_sources": [
                    "ted",
                ],
                "failed_sources": [],
                "partial_failure": False,
                "total_failure": False,
                "history_id": 1,
            }
        )
    )

    assert (
        response.source_statuses
        == []
    )
