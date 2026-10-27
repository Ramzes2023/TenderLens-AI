"""Offline fail-closed contract for the Windows Gmail SMTP candidate helper."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PS1 = ROOT / "scripts/ops/valyqon_gmail_fallback_candidate.ps1"


def test_helper_only_stages_candidate_never_restarts_production():
    text = PS1.read_text(encoding="utf-8")
    assert "google.candidate.env" in text
    assert "resend.env" not in text
    assert "docker compose" not in text.lower()
    assert "docker restart" not in text.lower()
    assert "down -v" not in text.lower()
    assert "VALYQON_EMAIL_MODE=smtp" in text
    assert "PRODUCTION_API_UNCHANGED=YES" in text
    assert "VALYQON_PUBLIC_BASE_URL=https://valyqon.duckdns.org" in text


def test_helper_requires_explicit_consent_for_secret_and_test_email():
    text = PS1.read_text(encoding="utf-8")
    assert 'Read-Host "Type STAGE_GMAIL' in text
    assert "Read-Host" in text and "-AsSecureString" in text
    assert "ZeroFreeBSTR" in text
    assert 'Read-Host "Type SEND_ONE_TEST' in text
    assert "[switch]$SendOneTestEmail" in text
    assert 'send_one = "__SEND_ONE__" == "yes"' in text
    assert "SMTP_HANDOFF=PASS" in text
    assert "REAL_INBOX_DELIVERY=NOT_VERIFIED" in text


def test_helper_security_guardrails():
    text = PS1.read_text(encoding="utf-8")
    assert 'StrictHostKeyChecking=yes' in text
    assert 'IdentitiesOnly=yes' in text
    assert 'install -d -m 700' in text
    assert 'chmod 600 "$t"' in text
    assert "ssl.create_default_context()" in text
    assert "smtp.gmail.com" in text
    assert "smtp.login(" in text
    assert "smtp.send_message(message)" in text
    assert "set_content(" in text
    assert "Message-ID" in text
    assert "Date" in text
    assert "secret=" not in text.lower()
    assert "print(config" not in text.lower()
