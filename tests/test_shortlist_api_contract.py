from app.api.organization_workflow_routes import (
    SavedOpportunityResponse,
    router,
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


def test_shortlist_routes_are_registered():
    routes = _route_methods()

    assert (
        PREFIX + "/shortlist",
        "GET",
    ) in routes

    assert (
        PREFIX + "/shortlist",
        "POST",
    ) in routes

    assert (
        PREFIX
        + "/shortlist/{saved_id}",
        "DELETE",
    ) in routes


def test_shortlist_response_contract():
    fields = (
        SavedOpportunityResponse
        .model_fields
    )

    assert set(fields) == {
        "id",
        "organization_id",
        "company_id",
        "opportunity",
        "created_at",
        "updated_at",
    }
