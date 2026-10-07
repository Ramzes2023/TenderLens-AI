"""Authentication, CSRF and API-key access helpers for VALYQON AI HTTP routes."""

from __future__ import annotations

import asyncio
import math
import secrets
import time
from collections import OrderedDict
from dataclasses import dataclass
from hashlib import sha256
from types import MappingProxyType
from threading import Lock
from urllib.parse import urlsplit

from fastapi import HTTPException, Request, status
from fastapi.security import APIKeyHeader

from app.tenancy import is_organization_owner_id

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


# Policies are process-local: multiple workers each enforce their own budgets.


@dataclass(frozen=True)
class AuthRatePolicy:
    client_limit: int
    identifier_limit: int
    window_seconds: int = 300


AUTH_RATE_POLICIES = MappingProxyType({
    "login": AuthRatePolicy(60, 5),
    "register": AuthRatePolicy(30, 10, 900),
    "forgot-password": AuthRatePolicy(30, 6, 900),
    "resend-verification": AuthRatePolicy(30, 6, 900),
    "verify-email": AuthRatePolicy(60, 10),
    "reset-password": AuthRatePolicy(60, 10),
    "telegram-link": AuthRatePolicy(30, 10),
})


class AuthRateLimiter:
    """Atomic sliding-window admission with bounded, hash-only identifier state.

    Full storage fails closed until an entry expires; live buckets are never
    evicted, so identifier churn cannot erase an existing abuse budget.
    Denied requests do not extend windows. Cleanup runs on every operation.
    """

    def __init__(self, *, policies=None, max_entries=4096, clock=None):
        self.policies = MappingProxyType(dict(
            AUTH_RATE_POLICIES if policies is None else policies
        ))
        if max_entries < 2 or any(
            min(p.client_limit, p.identifier_limit, p.window_seconds) < 1
            for p in self.policies.values()
        ):
            raise ValueError("Invalid authentication rate limit configuration")
        self.max_entries = int(max_entries)
        self._clock = clock or time.monotonic
        self._events: OrderedDict[tuple[str, str, str], list[float]] = OrderedDict()
        self._lock = Lock()

    @staticmethod
    def fingerprint(value: str) -> str:
        return sha256(value.encode("utf-8")).hexdigest()

    def keys(self, route, client, identifier, *, email=False):
        if email:
            identifier = identifier.strip().lower()
        return (
            (route, "client", self.fingerprint(client)),
            (route, "identifier", self.fingerprint(identifier)),
        )

    def _cleanup_locked(self, now):
        for key in list(self._events):
            cutoff = now - self.policies[key[0]].window_seconds
            events = self._events[key]
            events[:] = [stamp for stamp in events if stamp > cutoff]
            if not events:
                del self._events[key]

    def _retry_locked(self, key, limit, now):
        events = self._events.get(key, [])
        if len(events) < limit:
            return None
        return max(1, math.ceil(
            events[0] + self.policies[key[0]].window_seconds - now
        ))

    def consume(self, route, client, identifier, *, email=False):
        keys = self.keys(route, client, identifier, email=email)
        policy = self.policies[route]
        with self._lock:
            now = float(self._clock())
            self._cleanup_locked(now)
            retries = [self._retry_locked(key, limit, now) for key, limit in zip(
                keys, (policy.client_limit, policy.identifier_limit)
            )]
            missing = sum(key not in self._events for key in keys)
            if len(self._events) + missing > self.max_entries:
                # Earliest expiry that can free capacity; generic public response.
                retries.append(max(1, math.ceil(min(
                    events[-1] + self.policies[key[0]].window_seconds
                    for key, events in self._events.items()
                ) - now)))
            if any(retries):
                return max(retry for retry in retries if retry is not None)
            for key in keys:
                self._events.setdefault(key, []).append(now)
            return None

    def identifier_retry_after(self, route, client, identifier, *, email=False):
        key = self.keys(route, client, identifier, email=email)[1]
        with self._lock:
            now = float(self._clock())
            self._cleanup_locked(now)
            return self._retry_locked(key, self.policies[route].identifier_limit, now)

    def login_succeeded(self, client, email):
        # Relax only this email; successful credentials cannot clear IP pressure.
        key = self.keys("login", client, email, email=True)[1]
        with self._lock:
            self._events.pop(key, None)


class LoginRateLimiter(AuthRateLimiter):
    """Compatibility constructor for the former login-only limiter."""

    def __init__(self, *, max_failures=5, window_seconds=300,
                 max_entries=4096, clock=None):
        policies = dict(AUTH_RATE_POLICIES)
        policies["login"] = AuthRatePolicy(60, max(2, int(max_failures)),
                                           max(1, int(window_seconds)))
        super().__init__(policies=policies, max_entries=max_entries, clock=clock)


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
        if (
            requested_owner_user_id is not None
            and is_organization_owner_id(requested_owner_user_id)
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Reserved organization owner namespace.",
            )

        return requested_owner_user_id

    owner_user_id = int(account.owner_user_id)

    if is_organization_owner_id(owner_user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Reserved organization owner namespace.",
        )

    if requested_owner_user_id is not None and int(requested_owner_user_id) != owner_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account cannot access the requested owner.",
        )

    return owner_user_id


__all__ = [
    "SESSION_COOKIE",
    "LoginRateLimiter",
    "AuthRateLimiter",
    "AuthRatePolicy",
    "AUTH_RATE_POLICIES",
    "api_key_header",
    "current_account",
    "require_api_key",
    "require_api_or_session",
    "require_same_origin_browser_request",
    "resolve_owner",
]
