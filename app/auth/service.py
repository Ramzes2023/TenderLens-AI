"""Application service for TenderLens account registration and sessions."""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

from .models import AuthAccount
from .passwords import PasswordPolicyError, hash_password, verify_password
from .repository import AuthRepository, AuthRepositoryError

_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,189}$")


class AuthError(RuntimeError):
    pass


class InvalidCredentials(AuthError):
    pass


class RegistrationError(AuthError):
    pass


def normalize_email(email: str) -> str:
    value = (email or "").strip().lower()
    if len(value) > 254 or not _EMAIL_RE.fullmatch(value):
        raise RegistrationError("Enter a valid email address.")
    local, domain = value.rsplit("@", 1)
    if "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise RegistrationError("Enter a valid email address.")
    return f"{local}@{domain}"


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AuthService:
    def __init__(self, repository: AuthRepository, *, session_days: int = 7):
        self.repository = repository
        self.session_days = max(1, min(int(session_days), 30))

    def register(self, email: str, password: str) -> AuthAccount:
        clean_email = normalize_email(email)
        try:
            password_hash = hash_password(password)
            return self.repository.create_account(clean_email, password_hash)
        except PasswordPolicyError as error:
            raise RegistrationError(str(error)) from None
        except AuthRepositoryError as error:
            raise RegistrationError(str(error)) from None

    def authenticate(self, email: str, password: str) -> AuthAccount:
        try:
            clean_email = normalize_email(email)
        except RegistrationError:
            raise InvalidCredentials("Invalid email or password.") from None
        record = self.repository.find_account_by_email(clean_email)
        if record is None:
            hash_password(password if 12 <= len(password) <= 128 else "invalid-password-value")
            raise InvalidCredentials("Invalid email or password.")
        account, encoded_hash = record
        if not account.is_active or not verify_password(password, encoded_hash):
            raise InvalidCredentials("Invalid email or password.")
        return account

    def create_session(self, account: AuthAccount) -> str:
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(days=self.session_days)).isoformat(timespec="seconds")
        self.repository.create_session(account_id=account.id, token_hash=_token_hash(token), expires_at=expires_at)
        return token

    def account_for_token(self, token: str | None, *, touch: bool = True):
        if not token:
            return None
        token_hash = _token_hash(token)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        account = self.repository.find_account_for_session(token_hash, now)
        if account is not None and touch:
            self.repository.touch_session(token_hash)
        return account

    def logout(self, token: str | None) -> None:
        if token:
            self.repository.delete_session(_token_hash(token))

    def link_legacy_owner(self, account: AuthAccount, owner_user_id: int) -> AuthAccount:
        try:
            return self.repository.link_owner(account.id, owner_user_id)
        except AuthRepositoryError as error:
            raise AuthError(str(error)) from None
