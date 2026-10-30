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

# Public source flags are separate from the legacy main API's registry.
# A source disabled after a failed staged run must not remain discoverable
# merely because its isolated SQLite rows have not been deleted.
ISOLATED_SOURCES = (
    ("mikroton_tender", "MIKROTON_TENDER_ENABLED"),
    ("stan_commercial_public", "STAN_COMMERCIAL_PUBLIC_ENABLED"),
    ("south_ural_public", "SOUTH_URAL_PUBLIC_ENABLED"),
    ("kavkaz_rf_firstparty", "KAVKAZ_RF_FIRSTPARTY_ENABLED"),
    ("lenobl_small_public", "LENOBL_SMALL_PUBLIC_ENABLED"),
    ("ru_samara_public_list", "RU_SAMARA_PUBLIC_LIST_ENABLED"),
)


def approved_public_source_keys(environment):
    enabled = set()
    for source, flag in ISOLATED_SOURCES:
        value = environment.get(flag, "false")
        if value not in {"true", "false"}:
            raise RuntimeError("Invalid isolated source opt-in flag")
        if value == "true":
            enabled.add(source)
    # The original public publisher requires MikroTon + STAN. A separate
    # non-public, no-ingress RC may test STAN + Lenobl independently, but
    # must opt in explicitly and satisfy an exact no-send environment.
    rc = environment.get("VALYQON_STAN_LENOBL_RC_MODE", "false")
    if rc not in {"true", "false"}:
        raise RuntimeError("Invalid isolated release candidate mode")
    if rc == "true":
        if (enabled != {"stan_commercial_public", "lenobl_small_public"}
                or environment.get("VALYQON_ISOLATED_PUBLIC_SOURCES_ENABLED") != "true"
                or environment.get("DATABASE_URL") != ISOLATED_SQLITE_URL
                or environment.get("MONITORING_ENABLED") != "false"
                or environment.get("VALYQON_EMAIL_MODE") != "disabled"
                or environment.get("VALYQON_PUBLIC_AI_ENABLED") != "false"
                or environment.get("VALYQON_RU_BACKGROUND_CATALOG_ENABLED") != "false"
                or environment.get("TELEGRAM_BOT_TOKEN", "") != ""
                or environment.get("OUTBOUND_PROXY_URL", "") != ""):
            raise RuntimeError("Nonpublic STAN/Lenobl RC environment rejected")
    elif not {"mikroton_tender", "stan_commercial_public"}.issubset(enabled):
        raise RuntimeError("Mandatory base public source flags unavailable")
    return frozenset(enabled)


def create_public_source_app(*, database_factory=None, allowed_sources_for_tests=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        if database_factory is None:
            if os.environ.get("VALYQON_ISOLATED_PUBLIC_SOURCES_ENABLED") != "true":
                raise RuntimeError("Isolated public sources not explicitly enabled.")
            if os.environ.get("DATABASE_URL") != ISOLATED_SQLITE_URL:
                raise RuntimeError("Isolated public source database location mismatch.")
            application.state.public_source_allowed_keys = approved_public_source_keys(os.environ)
            database = Database(parse_database_settings(ISOLATED_SQLITE_URL))
        else:
            # Only used by offline tests with a disposable injected DB.
            database = database_factory()
            application.state.public_source_allowed_keys = allowed_sources_for_tests
        try:
            OpportunityRepository(database).initialize()
            application.state.runtime = SimpleNamespace(database=database)
            yield
        finally:
            database.close()
            application.state.runtime = SimpleNamespace(database=None)
            application.state.public_source_allowed_keys = None

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
