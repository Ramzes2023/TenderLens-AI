"""RFC 5322 transport headers for VALYQON transactional SMTP messages."""

from datetime import timedelta
from email.utils import parsedate_to_datetime
from unittest.mock import patch

import pytest

from app.auth.email_delivery import SMTPEmailSender


@pytest.mark.parametrize("kind", ["verification", "password_reset", "deadline_reminder"])
def test_transactional_smtp_messages_have_date_and_message_id(kind):
    captured = []

    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def send_message(self, message):
            captured.append(message)

    sender = SMTPEmailSender(
        host="smtp.example.test",
        port=465,
        from_address="VALYQON AI <team@valyqon.dns.army>",
        public_base_url="https://valyqon.duckdns.org",
        ssl_enabled=True,
    )

    with patch("app.auth.email_delivery.smtplib.SMTP_SSL", FakeSMTP):
        if kind == "verification":
            sender.send_verification(
                recipient="owner@example.test",
                verification_url="https://valyqon.duckdns.org/verify-email?token=abc",
                expires_at="2026-10-27T23:59:00+00:00",
            )
        elif kind == "password_reset":
            sender.send_password_reset(
                recipient="owner@example.test",
                reset_url="https://valyqon.duckdns.org/reset-password?token=abc",
                expires_at="2026-10-27T23:59:00+00:00",
            )
        else:
            sender.send_deadline_reminder(
                recipient="owner@example.test", text="Saved deadline reminder."
            )

    assert len(captured) == 1
    message = captured[0]
    assert message["From"] == "VALYQON AI <team@valyqon.dns.army>"
    assert message["To"] == "owner@example.test"
    assert message["Message-ID"].endswith("@valyqon.dns.army>")
    assert message["Message-ID"].startswith("<")
    assert parsedate_to_datetime(message["Date"]).utcoffset() == timedelta(0)
    assert set(message.keys()).issuperset(
        {"From", "To", "Subject", "Date", "Message-ID", "MIME-Version"}
    )
    # Generated transport headers must not expose a reset or verification token.
    assert "token=abc" not in message["Message-ID"]


def test_transactional_emails_get_distinct_message_ids():
    captured = []

    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, traceback):
            return False
        def send_message(self, message):
            captured.append(message)

    sender = SMTPEmailSender(
        host="smtp.example.test",
        port=465,
        from_address="team@valyqon.dns.army",
        public_base_url="https://valyqon.duckdns.org",
        ssl_enabled=True,
    )
    with patch("app.auth.email_delivery.smtplib.SMTP_SSL", FakeSMTP):
        sender.send_password_reset(
            recipient="owner@example.test",
            reset_url="https://valyqon.duckdns.org/reset-password?token=one",
            expires_at="2026-10-27T23:59:00+00:00",
        )
        sender.send_password_reset(
            recipient="owner@example.test",
            reset_url="https://valyqon.duckdns.org/reset-password?token=two",
            expires_at="2026-10-27T23:59:00+00:00",
        )

    assert len(captured) == 2
    assert captured[0]["Message-ID"] != captured[1]["Message-ID"]


@pytest.mark.parametrize("kind", ["verification", "password_reset", "deadline_reminder"])
@pytest.mark.parametrize("ssl_enabled", [True, False])
@pytest.mark.parametrize("refused", [True, False])
def test_smtp_recipient_refusal_is_not_mistaken_for_delivery(kind, ssl_enabled, refused):
    """SMTP can reject individual recipients by returning a nonempty mapping."""
    from app.auth.email_delivery import EmailDeliveryError

    class FakeSMTP:
        sends = 0

        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def ehlo(self):
            return None

        def starttls(self, **kwargs):
            return None

        def login(self, *args):
            return None

        def send_message(self, message):
            FakeSMTP.sends += 1
            assert message["To"] == "owner@example.test"
            if refused:
                return {"owner@example.test": (550, b"Recipient rejected")}
            return {}

    sender = SMTPEmailSender(
        host="smtp.resend.com",
        port=465 if ssl_enabled else 587,
        from_address="VALYQON AI <team@valyqon.dns.army>",
        public_base_url="https://valyqon.duckdns.org",
        username="resend",
        password="re_OFFLINE_ONLY",
        ssl_enabled=ssl_enabled,
        starttls=not ssl_enabled,
    )
    kwargs = {
        "verification": dict(
            recipient="owner@example.test",
            verification_url="https://valyqon.duckdns.org/verify-email?token=abc",
            expires_at="2026-10-28T23:59:00+00:00",
        ),
        "password_reset": dict(
            recipient="owner@example.test",
            reset_url="https://valyqon.duckdns.org/reset-password?token=abc",
            expires_at="2026-10-28T23:59:00+00:00",
        ),
        "deadline_reminder": dict(
            recipient="owner@example.test", text="Expected transactional reminder."
        ),
    }
    method = {
        "verification": sender.send_verification,
        "password_reset": sender.send_password_reset,
        "deadline_reminder": sender.send_deadline_reminder,
    }[kind]
    transport = "SMTP_SSL" if ssl_enabled else "SMTP"
    with patch(f"app.auth.email_delivery.smtplib.{transport}", FakeSMTP):
        if refused:
            with pytest.raises(EmailDeliveryError, match="SMTP recipient rejected"):
                method(**kwargs[kind])
        else:
            method(**kwargs[kind])
    assert FakeSMTP.sends == 1
