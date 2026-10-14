"""Isolated composition using the real app, repositories, migrations and auth.

Only this preview entrypoint signs opaque sessions and disables external sources.
No production configuration flags or authentication bypasses are introduced.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import smtplib
from contextlib import asynccontextmanager
from dataclasses import replace

from fastapi import HTTPException, Request, Response
from fastapi.routing import APIRoute
from pydantic import BaseModel

from app.auth.service import AuthService


class PreviewRegistrationAccepted(BaseModel):
    accepted: bool = True
    email: str
    verification_required: bool = True


class SignedPreviewAuth(AuthService):
    """Add integrity to the existing expiring, DB-revocable opaque session."""

    def __init__(self, service, secret):
        if not secret or len(secret) < 32:
            raise ValueError("Preview signing secret must contain at least 32 characters.")
        super().__init__(service.repository, session_days=service.session_days)
        self._signing_key = secret.encode()

    def _signature(self, token):
        return hmac.new(self._signing_key, token.encode(), hashlib.sha256).hexdigest()

    def _unsigned(self, value):
        if not value or len(value) > 256:
            return None
        token, separator, signature = value.rpartition(".")
        if (not separator or len(signature) != 64
                or any(character not in "0123456789abcdef" for character in signature)
                or not hmac.compare_digest(signature, self._signature(token))):
            return None
        return token

    def create_session(self, account):
        token = super().create_session(account)
        return token + "." + self._signature(token)

    def account_for_token(self, token, *, touch=True):
        return super().account_for_token(self._unsigned(token), touch=touch)

    def logout(self, token):
        return super().logout(self._unsigned(token))


def configure_runtime(runtime, secret):
    from app.sources.catalog import SourceCatalog
    from app.sources.multi import MultiSourceFetcher
    from app.sources.registry import SourceRegistry

    if runtime.auth_service is not None:
        runtime.auth_service = SignedPreviewAuth(runtime.auth_service, secret)
    if runtime.source_catalog is not None:
        registry = SourceRegistry([
            replace(item, enabled=False)
            for item in runtime.source_catalog.registry.registrations()
        ])
        runtime.source_catalog = SourceCatalog(registry, MultiSourceFetcher(registry))
    runtime.provider = None
    runtime.rag_service = None
    runtime.rag_ingestion_service = None
    # Keep genuine persisted subscription/status reads working with zero feeds.
    # There is no background worker; catalog registrations are all disabled.
    if runtime.tender_discovery_service is not None:
        service = runtime.tender_discovery_service
        service.settings = replace(service.settings, enabled=False,
                                   profile_feeds_enabled=False, eis_rss_urls=())
        from app.sources.eis_rss import EisRssSource
        service.source = EisRssSource(urls=(), timeout=3, name="eis")
        runtime.monitoring_service = service
    runtime.component_errors.update({
        "llm": "External AI disabled in private preview",
        "rag": "Model downloads disabled in private preview",
        "monitoring": "External notifications and scans disabled in private preview",
        "discovery": "External sources disabled in private preview",
    })


def create_preview_app(runtime=None, secret=None):
    if runtime is None:
        # The Docker entrypoint uses this path; injected offline test runtimes
        # must not install a permanent process-wide hook in the test runner.
        from ops.private_preview.egress_guard import install
        install()
    # Must be set before importing create_app, whose module constructs its default app.
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    from app.api.config import ApiSettings
    from app.api.main import create_app
    from app.api.auth_routes import RegisterRequest, register

    app = create_app(runtime=runtime, settings=ApiSettings(
        host="0.0.0.0", port=8000, reload=False, api_key=None,
    ))
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with original_lifespan(application):
            configure_runtime(application.state.runtime, secret or os.environ.get("PREVIEW_APP_SECRET", ""))
            yield

    app.router.lifespan_context = lifespan
    # Registration has a generic acknowledgement for both new/existing accounts.
    # Never report verification_sent=true without actual delivery.
    app.router.routes = [route for route in app.router.routes if not (
        isinstance(route, APIRoute) and route.path == "/api/v1/auth/register"
    )]

    async def preview_register(payload, request: Request, response: Response):
        try:
            await register(payload, request, response)
        except HTTPException as error:
            if error.status_code != 422 or error.detail != "An account with this email already exists.":
                raise
            # A duplicate submission is only acknowledged. Explicit resend is
            # the sole recovery action; do not replace tickets or send extra mail.
        response.headers["Cache-Control"] = "no-store"
        return {"accepted": True, "email": payload.email.strip().lower(), "verification_required": True}

    # The model is imported lazily to keep dotenv/app startup inside the factory.
    # Bind its actual type before FastAPI resolves postponed endpoint annotations.
    preview_register.__annotations__["payload"] = RegisterRequest
    app.add_api_route("/api/v1/auth/register", preview_register, methods=["POST"],
                      status_code=201, response_model=PreviewRegistrationAccepted)
    # New FastAPI versions can retain include_router() as a deferred router,
    # rather than flat APIRoutes. Removing flat routes alone does not shadow it.
    # Match the preview endpoint first, without mutating the shared auth router.
    app.router.routes.insert(0, app.router.routes.pop())
    app.openapi_schema = None
    preview_route = app.router.routes[0]
    original_openapi = app.openapi

    def preview_openapi():
        from fastapi.openapi.utils import get_openapi
        schema = original_openapi()
        preview_schema = get_openapi(title=app.title, version=app.version,
                                     routes=[preview_route])
        # Deferred shared routers may also contribute this path to OpenAPI.
        # Document the actual first-match preview contract, including its model.
        schema["paths"]["/api/v1/auth/register"]["post"] = (
            preview_schema["paths"]["/api/v1/auth/register"]["post"]
        )
        schema.setdefault("components", {}).setdefault("schemas", {}).update(
            preview_schema.get("components", {}).get("schemas", {})
        )
        return schema

    app.openapi = preview_openapi

    @app.get("/private-preview/ready", include_in_schema=False)
    async def ready(request: Request):
        import asyncio
        active = request.app.state.runtime
        components = await asyncio.to_thread(active.component_status)
        required = ("database", "auth", "companies", "organizations", "support")
        if any(components.get(key) != "ready" for key in required) or active.email_sender is None:
            raise HTTPException(503, "Private preview services unavailable.")

        def smtp_ready():
            sender = active.email_sender
            # Check a real Mailpit SMTP handshake, not a static ready flag.
            with smtplib.SMTP(sender.host, sender.port, timeout=3) as smtp:
                if smtp.ehlo()[0] != 250:
                    raise RuntimeError
        try:
            await asyncio.to_thread(smtp_ready)
        except Exception:
            raise HTTPException(503, "Private mailbox unavailable.") from None
        return {"status": "ready", "email": "isolated SMTP capture", "external_integrations": "disabled"}

    return app
