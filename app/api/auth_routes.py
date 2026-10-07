"""Web account authentication routes for VALYQON AI."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field

from app.auth import (
    AuthAccount,
    EmailNotVerified,
    EmailVerificationError,
    EmailVerificationInvalid,
    InvalidCredentials,
    RegistrationError,
    PasswordResetError,
    PasswordResetInvalid,
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


class VerifyEmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(
        min_length=1,
        max_length=256,
    )


class ResendVerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(
        min_length=3,
        max_length=254,
    )


class RegistrationResponse(BaseModel):
    email: str
    verification_required: bool = True
    verification_sent: bool
    verification_expires_at: str | None


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=1, max_length=128)


class ForgotPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)


class PasswordResetAcceptedResponse(BaseModel):
    accepted: bool = True


class ResendVerificationResponse(BaseModel):
    accepted: bool = True


class AccountResponse(BaseModel):
    id: int
    email: str
    owner_user_id: int
    is_active: bool
    email_verified: bool
    email_verified_at: str | None
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
        email_verified=account.email_verified,
        email_verified_at=account.email_verified_at,
        created_at=account.created_at,
        telegram_connected=0 < account.owner_user_id < WEB_OWNER_OFFSET,
    )


def _email_sender(request: Request):
    return getattr(
        request.app.state.runtime,
        "email_sender",
        None,
    )


def _verification_url(
    sender,
    token: str,
) -> str:
    from urllib.parse import urlencode

    base = (
        str(sender.public_base_url)
        .strip()
        .rstrip("/")
    )

    query = urlencode(
        {
            "token": token,
            "next": "/dashboard",
        }
    )

    return (
        f"{base}/verify-email?"
        f"{query}"
    )


async def _send_verification(
    sender,
    *,
    recipient: str,
    token: str,
    expires_at: str,
) -> bool:
    if sender is None:
        return False

    try:
        await asyncio.to_thread(
            sender.send_verification,
            recipient=recipient,
            verification_url=(
                _verification_url(
                    sender,
                    token,
                )
            ),
            expires_at=expires_at,
        )
        return True

    except Exception:
        return False


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


@router.post(
    "/register",
    response_model=RegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
) -> RegistrationResponse:
    require_same_origin_browser_request(
        request
    )

    service = _service(
        request
    )

    sender = _email_sender(
        request
    )

    if sender is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email verification delivery is not configured.",
        )

    try:
        account = await asyncio.to_thread(
            service.register,
            payload.email,
            payload.password,
        )

        token, expires_at = (
            await asyncio.to_thread(
                service.issue_email_verification,
                account,
                enforce_cooldown=False,
            )
        )

    except RegistrationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from None

    except EmailVerificationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email verification is temporarily unavailable.",
        ) from None

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication storage is unavailable.",
        ) from None

    sent = await _send_verification(
        sender,
        recipient=account.email,
        token=token,
        expires_at=expires_at,
    )

    if not sent:
        try:
            await asyncio.to_thread(
                service.revoke_email_verification,
                token,
            )
        except EmailVerificationError:
            pass

    response.headers[
        "Cache-Control"
    ] = "no-store"

    return RegistrationResponse(
        email=account.email,
        verification_required=True,
        verification_sent=sent,
        verification_expires_at=(
            expires_at
            if sent
            else None
        ),
    )


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
        account = await asyncio.to_thread(
            service.authenticate,
            payload.email,
            payload.password,
        )

    except EmailNotVerified:
        limiter.reset(key)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required.",
        ) from None

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


@router.post(
    "/verify-email",
    response_model=AccountResponse,
)
async def verify_email(
    payload: VerifyEmailRequest,
    request: Request,
    response: Response,
) -> AccountResponse:
    require_same_origin_browser_request(
        request
    )

    service = _service(
        request
    )

    try:
        account = await asyncio.to_thread(
            service.verify_email,
            payload.token,
        )

        session_token = (
            await asyncio.to_thread(
                service.create_session,
                account,
            )
        )

    except EmailVerificationInvalid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Verification link is invalid or expired.",
        ) from None

    except EmailVerificationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email verification is temporarily unavailable.",
        ) from None

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication storage is unavailable.",
        ) from None

    _set_session_cookie(
        request,
        response,
        session_token,
        service.session_days,
    )

    return _account_response(
        account
    )


@router.post(
    "/resend-verification",
    response_model=ResendVerificationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def resend_verification(
    payload: ResendVerificationRequest,
    request: Request,
    response: Response,
) -> ResendVerificationResponse:
    require_same_origin_browser_request(
        request
    )

    service = _service(
        request
    )

    sender = _email_sender(
        request
    )

    if sender is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email verification delivery is unavailable.",
        )

    try:
        prepared = await asyncio.to_thread(
            service.request_email_verification,
            payload.email,
        )

    except EmailVerificationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email verification is temporarily unavailable.",
        ) from None

    if prepared is not None:
        account, token, expires_at = (
            prepared
        )

        sent = await _send_verification(
            sender,
            recipient=account.email,
            token=token,
            expires_at=expires_at,
        )

        if not sent:
            try:
                await asyncio.to_thread(
                    service.revoke_email_verification,
                    token,
                )
            except EmailVerificationError:
                pass

    response.headers[
        "Cache-Control"
    ] = "no-store"

    # Deliberately enumeration-safe.
    return ResendVerificationResponse(
        accepted=True
    )


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


class _PasswordResetRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def protected(request: Request):
            require_same_origin_browser_request(request)
            try:
                return await handler(request)
            except RequestValidationError:
                # Pydantic's default errors include raw input (tokens/passwords).
                raise HTTPException(
                    status_code=422,
                    detail="Password reset request is invalid.",
                ) from None

        return protected


password_reset_router = APIRouter(route_class=_PasswordResetRoute)


@password_reset_router.post(
    "/forgot-password", status_code=status.HTTP_202_ACCEPTED,
    response_model=PasswordResetAcceptedResponse,
)
async def forgot_password(
    payload: ForgotPasswordRequest, request: Request, response: Response,
) -> PasswordResetAcceptedResponse:
    from urllib.parse import urlencode
    from app.auth.email_delivery import normalize_public_base_url

    require_same_origin_browser_request(request)
    service = _service(request)
    sender = _email_sender(request)
    if sender is None:
        raise HTTPException(status_code=503, detail="Password reset is temporarily unavailable.")
    try:
        base = normalize_public_base_url(sender.public_base_url)
        prepared = await asyncio.to_thread(service.request_password_reset, payload.email)
    except Exception:
        raise HTTPException(status_code=503, detail="Password reset is temporarily unavailable.") from None
    if prepared is not None:
        account, token, expires_at = prepared
        try:
            await asyncio.to_thread(
                sender.send_password_reset, recipient=account.email,
                reset_url=f"{base}/reset-password?{urlencode({'token': token})}",
                expires_at=expires_at,
            )
        except Exception:
            try:
                await asyncio.to_thread(service.revoke_password_reset, token)
            except PasswordResetError:
                pass
    response.headers["Cache-Control"] = "no-store"
    return PasswordResetAcceptedResponse(accepted=True)


@password_reset_router.post("/reset-password")
async def reset_password(
    payload: ResetPasswordRequest, request: Request, response: Response,
) -> dict[str, bool]:
    require_same_origin_browser_request(request)
    service = _service(request)
    try:
        await asyncio.to_thread(service.reset_password, payload.token, payload.password)
    except PasswordResetInvalid as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    except Exception:
        raise HTTPException(status_code=503, detail="Password reset is temporarily unavailable.") from None
    response.delete_cookie(
        key=SESSION_COOKIE, path="/", httponly=True,
        secure=request.url.scheme == "https", samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"reset": True}


router.include_router(password_reset_router)

__all__ = ["router", "SESSION_COOKIE"]
