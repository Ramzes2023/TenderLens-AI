"""API tests use a fake sender; SMTP is blocked for the entire module."""
import hashlib
from contextlib import closing
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.config import ApiSettings
from app.api.main import create_app
from app.api.runtime import ApiRuntime
from app.auth import AuthRepository, AuthService

OLD_PASSWORD = "original secure password 123"
NEW_PASSWORD = "replacement secure password 456"


class FakeEmailSender:
    public_base_url = "https://accounts.valyqon.example"

    def __init__(self):
        self.messages = []
        self.fail = False

    def send_verification(self, **kwargs):
        self.messages.append(kwargs)

    def send_password_reset(self, *, recipient, reset_url, expires_at):
        if self.fail:
            raise RuntimeError("fake delivery failure")
        self.messages.append(dict(recipient=recipient, reset_url=reset_url, expires_at=expires_at))


@pytest.fixture(autouse=True)
def no_real_email(monkeypatch):
    monkeypatch.setenv("VALYQON_EMAIL_MODE", "disabled")
    with patch("smtplib.SMTP", side_effect=AssertionError("Real SMTP forbidden")) as smtp, \
         patch("smtplib.SMTP_SSL", side_effect=AssertionError("Real SMTP forbidden")) as smtp_ssl:
        yield
        smtp.assert_not_called()
        smtp_ssl.assert_not_called()


@pytest.fixture
def api(tmp_path):
    repository = AuthRepository(tmp_path / "reset-api.db")
    repository.initialize()
    service = AuthService(repository)
    account = service.register("user@example.com", OLD_PASSWORD)
    sender = FakeEmailSender()
    runtime = ApiRuntime(auth_service=service, email_sender=sender)
    settings = ApiSettings(host="127.0.0.1", port=8000, reload=False, api_key=None)
    with TestClient(create_app(runtime=runtime, settings=settings), follow_redirects=False) as client:
        yield client, repository, service, account, sender, runtime


def request_reset(client, email="user@example.com", **kwargs):
    return client.post("/api/v1/auth/forgot-password", json={"email": email}, **kwargs)


def token_from(sender):
    return parse_qs(urlsplit(sender.messages[-1]["reset_url"]).query)["token"][0]


def reset(client, token, password=NEW_PASSWORD, **kwargs):
    return client.post("/api/v1/auth/reset-password", json={"token": token, "password": password}, **kwargs)


def test_known_unknown_inactive_cooldown_are_identical(api):
    client, repository, service, account, sender, runtime = api
    inactive = service.register("inactive@example.com", OLD_PASSWORD)
    with closing(repository._connect()) as conn:
        with conn:
            conn.execute("UPDATE auth_accounts SET is_active=0 WHERE id=?", (inactive.id,))
    responses = [request_reset(client, email) for email in (
        account.email, "unknown@example.com", "inactive@example.com", account.email,
    )]
    assert all(response.status_code == 202 for response in responses)
    assert all(response.json() == {"accepted": True} for response in responses)
    assert all(response.headers["cache-control"] == "no-store" for response in responses)
    assert len(sender.messages) == 1
    token = token_from(sender)
    assert all(token not in response.text and "reset_url" not in response.text for response in responses)
    assert all("set-cookie" not in response.headers for response in responses)


def test_canonical_url_ignores_host_and_forwarded_host(api):
    client, repository, service, account, sender, runtime = api
    response = request_reset(client, headers={"Host": "hostile.example", "X-Forwarded-Host": "evil.example"})
    assert response.status_code == 202
    url = urlsplit(sender.messages[-1]["reset_url"])
    assert url.scheme == "https"
    assert url.netloc == "accounts.valyqon.example"
    assert url.path == "/reset-password"
    assert set(parse_qs(url.query)) == {"token"}
    assert sender.messages[-1]["recipient"] == account.email
    assert "hostile" not in sender.messages[-1]["reset_url"]


def test_delivery_failure_revokes_ticket_and_remains_generic(api):
    client, repository, service, account, sender, runtime = api
    sender.fail = True
    with patch("app.auth.service.secrets.token_urlsafe", return_value="failed-delivery-token"):
        known = request_reset(client)
    unknown = request_reset(client, "unknown@example.com")
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json() == {"accepted": True}
    assert not sender.messages
    assert reset(client, "failed-delivery-token").status_code == 422
    with closing(repository._connect()) as conn:
        row = conn.execute("SELECT * FROM auth_password_resets").fetchone()
    assert row["token_hash"] == hashlib.sha256(b"failed-delivery-token").hexdigest()
    assert row["consumed_at"] is not None


def test_globally_unavailable_sender_is_generic(api):
    client, repository, service, account, sender, runtime = api
    runtime.email_sender = None
    known = request_reset(client)
    unknown = request_reset(client, "unknown@example.com")
    assert known.status_code == unknown.status_code == 503
    assert known.json() == unknown.json()


@pytest.mark.parametrize("endpoint,body", [
    ("forgot-password", {"email": "user@example.com"}),
    ("reset-password", {"token": "some-token", "password": NEW_PASSWORD}),
])
@pytest.mark.parametrize("headers", [
    {"Origin": "https://evil.example"},
    {"Sec-Fetch-Site": "cross-site"},
])
def test_cross_origin_writes_blocked(api, endpoint, body, headers):
    client, repository, service, account, sender, runtime = api
    response = client.post(f"/api/v1/auth/{endpoint}", json=body, headers=headers)
    assert response.status_code == 403
    assert not sender.messages


def test_reset_no_session_revokes_old_sessions_and_clears_cookie(api):
    client, repository, service, account, sender, runtime = api
    verification, _ = service.issue_email_verification(account)
    account = service.verify_email(verification)
    sessions = [service.create_session(account) for _ in range(2)]
    client.cookies.set("tenderlens_session", sessions[0])
    assert client.get("/api/v1/auth/me").status_code == 200
    request_reset(client)
    token = token_from(sender)
    response = reset(client, token)
    assert response.status_code == 200
    assert response.json() == {"reset": True}
    assert token not in response.text
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert client.get("/api/v1/auth/me").status_code == 401
    assert all(service.account_for_token(session) is None for session in sessions)
    with closing(repository._connect()) as conn:
        assert conn.execute("SELECT COUNT(*) FROM auth_sessions").fetchone()[0] == 0
    assert reset(client, token).status_code == 422
    assert client.post("/api/v1/auth/login", json={"email": account.email, "password": OLD_PASSWORD}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": account.email, "password": NEW_PASSWORD}).status_code == 200


def test_unverified_reset_does_not_verify_or_login(api):
    client, repository, service, account, sender, runtime = api
    request_reset(client)
    response = reset(client, token_from(sender))
    assert response.status_code == 200
    assert not repository.find_account_by_id(account.id).email_verified
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": account.email, "password": NEW_PASSWORD}).status_code == 403


def test_invalid_expired_and_password_policy_safe_422(api):
    client, repository, service, account, sender, runtime = api
    response = reset(client, "unknown-token")
    assert response.status_code == 422
    assert response.json() == {"detail": "Password reset link is invalid or expired."}
    assert "unknown-token" not in response.text
    request_reset(client)
    token = token_from(sender)
    assert reset(client, token, "short").status_code == 422
    with closing(repository._connect()) as conn:
        with conn:
            conn.execute("UPDATE auth_password_resets SET expires_at='2000-01-01'")
    response = reset(client, token)
    assert response.status_code == 422
    assert response.json() == {"detail": "Password reset link is invalid or expired."}
    assert token not in response.text


def test_pages_and_fixed_login_destination(api):
    client, repository, service, account, sender, runtime = api
    login = client.get("/login")
    assert 'href="/forgot-password"' in login.text
    assert "Forgot password?" in login.text
    forgot = client.get("/forgot-password")
    assert forgot.status_code == 200
    assert 'type="email"' in forgot.text
    assert "If an eligible account exists for this email, a password reset link has been sent." in forgot.text
    page = client.get("/reset-password?token=test-token&next=https://evil.example")
    assert page.status_code == 200
    assert page.headers["referrer-policy"] == "no-referrer"
    assert page.headers["cache-control"] == "no-store"
    assert '<meta name="referrer" content="no-referrer">' in page.text
    assert "Confirm password" in page.text
    assert "Use at least 12 characters." in page.text
    assert "window.location.replace('/login')" in page.text
    assert "evil.example" not in page.text
    assert 'new URLSearchParams(window.location.search)' in page.text
    assert 'history.replaceState' in page.text
    assert 'premium.css' in page.text


@pytest.mark.parametrize("payload", [
    {"token": "raw-secret-token" * 30, "password": NEW_PASSWORD},
    {"token": "raw-secret-token", "password": "x" * 129},
    {"token": {"value": "raw-secret-token"}, "password": NEW_PASSWORD},
    {"token": "raw-secret-token", "password": NEW_PASSWORD, "extra": "raw-secret-token"},
])
def test_malformed_reset_never_echoes_token_or_password(api, payload):
    client, repository, service, account, sender, runtime = api
    response = client.post("/api/v1/auth/reset-password", json=payload)
    assert response.status_code == 422
    assert "raw-secret-token" not in response.text
    assert NEW_PASSWORD not in response.text
    assert "x" * 129 not in response.text
    assert response.json() == {"detail": "Password reset request is invalid."}
