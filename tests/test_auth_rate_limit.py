"""Deterministic authentication admission tests; real SMTP is forbidden."""
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from app.api.config import ApiSettings
from app.api.main import create_app
from app.api.runtime import ApiRuntime
from app.api.security import AuthRateLimiter, AuthRatePolicy
from app.auth import AuthRepository, AuthService

PASSWORD = "original secure password 123"
NEW_PASSWORD = "replacement secure password 456"
DETAIL = {"detail": "Too many attempts. Please try again later."}


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class Sender:
    public_base_url = "https://accounts.valyqon.example"

    def __init__(self):
        self.messages = []

    def send_verification(self, **kwargs):
        self.messages.append(kwargs)

    def send_password_reset(self, **kwargs):
        self.messages.append(kwargs)

    def token(self, kind):
        return parse_qs(urlsplit(self.messages[-1][kind + "_url"]).query)["token"][0]


@pytest.fixture(autouse=True)
def no_smtp(monkeypatch):
    monkeypatch.setenv("VALYQON_EMAIL_MODE", "disabled")
    with patch("smtplib.SMTP") as smtp, patch("smtplib.SMTP_SSL") as ssl:
        smtp.side_effect = ssl.side_effect = AssertionError("Real email forbidden")
        yield
        smtp.assert_not_called()
        ssl.assert_not_called()


@pytest.fixture
def api(tmp_path):
    repository = AuthRepository(tmp_path / "rate.db")
    repository.initialize()
    service = AuthService(repository)
    sender = Sender()
    app = create_app(
        runtime=ApiRuntime(auth_service=service, email_sender=sender),
        settings=ApiSettings(host="127.0.0.1", port=8000, reload=False, api_key=None),
    )
    clock = Clock()
    app.state.login_rate_limiter = AuthRateLimiter(clock=clock)
    with TestClient(app) as client:
        yield client, service, sender, app.state.login_rate_limiter, clock


def post(client, endpoint, **body):
    return client.post("/api/v1/auth/" + endpoint, json=body)


def assert_limited(response):
    assert response.status_code == 429
    assert response.json() == DETAIL
    assert response.headers["retry-after"].isdigit()
    assert int(response.headers["retry-after"]) >= 1
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("endpoint,body,initial", [
    ("login", {"email": "unknown@example.com", "password": PASSWORD}, 401),
    ("register", {"email": "user@example.com", "password": "short"}, 422),
    ("forgot-password", {"email": "unknown@example.com"}, 202),
    ("resend-verification", {"email": "unknown@example.com"}, 202),
    ("verify-email", {"token": "raw-invalid-verification-token"}, 422),
    ("reset-password", {"token": "raw-invalid-reset-token", "password": PASSWORD}, 422),
])
def test_endpoint_limits_and_recovery(api, endpoint, body, initial):
    client, service, sender, limiter, clock = api
    limit = limiter.policies[endpoint].identifier_limit
    # Login retains the former behavior: the final failed credential attempt is 429.
    for _ in range(limit - (endpoint == "login")):
        assert post(client, endpoint, **body).status_code == initial
    assert_limited(post(client, endpoint, **body))
    assert_limited(post(client, endpoint, **body))
    assert not sender.messages
    state = repr(limiter._events)
    for name in ("email", "token", "password"):
        if name in body:
            assert body[name] not in state
    clock.now += limiter.policies[endpoint].window_seconds
    assert post(client, endpoint, **body).status_code == initial


@pytest.mark.parametrize("endpoint", ["forgot-password", "resend-verification"])
@pytest.mark.parametrize("kind", ["known", "unknown", "verified", "inactive"])
def test_equivalent_accounting(api, endpoint, kind):
    client, service, sender, limiter, clock = api
    email = "subject@example.com"
    if kind != "unknown":
        account = service.register(email, PASSWORD)
        if kind == "verified":
            token, _ = service.issue_email_verification(account)
            service.verify_email(token)
        elif kind == "inactive":
            with service.repository._connect() as conn:
                conn.execute("UPDATE auth_accounts SET is_active=0 WHERE id=?", (account.id,))
                conn.commit()
    for _ in range(limiter.policies[endpoint].identifier_limit):
        response = post(client, endpoint, email=email)
        assert response.status_code == 202
        assert response.json() == {"accepted": True}
    assert_limited(post(client, endpoint, email=email))
    assert len(sender.messages) == (kind == "known" or (kind == "verified" and endpoint == "forgot-password"))


@pytest.mark.parametrize("header", ["X-Forwarded-For", "Forwarded", "X-Real-IP"])
def test_spoofed_proxy_headers_cannot_bypass_client_budget(api, header):
    client, service, sender, limiter, clock = api
    for index in range(limiter.policies["forgot-password"].client_limit):
        response = client.post(
            "/api/v1/auth/forgot-password", json={"email": f"user{index}@example.com"},
            headers={header: f"for=198.51.100.{index}"},
        )
        assert response.status_code == 202
    assert_limited(client.post(
        "/api/v1/auth/forgot-password", json={"email": "another@example.com"},
        headers={header: "for=203.0.113.1"},
    ))


def test_normalized_email_and_distributed_identity_budget(api):
    client, service, sender, limiter, clock = api
    for email in ["user@example.com", "USER@EXAMPLE.COM", " user@example.com "] * 2:
        assert post(client, "forgot-password", email=email).status_code == 202
    assert_limited(post(client, "forgot-password", email=" User@Example.com "))
    assert limiter.consume("forgot-password", "different-peer", "user@example.com", email=True)
    assert "user@example.com" not in repr(limiter._events)


@pytest.mark.parametrize("route", ["verify-email", "reset-password"])
def test_token_identifier_budget_across_clients(route):
    limiter = AuthRateLimiter(clock=Clock())
    for index in range(limiter.policies[route].identifier_limit):
        assert limiter.consume(route, str(index), "private-raw-token") is None
    assert limiter.consume(route, "another-peer", "private-raw-token")
    assert "private-raw-token" not in repr(limiter._events)


def test_expiry_cleanup_and_bounded_memory_fail_closed():
    clock = Clock()
    limiter = AuthRateLimiter(max_entries=4, clock=clock)
    assert limiter.consume("login", "peer", "first", email=True) is None
    assert limiter.consume("login", "peer", "second", email=True) is None
    assert limiter.consume("login", "peer", "third", email=True) is None
    original = dict(limiter._events)
    for index in range(100):
        assert limiter.consume("login", "other-peer", str(index), email=True)
    assert dict(limiter._events) == original
    assert len(limiter._events) == 4
    clock.now += 300
    assert limiter.consume("login", "new-peer", "fresh", email=True) is None
    assert len(limiter._events) == 2
    assert not set(original).intersection(limiter._events)


def test_concurrent_admission_is_atomic_and_event_storage_bounded():
    limiter = AuthRateLimiter(clock=Clock())
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda _: limiter.consume(
            "login", "peer", "subject@example.com", email=True,
        ), range(200)))
    assert results.count(None) == 5
    assert len(limiter._events) == 2
    assert all(len(events) == 5 for events in limiter._events.values())


def test_each_application_has_isolated_state(api):
    client, service, sender, limiter, clock = api
    for _ in range(6):
        post(client, "forgot-password", email="unknown@example.com")
    other = create_app(
        runtime=ApiRuntime(auth_service=service, email_sender=sender),
        settings=ApiSettings(host="127.0.0.1", port=8000, reload=False, api_key=None),
    )
    with TestClient(other) as other_client:
        assert post(other_client, "forgot-password", email="unknown@example.com").status_code == 202
    assert_limited(post(client, "forgot-password", email="unknown@example.com"))


def test_normal_flows_and_successful_login_relaxes_only_email(api):
    client, service, sender, limiter, clock = api
    email = "normal@example.com"
    assert post(client, "register", email=email, password=PASSWORD).status_code == 201
    verification = sender.token("verification")
    assert post(client, "login", email=email, password=PASSWORD).status_code == 403
    assert post(client, "verify-email", token=verification).status_code == 200
    assert post(client, "verify-email", token=verification).status_code == 422
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert post(client, "login", email=email, password="wrong").status_code == 401
    assert post(client, "login", email=email, password=PASSWORD).status_code == 200
    keys = limiter.keys("login", "testclient", email, email=True)
    assert keys[1] not in limiter._events
    assert len(limiter._events[keys[0]]) == 3
    account = service.repository.find_account_by_email(email)[0]
    old_sessions = [service.create_session(account) for _ in range(2)]
    assert post(client, "forgot-password", email=email).status_code == 202
    reset = sender.token("reset")
    assert post(client, "reset-password", token=reset, password=NEW_PASSWORD).status_code == 200
    assert all(service.account_for_token(token) is None for token in old_sessions)
    assert client.get("/api/v1/auth/me").status_code == 401
    assert post(client, "reset-password", token=reset, password=NEW_PASSWORD).status_code == 422
    assert post(client, "login", email=email, password=NEW_PASSWORD).status_code == 200


def test_reset_preserves_unverified_status(api):
    client, service, sender, limiter, clock = api
    account = service.register("unverified@example.com", PASSWORD)
    assert post(client, "forgot-password", email=account.email).status_code == 202
    assert post(client, "reset-password", token=sender.token("reset"), password=NEW_PASSWORD).status_code == 200
    assert not service.repository.find_account_by_id(account.id).email_verified
    assert post(client, "login", email=account.email, password=NEW_PASSWORD).status_code == 403
    assert client.get("/api/v1/auth/me").status_code == 401


def test_authenticated_telegram_ticket_generation_is_limited(api):
    client, service, sender, limiter, clock = api
    account = service.register("linked@example.com", PASSWORD)
    verification, _ = service.issue_email_verification(account)
    account = service.verify_email(verification)
    client.cookies.set("tenderlens_session", service.create_session(account))
    with patch.object(service, "create_telegram_link", return_value=("fake-ticket", "2099-01-01")):
        for _ in range(limiter.policies["telegram-link"].identifier_limit):
            assert post(client, "telegram-link").status_code == 200
        assert_limited(post(client, "telegram-link"))


def test_success_cannot_clear_client_budget(api):
    client, service, sender, limiter, clock = api
    account = service.register("success@example.com", PASSWORD)
    token, _ = service.issue_email_verification(account)
    service.verify_email(token)
    # Small injected budget exercises repeated successful credential use.
    policies = dict(limiter.policies)
    policies["login"] = AuthRatePolicy(3, 5)
    client.app.state.login_rate_limiter = AuthRateLimiter(policies=policies, clock=clock)
    for _ in range(3):
        assert post(client, "login", email=account.email, password=PASSWORD).status_code == 200
    assert_limited(post(client, "login", email=account.email, password=PASSWORD))


def test_sliding_window_retry_rounding_and_cross_route_cleanup():
    clock = Clock()
    limiter = AuthRateLimiter(clock=clock)
    for _ in range(5):
        assert limiter.consume("login", "peer", "email", email=True) is None
    clock.now += 299.25
    assert limiter.consume("login", "peer", "email", email=True) == 1
    clock.now += .75
    assert limiter.consume("verify-email", "peer", "token") is None
    assert all(key[0] == "verify-email" for key in limiter._events)
