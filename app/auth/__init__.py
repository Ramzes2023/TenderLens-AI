"""VALYQON AI web authentication core."""

from .models import AuthAccount, AuthSession
from .passwords import PasswordPolicyError, hash_password, validate_password, verify_password
from .repository import AuthRepository, AuthRepositoryError, WEB_OWNER_OFFSET
from .service import (
    AuthError,
    AuthService,
    EmailAlreadyVerified,
    EmailNotVerified,
    EmailVerificationError,
    EmailVerificationInvalid,
    EmailVerificationRateLimited,
    InvalidCredentials,
    RegistrationError,
    PasswordResetError,
    PasswordResetInvalid,
    PasswordResetRateLimited,
    TelegramLinkError,
    TelegramLinkUnavailable,
    normalize_email,
)

__all__ = [
    "PasswordResetError", "PasswordResetInvalid", "PasswordResetRateLimited",
    "AuthAccount", "AuthSession", "AuthRepository", "AuthRepositoryError",
    "WEB_OWNER_OFFSET", "AuthService", "AuthError", "InvalidCredentials",
    "RegistrationError", "EmailNotVerified", "EmailVerificationError", "EmailVerificationInvalid",
    "EmailVerificationRateLimited", "EmailAlreadyVerified",
    "TelegramLinkError", "TelegramLinkUnavailable", "PasswordPolicyError", "hash_password",
    "verify_password", "validate_password", "normalize_email",
]
