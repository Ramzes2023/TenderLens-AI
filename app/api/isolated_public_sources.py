"""Public-only procurement previews backed by an isolated connector database.

No production API, tenant account, AI, Telegram, email, merchant or tender
detail route is imported. The only persisted DB is the separate public-source
volume selected explicitly by the operator-only Compose profile.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from app.database.backend import Database
from app.database.config import parse_database_settings
from app.sources.opportunities import OpportunityRepository

from .guest_search_routes import router as guest_search_router
from .public_market_routes import router as market_pulse_router
from .public_intelligence_routes import router as market_intelligence_router
from .security import AuthRateLimiter, AuthRatePolicy


ISOLATED_SQLITE_URL = "sqlite:////app/data/isolated-public-sources.sqlite3"


def create_public_source_app(*, database_factory=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        if database_factory is None:
            if os.environ.get("VALYQON_ISOLATED_PUBLIC_SOURCES_ENABLED") != "true":
                raise RuntimeError("Isolated public sources not explicitly enabled.")
            if os.environ.get("DATABASE_URL") != ISOLATED_SQLITE_URL:
                raise RuntimeError("Isolated public source database location mismatch.")
            database = Database(parse_database_settings(ISOLATED_SQLITE_URL))
        else:
            # Only used by offline tests with a disposable injected DB.
            database = database_factory()
        try:
            OpportunityRepository(database).initialize()
            application.state.runtime = SimpleNamespace(database=database)
            yield
        finally:
            database.close()
            application.state.runtime = SimpleNamespace(database=None)

    app = FastAPI(
        title="VALYQON isolated public source previews",
        docs_url=None, redoc_url=None, openapi_url=None,
        lifespan=lifespan,
    )
    # Only this isolated, operator-approved feed hides expired archives.
    app.state.public_source_active_only = True
    app.state.guest_search_limiter = AuthRateLimiter(
        policies={"guest-search": AuthRatePolicy(24, 24, 60)},
        max_entries=8192,
    )
    app.include_router(guest_search_router)
    app.include_router(market_pulse_router)
    app.include_router(market_intelligence_router)

    @app.get("/_internal/health")
    def internal_health():
        database = getattr(app.state.runtime, "database", None)
        if database is None or not database.healthy():
            raise HTTPException(503, "Isolated public source store unavailable.")
        return JSONResponse(
            {"service": "valyqon-public-source-preview",
             "database": "isolated", "status": "ready"},
            headers={"Cache-Control": "no-store"},
        )

    return app


app = create_public_source_app()
