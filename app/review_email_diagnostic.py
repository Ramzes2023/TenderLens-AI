"""Local-only diagnostics for the isolated Windows browser review.

Run inside the review API container, never from a web route:
python -m app.review_email_diagnostic check
python -m app.review_email_diagnostic probe
python -m app.review_email_diagnostic account  # test email via standard input

No password, reset tokens, account addresses or configuration secrets are printed.
"""
from __future__ import annotations

import os
import smtplib
import sqlite3
import sys
from email.message import EmailMessage
from pathlib import Path

LOCAL_BASE = "http://127.0.0.1:18865"
REVIEW_DB = Path("/app/data/website-review.sqlite")


def _validated_review_sender():
    # Never allow this diagnostic to run against production or another stack.
    if os.environ.get("VALYQON_WEBSITE_REVIEW_ONLY") != "1":
        raise RuntimeError("NOT_ISOLATED_WEBSITE_REVIEW")
    if os.environ.get("VALYQON_EMAIL_MODE", "").lower() != "smtp":
        raise RuntimeError("REVIEW_EMAIL_MODE_NOT_SMTP")
    if os.environ.get("VALYQON_SMTP_HOST") != "mailpit":
        raise RuntimeError("REVIEW_SMTP_HOST_NOT_LOCAL_MAILPIT")
    if os.environ.get("VALYQON_PUBLIC_BASE_URL") != LOCAL_BASE:
        raise RuntimeError("REVIEW_PASSWORD_RESET_BASE_MISMATCH")
    if os.environ.get("DATABASE_URL") != "sqlite:////app/data/website-review.sqlite":
        raise RuntimeError("REVIEW_DATABASE_NOT_ISOLATED")
    from app.auth.email_delivery import SMTPEmailSender, load_email_sender_from_env
    sender = load_email_sender_from_env()
    if (
        not isinstance(sender, SMTPEmailSender)
        or sender.host != "mailpit"
        or sender.port != 1025
        or sender.starttls
        or sender.ssl_enabled
        or sender.username
        or sender.password
        or sender.public_base_url != LOCAL_BASE
    ):
        raise RuntimeError("REVIEW_SENDER_CONFIGURATION_INVALID")
    return sender


def _check():
    sender = _validated_review_sender()
    print("REVIEW_EMAIL_MODE=SMTP")
    print("REVIEW_ACTUAL_EMAIL_SENDER_READY=YES")
    print("REVIEW_SMTP_POINTS_TO_LOCAL_MAILPIT=YES")
    print("REVIEW_RESET_LINK_BASE_OK=YES")
    return sender


def _probe():
    sender = _check()
    msg = EmailMessage()
    msg["From"] = sender.from_address
    msg["To"] = "review-check@valyqon.example.test"
    msg["Subject"] = "VALYQON LOCAL MAILPIT DIAGNOSTIC"
    msg.set_content("Local, disposable SMTP delivery test. No password reset token is included.")
    with smtplib.SMTP(sender.host, sender.port, timeout=8) as connection:
        connection.send_message(msg)
    print("REVIEW_SMTP_PROBE_SUBMITTED=YES")


def _account():
    _check()
    address = sys.stdin.readline().strip().casefold()
    if not address:
        print("ACCOUNT_CHECK=SKIPPED")
        return
    if len(address) > 254 or "@" not in address:
        raise RuntimeError("INVALID_TEST_EMAIL")
    if not REVIEW_DB.is_file():
        raise RuntimeError("REVIEW_DATABASE_MISSING")
    conn = sqlite3.connect("file:/app/data/website-review.sqlite?mode=ro", uri=True, timeout=5)
    try:
        row = conn.execute(
            "SELECT is_active, email_verified FROM auth_accounts WHERE lower(email)=?",
            (address,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        print("ACCOUNT_IN_18865_DATABASE=NO")
    else:
        print("ACCOUNT_IN_18865_DATABASE=YES")
        print("ACCOUNT_ACTIVE=" + ("YES" if row[0] else "NO"))
        print("ACCOUNT_EMAIL_VERIFIED=" + ("YES" if row[1] else "NO"))


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        if argv == ["check"]:
            _check()
        elif argv == ["probe"]:
            _probe()
        elif argv == ["account"]:
            _account()
        else:
            print("USAGE: check | probe | account")
            return 2
    except (RuntimeError, OSError, sqlite3.Error, smtplib.SMTPException) as exc:
        # Only fixed messages; never expose full tracebacks, user address or SMTP credentials.
        print("REVIEW_EMAIL_DIAGNOSTIC=FAILED")
        if isinstance(exc, RuntimeError):
            print("REASON=" + str(exc))
        elif isinstance(exc, sqlite3.Error):
            print("REASON=LOCAL_ACCOUNT_DB_UNAVAILABLE")
        else:
            print("REASON=LOCAL_MAIL_TRANSPORT_UNAVAILABLE")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
