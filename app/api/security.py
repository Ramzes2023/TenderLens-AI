"""Authentication and API-key access helpers for TenderLens HTTP routes."""

from __future__ import annotations

import asyncio
import secrets

from fastapi import HTTPException, Request, status
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
SESSION_COOKIE = "tenderlens_session"


async def require_api_key(request: Request, supplied_key: str | None = None) -> None:
    configured = request.app.state.api_settings.api_key
    if configured is None:
        return
    if supplied_key is None or not secrets.compare_digest(supplied_key, configured):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
        )


async def current_account(request: Request, *, touch: bool = True):
    runtime = getattr(request.app.state, "runtime", None)
    service = getattr(runtime, "auth_service", None)
    if service is None:
        return None
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    try:
        return await asyncio.to_thread(service.account_for_token, token, touch=touch)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication storage is unavailable.",
        ) from None


async def require_api_or_session(request: Request, supplied_key: str | None = None):
    account = await current_account(request)
    if account is not None:
        return account
    await require_api_key(request, supplied_key)
    return None


async def resolve_owner(request: Request, requested_owner_user_id: int | None) -> int | None:
    account = await current_account(request, touch=False)
    if account is None:
        return requested_owner_user_id

    owner_user_id = int(account.owner_user_id)
    if requested_owner_user_id is not None and int(requested_owner_user_id) != owner_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account cannot access the requested owner.",
        )
    return owner_user_id


__all__ = [
    "SESSION_COOKIE",
    "api_key_header",
    "current_account",
    "require_api_key",
    "require_api_or_session",
    "resolve_owner",
]
