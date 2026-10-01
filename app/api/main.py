"""FastAPI application factory for TenderLens AI."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__

from .config import ApiSettings, load_api_settings
from .routes import router
from .runtime import ApiRuntime, build_runtime


def create_app(runtime: ApiRuntime | None = None, settings: ApiSettings | None = None) -> FastAPI:
    api_settings = settings or load_api_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.api_settings = api_settings
        app.state.runtime = runtime or build_runtime()
        yield

    app = FastAPI(
        title="TenderLens AI API",
        version=__version__,
        description=(
            "Tender intelligence backend: PDF analysis, deterministic scoring, "
            "semantic RAG, history and EIS monitoring."
        ),
        lifespan=lifespan,
    )
    app.include_router(router)
    return app


app = create_app()
