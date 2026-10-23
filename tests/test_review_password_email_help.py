"""Review-only password-recovery diagnostics never bypass real auth or leak secrets."""
from pathlib import Path

from app.api.auth_pages import forgot_password_html

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "ops" / "website_preview"


def test_review_forgot_password_includes_local_mailpit_and_separate_account_notice(monkeypatch):
    monkeypatch.setenv("VALYQON_WEBSITE_REVIEW_ONLY", "1")
    rendered = forgot_password_html()
    assert "Local preview password help" in rendered
    assert 'http://127.0.0.1:18866/' in rendered
    assert "Accounts from the 18765 AWS preview are separate" in rendered
    assert "intentionally acknowledged" in rendered
    assert "type=\"email\"" in rendered
    assert "/api/v1/auth/" in rendered


def test_normal_forgot_password_does_not_expose_local_test_mailbox(monkeypatch):
    monkeypatch.delenv("VALYQON_WEBSITE_REVIEW_ONLY", raising=False)
    html = forgot_password_html()
    assert "18866" not in html
    assert "Local preview password help" not in html


def test_local_diagnostic_only_queries_preview_and_uses_disposable_probe():
    script = (REVIEW / "diagnose-mail.ps1").read_text(encoding="utf-8")
    helper = (ROOT / "app/review_email_diagnostic.py").read_text(encoding="utf-8")
    assert "valyqon-website-review" in script
    assert "127.0.0.1:18865/forgot-password" in script
    assert "127.0.0.1:18866/" in script
    assert "python -m app.review_email_diagnostic check" in script
    assert "python -m app.review_email_diagnostic probe" in script
    assert "python -m app.review_email_diagnostic account" in script
    assert "python -c" not in script
    assert 'VALYQON_EMAIL_MODE' in helper
    assert 'VALYQON_SMTP_HOST' in helper
    assert 'load_email_sender_from_env()' in helper
    assert 'REVIEW_SMTP_PROBE_SUBMITTED' in helper
    assert 'review-check@valyqon.example.test' in helper
    assert 'REVIEW_DB.as_uri() + "?mode=ro"' in helper
    assert 'ACCOUNT_IN_18865_DATABASE=YES' in helper
    assert 'sys.stdin.readline()' in helper
    for forbidden in ("UPDATE auth_accounts", "INSERT INTO auth_accounts",
                      "DROP TABLE", "DELETE FROM", "reset --hard",
                      "docker system prune", "down -v", "PASSWORD="):
        assert forbidden not in script
        assert forbidden not in helper
