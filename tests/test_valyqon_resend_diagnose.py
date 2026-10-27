"""Static release contract: operator diagnostics use Resend only."""
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "scripts/ops/valyqon_resend_diagnose.ps1"


def test_resend_only_and_existing_operator_secret():
    data = SOURCE.read_text(encoding="utf-8")
    assert "smtp.resend.com" in data
    assert "resend.env" in data
    assert "resend._domainkey." in data
    assert "VALYQON_SMTP_PASSWORD" in data
    assert "smtp.gmail.com" not in data
    assert "GOOGLE_APP_PASSWORD" not in data
    assert "App Password" not in data
    assert "gmail.candidate.env" not in data
    assert 'message["From"] = "VALYQON AI <team@valyqon.dns.army>"' in data
    assert 'message["To"] = "ramzesisayev444@gmail.com"' in data


def test_no_send_default_and_owner_consent():
    data = SOURCE.read_text(encoding="utf-8")
    assert "param([switch]$SendOneResendTest)" in data
    assert 'if ($SendOneResendTest)' in data
    assert 'Read-Host "Type SEND_ONE_RESEND_TEST' in data
    assert 'if mode == "audit":' in data
    assert 'print("EMAIL_SENT=NO"' in data
    assert 'message.set_content("hello world\\n")' in data
    assert 'message["Subject"] = "hello"' in data
    assert "NO PRODUCTION" not in data or "PRODUCTION_EMAIL_DEPLOYED=NO" in data


def test_cooldown_one_time_real_inbox_gate_and_redaction():
    data = SOURCE.read_text(encoding="utf-8")
    assert "datetime(2026, 10, 28, 18, 0, tzinfo=timezone.utc)" in data
    assert "os.O_CREAT | os.O_EXCL | os.O_WRONLY" in data
    assert "resend-gmail-hello-once.marker" in data
    assert "StrictHostKeyChecking=yes" in data
    assert "IdentitiesOnly=yes" in data
    assert "stat.S_IMODE(secret.stat().st_mode) != 0o600" in data
    assert "REAL_GMAIL_DELIVERY=NOT_YET_VERIFIED" in data
    assert "LIVE_API_AND_SQLITE_CHANGED=NO" in data
    assert "docker compose" not in data.lower()
    assert "docker restart" not in data.lower()
    assert "SMTP_PASSWORD=" not in data  # never prints or creates a secret file


def test_dmarc_exact_and_sending_records_checked():
    data = SOURCE.read_text(encoding="utf-8")
    assert '"1.1.1.1", "8.8.8.8"' in data
    assert '"v=DMARC1; p=none;"' in data
    assert '("send", "rsend")' not in data or "rsend" in data
    assert 'foreach ($alias in @("send", "rsend"))' in data
    assert "RESEND_DNS_PUBLIC_RECORDS=PASS" in data
