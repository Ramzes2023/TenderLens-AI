"""Small API-key guard for non-public API routes."""
from __future__ import annotations

import secrets

from fastapi import HTTPException, Request, status
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(request: Request, supplied_key: str | None = None) -> None:
    configured = request.app.state.api_settings.api_key
    if configured is None:
        return
    if supplied_key is None or not secrets.compare_digest(supplied_key, configured):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
        )
