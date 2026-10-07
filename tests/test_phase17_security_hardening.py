import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from fastapi import Depends, FastAPI, Request


class RecordingEmailSender:
    public_base_url = "http://testserver"

    def __init__(self):
        self.messages = []

    def send_verification(
        self,
        *,
        recipient,
        verification_url,
        expires_at,
    ):
        self.messages.append(
            {
                "recipient": recipient,
                "verification_url": verification_url,
                "expires_at": expires_at,
            }
        )
from fastapi.security import APIKeyHeader
from fastapi.testclient import TestClient

from app.api.config import ApiSettings
from app.api.main import create_app
from app.api.runtime import ApiRuntime
from app.api.security import LoginRateLimiter, require_api_or_session
from app.auth import AuthRepository, AuthService, TelegramLinkError


class Phase17SecurityHardeningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "security.db"
        self.repository = AuthRepository(self.path)
        self.repository.initialize()
        self.service = AuthService(self.repository)
        self.email_sender = RecordingEmailSender()

    def _main_client(self):
        app = create_app(
            runtime=ApiRuntime(
                auth_service=self.service,
                email_sender=self.email_sender,
            ),
            settings=ApiSettings(
                host="127.0.0.1",
                port=8000,
                reload=False,
                api_key="legacy-api-secret",
            ),
        )
        ctx = TestClient(app)
        client = ctx.__enter__()
        self.addCleanup(ctx.__exit__, None, None, None)
        return app, client

    def _verify_latest(self, client):
        url = self.email_sender.messages[-1][
            "verification_url"
        ]
        token = parse_qs(
            urlsplit(url).query
        )["token"][0]

        response = client.post(
            "/api/v1/auth/verify-email",
            json={"token": token},
        )

        self.assertEqual(
            response.status_code,
            200,
        )

    def test_explicit_cross_origin_auth_write_is_blocked(self):
        _app, client = self._main_client()
        registered = client.post(
            "/api/v1/auth/register",
            json={"email": "origin@example.com", "password": "very secure password 123"},
        )
        self.assertEqual(registered.status_code, 201)
        self._verify_latest(client)

        blocked = client.post(
            "/api/v1/auth/telegram-link",
            headers={"Origin": "https://evil.example"},
        )
        self.assertEqual(blocked.status_code, 403)

        allowed = client.post(
            "/api/v1/auth/telegram-link",
            headers={"Origin": "http://testserver"},
        )
        self.assertEqual(allowed.status_code, 200)

    def test_session_origin_guard_and_legacy_api_key_compatibility(self):
        account = self.service.register("guard@example.com", "very secure password 123")
        token = self.service.create_session(account)

        api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)
        app = FastAPI()
        app.state.api_settings = ApiSettings(
            host="127.0.0.1",
            port=8000,
            reload=False,
            api_key="legacy-api-secret",
        )
        app.state.runtime = SimpleNamespace(auth_service=self.service)

        @app.post("/protected")
        async def protected(request: Request, key: str | None = Depends(api_key_scheme)):
            resolved = await require_api_or_session(request, key)
            return {"session": resolved is not None}

        with TestClient(app) as client:
            client.cookies.set("tenderlens_session", token)
            blocked = client.post("/protected", headers={"Origin": "https://evil.example"})
            self.assertEqual(blocked.status_code, 403)
            allowed = client.post("/protected", headers={"Origin": "http://testserver"})
            self.assertEqual(allowed.status_code, 200)
            self.assertTrue(allowed.json()["session"])

            client.cookies.clear()
            legacy = client.post(
                "/protected",
                headers={"X-API-Key": "legacy-api-secret"},
            )
            self.assertEqual(legacy.status_code, 200)
            self.assertFalse(legacy.json()["session"])

    def test_login_rate_limit_and_window_recovery(self):
        app, client = self._main_client()
        clock = [1000.0]
        app.state.login_rate_limiter = LoginRateLimiter(
            max_failures=3,
            window_seconds=60,
            max_entries=32,
            clock=lambda: clock[0],
        )

        created = client.post(
            "/api/v1/auth/register",
            json={"email": "rate@example.com", "password": "very secure password 123"},
        )
        self.assertEqual(created.status_code, 201)
        self._verify_latest(client)
        self.assertEqual(client.post("/api/v1/auth/logout").status_code, 204)

        payload = {"email": "rate@example.com", "password": "definitely wrong password"}
        self.assertEqual(client.post("/api/v1/auth/login", json=payload).status_code, 401)
        self.assertEqual(client.post("/api/v1/auth/login", json=payload).status_code, 401)
        limited = client.post("/api/v1/auth/login", json=payload)
        self.assertEqual(limited.status_code, 429)
        self.assertIn("Retry-After", limited.headers)

        clock[0] += 61
        success = client.post(
            "/api/v1/auth/login",
            json={"email": "rate@example.com", "password": "very secure password 123"},
        )
        self.assertEqual(success.status_code, 200)

    def test_session_creation_cleans_expired_but_keeps_active_sessions(self):
        account = self.service.register("sessions@example.com", "very secure password 123")
        self.repository.create_session(
            account_id=account.id,
            token_hash="expired-session",
            expires_at="2000-01-01T00:00:00+00:00",
        )
        self.repository.create_session(
            account_id=account.id,
            token_hash="active-session",
            expires_at="2999-01-01T00:00:00+00:00",
        )

        self.service.create_session(account)

        with closing(sqlite3.connect(self.path)) as conn:
            tokens = {row[0] for row in conn.execute("SELECT token_hash FROM auth_sessions")}
        self.assertNotIn("expired-session", tokens)
        self.assertIn("active-session", tokens)
        self.assertEqual(len(tokens), 2)

    def test_stale_web_account_cannot_create_ticket_after_owner_link(self):
        account = self.service.register("stale@example.com", "very secure password 123")
        stale = account
        self.repository.link_owner(account.id, 1844282717)

        with self.assertRaisesRegex(TelegramLinkError, "already connected"):
            self.service.create_telegram_link(stale)

        with closing(sqlite3.connect(self.path)) as conn:
            count = conn.execute("SELECT COUNT(*) FROM auth_telegram_links").fetchone()[0]
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
