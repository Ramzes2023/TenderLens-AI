from app.api.organization_workflow_routes import (
    DiscoveryHistoryDetailResponse,
    DiscoveryHistorySummaryResponse,
    router,
)
from app.api.schemas import (
    TenderDiscoveryResponse,
)


PREFIX = (
    "/api/v1/organizations/"
    "{organization_id}"
)


def _route_methods():
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


def test_discovery_history_routes_registered():
    routes = _route_methods()

    assert (
        PREFIX
        + "/discovery/history",
        "GET",
    ) in routes

    assert (
        PREFIX
        + "/discovery/history/{history_id}",
        "GET",
    ) in routes


def test_discovery_response_exposes_history_id():
    assert (
        "history_id"
        in TenderDiscoveryResponse.model_fields
    )


def test_discovery_history_summary_contract():
    fields = (
        DiscoveryHistorySummaryResponse
        .model_fields
    )

    assert set(fields) == {
        "id",
        "organization_id",
        "company_id",
        "created_by_account_id",
        "result_count",
        "scored_count",
        "attempted_sources",
        "successful_sources",
        "failed_sources",
        "partial_failure",
        "total_failure",
        "created_at",
    }


def test_discovery_history_detail_contract():
    fields = (
        DiscoveryHistoryDetailResponse
        .model_fields
    )

    assert (
        "discovery"
        in fields
    )
