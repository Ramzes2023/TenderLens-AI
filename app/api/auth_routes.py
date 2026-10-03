"""Web account authentication routes for TenderLens."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.auth import AuthAccount, InvalidCredentials, RegistrationError

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
SESSION_COOKIE = "tenderlens_session"


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


def _service(request: Request):
    service = getattr(request.app.state.runtime, "auth_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is unavailable.",
        )
    return service


def _account_response(account: AuthAccount) -> AccountResponse:
    return AccountResponse(
        id=account.id,
        email=account.email,
        owner_user_id=account.owner_user_id,
        is_active=account.is_active,
        created_at=account.created_at,
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


@router.post("/register", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, request: Request, response: Response) -> AccountResponse:
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
    service = _service(request)
    try:
        account = await asyncio.to_thread(service.authenticate, payload.email, payload.password)
        token = await asyncio.to_thread(service.create_session, account)
    except InvalidCredentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        ) from None
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication storage is unavailable.",
        ) from None

    _set_session_cookie(request, response, token, service.session_days)
    return _account_response(account)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response) -> None:
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
