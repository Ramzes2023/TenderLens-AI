"""Application service for VALYQON AI account registration and sessions."""

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


class PasswordResetError(AuthError):
    pass


class PasswordResetInvalid(PasswordResetError):
    pass


class PasswordResetRateLimited(PasswordResetError):
    pass


class EmailVerificationError(AuthError):
    pass


class EmailVerificationInvalid(EmailVerificationError):
    pass


class EmailVerificationRateLimited(EmailVerificationError):
    pass


class EmailAlreadyVerified(EmailVerificationError):
    pass


class EmailNotVerified(AuthError):
    pass


class TelegramLinkError(AuthError):
    pass


class TelegramLinkUnavailable(TelegramLinkError):
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
    def __init__(
        self,
        repository: AuthRepository,
        *,
        session_days: int = 7,
        verification_minutes: int = 30,
        verification_cooldown_seconds: int = 60,
    ):
        self.repository = repository
        self.session_days = max(
            1,
            min(
                int(session_days),
                30,
            ),
        )
        self.verification_minutes = max(
            5,
            min(
                int(verification_minutes),
                24 * 60,
            ),
        )
        self.verification_cooldown_seconds = max(
            10,
            min(
                int(verification_cooldown_seconds),
                60 * 60,
            ),
        )

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

        if not account.email_verified:
            raise EmailNotVerified(
                "Email verification required."
            )

        return account

    def issue_email_verification(
        self,
        account: AuthAccount,
        *,
        enforce_cooldown: bool = True,
    ) -> tuple[str, str]:
        if account.email_verified:
            raise EmailAlreadyVerified(
                "Email is already verified."
            )

        token = secrets.token_urlsafe(32)
        now = datetime.now(
            timezone.utc
        )

        expires_at = (
            now
            + timedelta(
                minutes=self.verification_minutes
            )
        ).isoformat(
            timespec="seconds"
        )

        cooldown_after = None

        if enforce_cooldown:
            cooldown_after = (
                now
                - timedelta(
                    seconds=(
                        self.verification_cooldown_seconds
                    )
                )
            ).isoformat(
                timespec="seconds"
            )

        try:
            created = (
                self.repository
                .create_email_verification(
                    account_id=account.id,
                    token_hash=_token_hash(
                        token
                    ),
                    expires_at=expires_at,
                    cooldown_after=cooldown_after,
                )
            )

        except AuthRepositoryError as error:
            if (
                str(error)
                == "Email is already verified."
            ):
                raise EmailAlreadyVerified(
                    "Email is already verified."
                ) from None

            raise EmailVerificationError(
                "Email verification storage is unavailable."
            ) from None

        if not created:
            raise EmailVerificationRateLimited(
                "Please wait before requesting another verification email."
            )

        return (
            token,
            expires_at,
        )

    def request_email_verification(
        self,
        email: str,
    ) -> tuple[AuthAccount, str, str] | None:
        """Prepare a resend without revealing whether an account exists."""

        try:
            clean_email = normalize_email(
                email
            )
        except RegistrationError:
            return None

        try:
            record = (
                self.repository
                .find_account_by_email(
                    clean_email
                )
            )
        except AuthRepositoryError:
            raise EmailVerificationError(
                "Email verification storage is unavailable."
            ) from None

        if record is None:
            return None

        account, _password_hash = (
            record
        )

        if (
            not account.is_active
            or account.email_verified
        ):
            return None

        try:
            token, expires_at = (
                self.issue_email_verification(
                    account,
                    enforce_cooldown=True,
                )
            )

        except (
            EmailAlreadyVerified,
            EmailVerificationRateLimited,
        ):
            return None

        return (
            account,
            token,
            expires_at,
        )

    def revoke_email_verification(
        self,
        token: str,
    ) -> None:
        clean_token = (
            token
            or ""
        ).strip()

        if not clean_token:
            return

        try:
            self.repository.delete_email_verification(
                token_hash=_token_hash(
                    clean_token
                ),
            )

        except AuthRepositoryError:
            raise EmailVerificationError(
                "Email verification storage is unavailable."
            ) from None

    def verify_email(
        self,
        token: str,
    ) -> AuthAccount:
        clean_token = (
            token or ""
        ).strip()

        if (
            not clean_token
            or len(clean_token) > 256
        ):
            raise EmailVerificationInvalid(
                "Verification link is invalid or expired."
            )

        now = datetime.now(
            timezone.utc
        ).isoformat(
            timespec="seconds"
        )

        try:
            account = (
                self.repository
                .consume_email_verification(
                    token_hash=_token_hash(
                        clean_token
                    ),
                    now=now,
                )
            )

        except AuthRepositoryError:
            raise EmailVerificationError(
                "Email verification storage is unavailable."
            ) from None

        if account is None:
            raise EmailVerificationInvalid(
                "Verification link is invalid or expired."
            )

        return account

    def issue_password_reset(
        self, account: AuthAccount, *, enforce_cooldown: bool = True,
    ) -> tuple[str, str]:
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(minutes=30)).isoformat(timespec="seconds")
        cooldown_after = (
            (now - timedelta(seconds=60)).isoformat(timespec="seconds")
            if enforce_cooldown else None
        )
        try:
            created = self.repository.create_password_reset(
                account_id=account.id, token_hash=_token_hash(token),
                expires_at=expires_at, cooldown_after=cooldown_after,
            )
        except AuthRepositoryError:
            raise PasswordResetError("Password reset is temporarily unavailable.") from None
        if not created:
            raise PasswordResetRateLimited("Please wait before requesting another password reset.")
        return token, expires_at

    def request_password_reset(self, email: str) -> tuple[AuthAccount, str, str] | None:
        """Suppress unknown, inactive and cooldown-limited requests identically."""
        try:
            clean_email = normalize_email(email)
        except RegistrationError:
            return None
        try:
            record = self.repository.find_account_by_email(clean_email)
        except AuthRepositoryError:
            raise PasswordResetError("Password reset is temporarily unavailable.") from None
        if record is None or not record[0].is_active:
            return None
        account = record[0]
        try:
            token, expires_at = self.issue_password_reset(account)
        except PasswordResetRateLimited:
            return None
        return account, token, expires_at

    def revoke_password_reset(self, token: str) -> None:
        if not token:
            return
        try:
            self.repository.delete_password_reset(token_hash=_token_hash(token.strip()))
        except AuthRepositoryError:
            raise PasswordResetError("Password reset is temporarily unavailable.") from None

    def reset_password(self, token: str, password: str) -> AuthAccount:
        clean_token = (token or "").strip()
        if not clean_token or len(clean_token) > 256:
            raise PasswordResetInvalid("Password reset link is invalid or expired.")
        try:
            password_hash = hash_password(password)
        except PasswordPolicyError as error:
            raise PasswordResetInvalid(str(error)) from None
        try:
            account = self.repository.consume_password_reset(
                token_hash=_token_hash(clean_token), password_hash=password_hash,
                now=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )
        except AuthRepositoryError:
            raise PasswordResetError("Password reset is temporarily unavailable.") from None
        if account is None:
            raise PasswordResetInvalid("Password reset link is invalid or expired.")
        return account

    def create_session(self, account: AuthAccount) -> str:
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        now_text = now.isoformat(timespec="seconds")
        expires_at = (now + timedelta(days=self.session_days)).isoformat(timespec="seconds")
        self.repository.delete_expired_sessions(now_text)
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

    def create_telegram_link(self, account: AuthAccount) -> tuple[str, str]:
        from .repository import WEB_OWNER_OFFSET

        if account.owner_user_id < WEB_OWNER_OFFSET:
            raise TelegramLinkError("Telegram is already connected.")

        token = secrets.token_urlsafe(24)
        expires_at = (
            datetime.now(timezone.utc) + timedelta(minutes=10)
        ).isoformat(timespec="seconds")
        try:
            created = self.repository.create_telegram_link(
                account_id=account.id,
                token_hash=_token_hash(token),
                expires_at=expires_at,
            )
        except AuthRepositoryError:
            raise TelegramLinkUnavailable(
                "Telegram linking is temporarily unavailable."
            ) from None
        if not created:
            raise TelegramLinkError("Telegram is already connected.")
        return token, expires_at

    def consume_telegram_link(self, token: str, telegram_user_id: int) -> AuthAccount:
        clean_token = (token or "").strip()
        if not clean_token or len(clean_token) > 128:
            raise TelegramLinkError(
                "Telegram link is invalid, expired, or already used."
            )

        try:
            telegram_owner = int(telegram_user_id)
        except (TypeError, ValueError):
            raise TelegramLinkError("Telegram user id is invalid.") from None
        if telegram_owner <= 0:
            raise TelegramLinkError("Telegram user id is invalid.")

        claim_marker = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        token_hash = _token_hash(clean_token)

        try:
            account_id = self.repository.claim_telegram_link(
                token_hash=token_hash,
                now=claim_marker,
            )
        except AuthRepositoryError as error:
            raise TelegramLinkError(str(error)) from None

        if account_id is None:
            raise TelegramLinkError(
                "Telegram link is invalid, expired, or already used."
            )

        try:
            account = self.repository.find_account_by_id(account_id)
            if account is None:
                raise TelegramLinkError("Account not found.")

            from .repository import WEB_OWNER_OFFSET
            if account.owner_user_id < WEB_OWNER_OFFSET:
                raise TelegramLinkError("Telegram is already connected.")

            return self.repository.link_owner(account.id, telegram_owner)
        except (TelegramLinkError, AuthRepositoryError) as error:
            try:
                self.repository.release_telegram_link(
                    token_hash=token_hash,
                    consumed_at=claim_marker,
                )
            except AuthRepositoryError:
                # Fail closed if the reservation cannot be released.
                pass
            if isinstance(error, TelegramLinkError):
                raise
            raise TelegramLinkError(str(error)) from None

    def link_legacy_owner(self, account: AuthAccount, owner_user_id: int) -> AuthAccount:
        try:
            return self.repository.link_owner(account.id, owner_user_id)
        except AuthRepositoryError as error:
            raise AuthError(str(error)) from None
