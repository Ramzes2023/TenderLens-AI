"""FastAPI application factory for VALYQON AI."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import mimetypes
import os

from app import __version__

from .config import ApiSettings, load_api_settings
from .auth_routes import router as auth_router
from .support_routes import router as support_router
from .operator_routes import router as operator_router
from .billing_routes import router as billing_router
from .guest_search_routes import router as guest_search_router
from .public_market_routes import router as public_market_router
from .public_intelligence_routes import router as public_intelligence_router
from .public_assistant_routes import router as public_assistant_router
from .operator_support_routes import router as operator_support_router
from .public_status_routes import router as public_status_router
from .organization_routes import router as organization_router
from .organization_company_routes import router as organization_company_router
from .organization_data_routes import router as organization_data_router
from .organization_workflow_routes import router as organization_workflow_router
from .scoring_run_routes import router as scoring_run_router
from .analytics_routes import router as analytics_router
from .launch_export_routes import router as launch_export_router
from .legal_routes import router as legal_router
from .deadline_alert_routes import router as deadline_alert_router
from .shortlist_workflow_routes import router as shortlist_workflow_router
from .saved_filter_routes import router as saved_filter_router
from .organization_activity_routes import router as organization_activity_router
from .routes import router
from .runtime import ApiRuntime, build_runtime
from .security import LoginRateLimiter, AuthRateLimiter, AuthRatePolicy
from .paid_content_gate import block_paid_details_before_billing


def create_app(runtime: ApiRuntime | None = None, settings: ApiSettings | None = None) -> FastAPI:
    api_settings = settings or load_api_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.api_settings = api_settings
        owns_runtime = runtime is None
        active_runtime = build_runtime() if owns_runtime else runtime
        app.state.runtime = active_runtime
        from app.analytics.admission import Admission
        app.state.analytics_admission = Admission(limit=2)
        try:
            yield
        finally:
            await app.state.analytics_admission.shutdown()
            if owns_runtime:
                active_runtime.close()

    app = FastAPI(
        title="VALYQON AI API",
        version=__version__,
        description=(
            "Tender intelligence backend: PDF analysis, deterministic scoring, "
            "semantic RAG, history and EIS monitoring."
        ),
        lifespan=lifespan,
    )
    from app.observability import RequestDiagnostics, telemetry
    app.state.telemetry = telemetry
    app.add_middleware(RequestDiagnostics)
    # Public marketing launch must not leak source details via older authenticated
    # endpoints before a verified merchant/subscription ledger is operational.
    # Opt-in to avoid altering local private preview or existing test workflows.
    if os.environ.get("VALYQON_RESTRICT_PAID_SOURCE_DETAILS", "").strip().lower() in {"1", "true"}:
        app.middleware("http")(block_paid_details_before_billing)
    # Windows may otherwise serve GeoJSON as application/octet-stream.
    mimetypes.add_type("application/geo+json", ".geojson")
    app.mount("/assets", StaticFiles(directory=Path(__file__).parent / "static"), name="assets")
    app.state.login_rate_limiter = LoginRateLimiter()
    app.state.guest_search_limiter = AuthRateLimiter(
        policies={"guest-search": AuthRatePolicy(24, 24, 60)}, max_entries=8192
    )
    app.state.guest_ai_limiter = AuthRateLimiter(
        policies={"guest-ai": AuthRatePolicy(3, 3, 600)}, max_entries=8192
    )
    app.include_router(auth_router)
    app.include_router(support_router)
    app.include_router(operator_router)
    app.include_router(billing_router)
    app.include_router(guest_search_router)
    app.include_router(public_market_router)
    app.include_router(public_intelligence_router)
    app.include_router(public_assistant_router)
    app.include_router(operator_support_router)
    app.include_router(public_status_router)
    app.include_router(organization_router)
    app.include_router(organization_company_router)
    app.include_router(organization_workflow_router)
    app.include_router(scoring_run_router)
    app.include_router(analytics_router)
    app.include_router(launch_export_router)
    app.include_router(legal_router)
    app.include_router(deadline_alert_router)
    app.include_router(shortlist_workflow_router)
    app.include_router(saved_filter_router)
    app.include_router(organization_activity_router)
    app.include_router(organization_data_router)
    app.include_router(router)
    return app


app = create_app()
