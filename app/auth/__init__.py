"""VALYQON AI web authentication core."""

from .models import AuthAccount, AuthSession
from .passwords import PasswordPolicyError, hash_password, validate_password, verify_password
from .repository import AuthRepository, AuthRepositoryError, WEB_OWNER_OFFSET
from .service import (
    AuthError,
    AuthService,
    InvalidCredentials,
    RegistrationError,
    TelegramLinkError,
    TelegramLinkUnavailable,
    normalize_email,
)

__all__ = [
    "AuthAccount", "AuthSession", "AuthRepository", "AuthRepositoryError",
    "WEB_OWNER_OFFSET", "AuthService", "AuthError", "InvalidCredentials",
    "RegistrationError", "TelegramLinkError", "TelegramLinkUnavailable", "PasswordPolicyError", "hash_password",
    "verify_password", "validate_password", "normalize_email",
]
