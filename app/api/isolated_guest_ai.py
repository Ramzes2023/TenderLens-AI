"""DB-disconnected, product-only VALYQON guest AI sidecar.

This is NOT the production API app. It creates no database, no migrations,
no auth, no source connectors, no worker, and no application file storage.
Expose it only through a reviewed exact-path reverse proxy rule.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, Callable

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.llm.base import LLMError
from app.llm.gateway import build_gateway

from .public_assistant_routes import router as product_help_router
from .security import AuthRateLimiter, AuthRatePolicy


def create_isolated_guest_app(
    provider_factory: Callable[[], Any] = build_gateway,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Fail closed when provider credentials, CA bundle or TLS are invalid.
        try:
            provider = provider_factory()
        except (LLMError, OSError, RuntimeError, ValueError):
            provider = None
        app.state.runtime = SimpleNamespace(provider=provider)
        try:
            yield
        finally:
            app.state.runtime = SimpleNamespace(provider=None)

    app = FastAPI(
        lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None
    )
    app.state.guest_ai_limiter = AuthRateLimiter(
        policies={
            "guest-ai": AuthRatePolicy(3, 3, 600),
            "guest-ai-global": AuthRatePolicy(48, 48, 86400),
        },
        max_entries=8192,
    )
    app.include_router(product_help_router)

    @app.get("/_internal/health")
    async def isolated_health():
        # Local container readiness ONLY, not a provider-inference assertion.
        configured = app.state.runtime.provider is not None
        return JSONResponse(
            {"service": "valyqon-guest-ai-only",
             "provider_initialized": configured,
             "provider_inference_verified": False},
            headers={"Cache-Control": "no-store"},
        )

    return app


app = create_isolated_guest_app()
