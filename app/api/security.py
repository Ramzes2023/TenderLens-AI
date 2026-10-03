"""Authentication, CSRF and API-key access helpers for TenderLens HTTP routes."""

from __future__ import annotations

import asyncio
import math
import secrets
import time
from collections import OrderedDict
from threading import Lock
from urllib.parse import urlsplit

from fastapi import HTTPException, Request, status
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
SESSION_COOKIE = "tenderlens_session"
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def _normalized_origin(value: str) -> tuple[str, str, int] | None:
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return None
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            return None
        if parsed.path not in {"", "/"}:
            return None
        port = parsed.port
    except ValueError:
        return None
    if port is None:
        port = 443 if parsed.scheme.lower() == "https" else 80
    return parsed.scheme.lower(), parsed.hostname.lower().rstrip("."), int(port)


def require_same_origin_browser_request(request: Request) -> None:
    """Reject explicit cross-site browser writes while preserving non-browser API clients."""
    if request.method.upper() in _SAFE_METHODS:
        return

    fetch_site = (request.headers.get("sec-fetch-site") or "").strip().lower()
    if fetch_site == "cross-site":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-origin session request blocked.",
        )

    origin = (request.headers.get("origin") or "").strip()
    if not origin:
        return

    supplied = _normalized_origin(origin)
    expected = _normalized_origin(str(request.base_url))
    if supplied is None or expected is None or supplied != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-origin session request blocked.",
        )


class LoginRateLimiter:
    """Small bounded in-memory limiter keyed by client + normalized email."""

    def __init__(
        self,
        *,
        max_failures: int = 5,
        window_seconds: int = 300,
        max_entries: int = 4096,
        clock=None,
    ):
        self.max_failures = max(2, int(max_failures))
        self.window_seconds = max(1, int(window_seconds))
        self.max_entries = max(16, int(max_entries))
        self._clock = clock or time.monotonic
        self._events: OrderedDict[str, list[float]] = OrderedDict()
        self._lock = Lock()

    @staticmethod
    def key(request: Request, email: str) -> str:
        host = getattr(getattr(request, "client", None), "host", None) or "unknown"
        normalized = (email or "").strip().lower()[:254]
        return f"{host}\0{normalized}"

    def _prune_locked(self, key: str, now: float) -> list[float]:
        events = self._events.get(key)
        if events is None:
            return []
        cutoff = now - self.window_seconds
        events[:] = [stamp for stamp in events if stamp > cutoff]
        if not events:
            self._events.pop(key, None)
            return []
        self._events.move_to_end(key)
        return events

    def _retry_after_locked(self, events: list[float], now: float) -> int | None:
        if len(events) < self.max_failures:
            return None
        remaining = self.window_seconds - (now - events[0])
        return max(1, int(math.ceil(remaining)))

    def retry_after(self, key: str) -> int | None:
        now = float(self._clock())
        with self._lock:
            events = self._prune_locked(key, now)
            return self._retry_after_locked(events, now)

    def record_failure(self, key: str) -> int | None:
        now = float(self._clock())
        with self._lock:
            events = self._prune_locked(key, now)
            if not events:
                if len(self._events) >= self.max_entries:
                    self._events.popitem(last=False)
                events = []
                self._events[key] = events
            events.append(now)
            self._events.move_to_end(key)
            return self._retry_after_locked(events, now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)


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
        require_same_origin_browser_request(request)
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
    "LoginRateLimiter",
    "api_key_header",
    "current_account",
    "require_api_key",
    "require_api_or_session",
    "require_same_origin_browser_request",
    "resolve_owner",
]
