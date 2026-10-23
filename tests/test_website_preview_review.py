"""Local website review is isolated and never starts existing Worker/project."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "ops/website_preview"


def test_review_compose_is_local_only_no_bot_no_prod_secrets():
    content = (PATH / "compose.yaml").read_text(encoding="utf-8")
    assert '127.0.0.1:18865:8000' in content
    assert "website_review_data:/app/data" in content
    assert "sqlite:////app/data/website-review.sqlite" in content
    assert 'VALYQON_RESTRICT_PAID_SOURCE_DETAILS: "true"' in content
    assert 'VALYQON_PUBLIC_AI_ENABLED: "false"' in content
    assert 'VALYQON_EMAIL_MODE: smtp' in content
    assert 'VALYQON_SMTP_HOST: mailpit' in content
    assert 'VALYQON_SMTP_PORT: "1025"' in content
    assert 'VALYQON_SMTP_STARTTLS: "false"' in content
    assert 'VALYQON_SMTP_SSL: "false"' in content
    assert 'VALYQON_PUBLIC_BASE_URL: "http://127.0.0.1:18865"' in content
    assert '127.0.0.1:18866:8025' in content
    assert 'mailpit:' in content
    assert 'MP_MAX_MESSAGES: "100"' in content
    for forbidden in ("env_file:", "TELEGRAM_BOT_TOKEN: ${", "caddy:", "bot:",
                      "tenderlens_data:", "PREVIEW_DB_PASSWORD:"):
        assert forbidden not in content


def test_review_scripts_preserve_main_checkout_and_named_volume():
    start = (PATH / "start.ps1").read_text(encoding="utf-8")
    stop = (PATH / "stop.ps1").read_text(encoding="utf-8")
    assert "valyqon-website-review" in start and "valyqon-website-review" in stop
    assert "Start-Process" in start and "guestSearchForm" in start
    assert "vqPulseChart" in start
    assert "down -v" not in stop
    assert "up -d --build api mailpit" in start
    assert "LOCAL_MAIL_INBOX=http://127.0.0.1:18866/" in start
    assert "LOCAL_PASSWORD_RECOVERY=http://127.0.0.1:18865/forgot-password" in start
    assert "git checkout" not in start
    assert (PATH / "review.env").read_text(encoding="utf-8").startswith("#")
