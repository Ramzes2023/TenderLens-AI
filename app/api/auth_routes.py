"""Web account authentication routes for VALYQON AI."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.auth import (
    AuthAccount,
    InvalidCredentials,
    RegistrationError,
    TelegramLinkError,
    TelegramLinkUnavailable,
)

from .security import (
    SESSION_COOKIE,
    LoginRateLimiter,
    require_same_origin_browser_request,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class AccountResponse(BaseModel):
    id: int
    email: str
    owner_user_id: int
    is_active: bool
    created_at: str
    telegram_connected: bool


class TelegramLinkResponse(BaseModel):
    start_parameter: str
    expires_at: str


def _service(request: Request):
    service = getattr(request.app.state.runtime, "auth_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is unavailable.",
        )
    return service


def _account_response(account: AuthAccount) -> AccountResponse:
    from app.auth.repository import WEB_OWNER_OFFSET
    return AccountResponse(
        id=account.id,
        email=account.email,
        owner_user_id=account.owner_user_id,
        is_active=account.is_active,
        created_at=account.created_at,
        telegram_connected=0 < account.owner_user_id < WEB_OWNER_OFFSET,
    )


def _session_token(request: Request) -> str | None:
    return request.cookies.get(SESSION_COOKIE)


def _set_session_cookie(request: Request, response: Response, token: str, session_days: int) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=int(session_days) * 24 * 60 * 60,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"


def _limiter(request: Request) -> LoginRateLimiter:
    limiter = getattr(request.app.state, "login_rate_limiter", None)
    if limiter is None:
        limiter = LoginRateLimiter()
        request.app.state.login_rate_limiter = limiter
    return limiter


def _rate_limited(retry_after: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many login attempts. Try again later.",
        headers={"Retry-After": str(max(1, int(retry_after)))},
    )


@router.post("/register", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, request: Request, response: Response) -> AccountResponse:
    require_same_origin_browser_request(request)
    service = _service(request)
    try:
        account = await asyncio.to_thread(service.register, payload.email, payload.password)
        token = await asyncio.to_thread(service.create_session, account)
    except RegistrationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from None
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication storage is unavailable.",
        ) from None

    _set_session_cookie(request, response, token, service.session_days)
    return _account_response(account)


@router.post("/login", response_model=AccountResponse)
async def login(payload: LoginRequest, request: Request, response: Response) -> AccountResponse:
    require_same_origin_browser_request(request)
    service = _service(request)
    limiter = _limiter(request)
    key = limiter.key(request, payload.email)
    retry_after = limiter.retry_after(key)
    if retry_after is not None:
        raise _rate_limited(retry_after)

    try:
        account = await asyncio.to_thread(service.authenticate, payload.email, payload.password)
    except InvalidCredentials:
        retry_after = limiter.record_failure(key)
        if retry_after is not None:
            raise _rate_limited(retry_after)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        ) from None
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication storage is unavailable.",
        ) from None

    limiter.reset(key)
    try:
        token = await asyncio.to_thread(service.create_session, account)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication storage is unavailable.",
        ) from None

    _set_session_cookie(request, response, token, service.session_days)
    return _account_response(account)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response) -> None:
    require_same_origin_browser_request(request)
    service = _service(request)
    token = _session_token(request)
    try:
        await asyncio.to_thread(service.logout, token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication storage is unavailable.",
        ) from None

    response.delete_cookie(
        key=SESSION_COOKIE,
        path="/",
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"
    return None


@router.post("/telegram-link", response_model=TelegramLinkResponse)
async def create_telegram_link(
    request: Request,
    response: Response,
) -> TelegramLinkResponse:
    require_same_origin_browser_request(request)
    service = _service(request)
    session_token = _session_token(request)
    try:
        account = await asyncio.to_thread(service.account_for_token, session_token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication storage is unavailable.",
        ) from None

    if account is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    try:
        token, expires_at = await asyncio.to_thread(
            service.create_telegram_link,
            account,
        )
    except TelegramLinkUnavailable:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram linking is temporarily unavailable.",
        ) from None
    except TelegramLinkError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from None

    response.headers["Cache-Control"] = "no-store"
    return TelegramLinkResponse(
        start_parameter=f"link_{token}",
        expires_at=expires_at,
    )


@router.get("/me", response_model=AccountResponse)
async def me(request: Request, response: Response) -> AccountResponse:
    service = _service(request)
    token = _session_token(request)
    try:
        account = await asyncio.to_thread(service.account_for_token, token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication storage is unavailable.",
        ) from None

    if account is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    response.headers["Cache-Control"] = "no-store"
    return _account_response(account)


__all__ = ["router", "SESSION_COOKIE"]
