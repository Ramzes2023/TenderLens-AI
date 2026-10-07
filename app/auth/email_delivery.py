"""Provider-neutral email delivery for VALYQON AI authentication."""

from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Protocol
from urllib.parse import urlsplit


class EmailDeliveryError(RuntimeError):
    pass


class EmailDeliveryConfigurationError(
    EmailDeliveryError
):
    pass


class EmailSender(Protocol):
    public_base_url: str

    def send_verification(
        self,
        *,
        recipient: str,
        verification_url: str,
        expires_at: str,
    ) -> None:
        ...


def _bool_env(
    name: str,
    default: bool,
) -> bool:
    raw = (
        os.environ.get(name)
        or ("true" if default else "false")
    ).strip().lower()

    if raw in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return True

    if raw in {
        "0",
        "false",
        "no",
        "off",
    }:
        return False

    raise EmailDeliveryConfigurationError(
        f"{name} must be true/false."
    )


def normalize_public_base_url(
    value: str,
) -> str:
    candidate = (
        value
        or ""
    ).strip().rstrip("/")

    if not candidate:
        raise EmailDeliveryConfigurationError(
            "VALYQON_PUBLIC_BASE_URL is required."
        )

    try:
        parsed = urlsplit(
            candidate
        )
    except ValueError:
        raise EmailDeliveryConfigurationError(
            "VALYQON_PUBLIC_BASE_URL is invalid."
        ) from None

    if (
        parsed.scheme.lower()
        not in {
            "http",
            "https",
        }
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {
            "",
            "/",
        }
    ):
        raise EmailDeliveryConfigurationError(
            "VALYQON_PUBLIC_BASE_URL must be a trusted HTTP(S) origin."
        )

    return candidate


class SMTPEmailSender:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        from_address: str,
        public_base_url: str,
        username: str | None = None,
        password: str | None = None,
        starttls: bool = True,
        ssl_enabled: bool = False,
        timeout_seconds: int = 10,
    ):
        clean_host = (
            host
            or ""
        ).strip()

        clean_from = (
            from_address
            or ""
        ).strip()

        if not clean_host:
            raise EmailDeliveryConfigurationError(
                "SMTP host is required."
            )

        if (
            not clean_from
            or "@"
            not in clean_from
        ):
            raise EmailDeliveryConfigurationError(
                "SMTP from address is required."
            )

        if (
            username
            and not password
        ) or (
            password
            and not username
        ):
            raise EmailDeliveryConfigurationError(
                "SMTP username and password must be configured together."
            )

        self.host = clean_host
        self.port = int(port)
        self.from_address = clean_from
        self.public_base_url = (
            normalize_public_base_url(
                public_base_url
            )
        )
        self.username = (
            username.strip()
            if username
            else None
        )
        self.password = (
            password
            if password
            else None
        )
        self.starttls = bool(
            starttls
        )
        self.ssl_enabled = bool(
            ssl_enabled
        )
        self.timeout_seconds = max(
            1,
            min(
                int(timeout_seconds),
                60,
            ),
        )

    def send_verification(
        self,
        *,
        recipient: str,
        verification_url: str,
        expires_at: str,
    ) -> None:
        message = EmailMessage()
        message["Subject"] = (
            "Verify your VALYQON AI email"
        )
        message["From"] = (
            self.from_address
        )
        message["To"] = recipient

        message.set_content(
            "Verify your VALYQON AI email address.\n\n"
            f"{verification_url}\n\n"
            f"This verification link expires at {expires_at}.\n"
            "If you did not create this account, you can ignore this email."
        )

        try:
            if self.ssl_enabled:
                with smtplib.SMTP_SSL(
                    self.host,
                    self.port,
                    timeout=self.timeout_seconds,
                    context=ssl.create_default_context(),
                ) as client:
                    if self.username:
                        client.login(
                            self.username,
                            self.password,
                        )

                    client.send_message(
                        message
                    )

                return

            with smtplib.SMTP(
                self.host,
                self.port,
                timeout=self.timeout_seconds,
            ) as client:
                client.ehlo()

                if self.starttls:
                    client.starttls(
                        context=ssl.create_default_context()
                    )
                    client.ehlo()

                if self.username:
                    client.login(
                        self.username,
                        self.password,
                    )

                client.send_message(
                    message
                )

        except (
            OSError,
            smtplib.SMTPException,
        ):
            raise EmailDeliveryError(
                "Verification email delivery failed."
            ) from None


def load_email_sender_from_env():
    mode = (
        os.environ.get(
            "VALYQON_EMAIL_MODE"
        )
        or "disabled"
    ).strip().lower()

    if mode in {
        "",
        "disabled",
        "off",
        "none",
    }:
        return None

    if mode != "smtp":
        raise EmailDeliveryConfigurationError(
            "VALYQON_EMAIL_MODE must be disabled or smtp."
        )

    host = (
        os.environ.get(
            "VALYQON_SMTP_HOST"
        )
        or ""
    ).strip()

    from_address = (
        os.environ.get(
            "VALYQON_SMTP_FROM"
        )
        or ""
    ).strip()

    public_base_url = (
        os.environ.get(
            "VALYQON_PUBLIC_BASE_URL"
        )
        or ""
    ).strip()

    try:
        port = int(
            os.environ.get(
                "VALYQON_SMTP_PORT",
                "587",
            )
            or "587"
        )
    except ValueError:
        raise EmailDeliveryConfigurationError(
            "VALYQON_SMTP_PORT must be an integer."
        ) from None

    return SMTPEmailSender(
        host=host,
        port=port,
        from_address=from_address,
        public_base_url=public_base_url,
        username=(
            os.environ.get(
                "VALYQON_SMTP_USERNAME"
            )
            or None
        ),
        password=(
            os.environ.get(
                "VALYQON_SMTP_PASSWORD"
            )
            or None
        ),
        starttls=_bool_env(
            "VALYQON_SMTP_STARTTLS",
            True,
        ),
        ssl_enabled=_bool_env(
            "VALYQON_SMTP_SSL",
            False,
        ),
        timeout_seconds=int(
            os.environ.get(
                "VALYQON_SMTP_TIMEOUT_SECONDS",
                "10",
            )
            or "10"
        ),
    )


__all__ = [
    "EmailDeliveryConfigurationError",
    "EmailDeliveryError",
    "EmailSender",
    "SMTPEmailSender",
    "load_email_sender_from_env",
    "normalize_public_base_url",
]
