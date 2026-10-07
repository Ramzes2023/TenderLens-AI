import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient
from app.api.main import create_app
from app.api.config import ApiSettings
from app.api.runtime import ApiRuntime
from app.api.dashboard import dashboard_html
from app.auth import AuthRepository, AuthService


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
                "verification_url":
                    verification_url,
                "expires_at":
                    expires_at,
            }
        )


class TelegramDashboardTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        repository = AuthRepository(Path(temp.name) / "test.db")
        repository.initialize()
        self.service = AuthService(repository)
        self.email_sender = RecordingEmailSender()

        context = TestClient(create_app(
            runtime=ApiRuntime(
                auth_service=self.service,
                email_sender=self.email_sender,
            ),
            settings=ApiSettings(
                host="127.0.0.1",
                port=8000,
                reload=False,
            ),
        ))
        self.client = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)

    def register(self):
        response = self.client.post(
            "/api/v1/auth/register",
            json={
                "email":
                    "ui@example.com",
                "password":
                    "test-password-strong-123",
            },
        )

        self.assertEqual(
            response.status_code,
            201,
        )

        self.assertNotIn(
            "tenderlens_session=",
            response.headers.get(
                "set-cookie",
                "",
            ),
        )

        self.assertTrue(
            self.email_sender.messages
        )

        url = (
            self.email_sender
            .messages[-1][
                "verification_url"
            ]
        )

        token = parse_qs(
            urlsplit(url).query
        )["token"][0]

        verified = self.client.post(
            "/api/v1/auth/verify-email",
            json={
                "token": token,
            },
        )

        self.assertEqual(
            verified.status_code,
            200,
        )

        account = verified.json()

        self.assertTrue(
            account[
                "email_verified"
            ]
        )

        self.assertFalse(
            account[
                "telegram_connected"
            ]
        )

        return account

    def test_anonymous_cannot_link(self):
        self.assertEqual(self.client.post("/api/v1/auth/telegram-link").status_code, 401)

    def test_link_status_migration_and_same_session(self):
        account = self.register()
        self.assertFalse(self.client.get("/api/v1/auth/me").json()["telegram_connected"])
        response = self.client.post("/api/v1/auth/telegram-link")
        self.assertEqual(response.status_code, 200)
        ticket = response.json()
        self.assertNotIn("token", ticket)
        self.assertTrue(ticket["start_parameter"].startswith("link_"))
        raw_token = ticket["start_parameter"][len("link_"):]
        self.service.consume_telegram_link(raw_token, 123456789)
        current = self.client.get("/api/v1/auth/me").json()
        self.assertTrue(current["telegram_connected"])
        self.assertEqual(current["id"], account["id"])
        self.assertEqual(self.client.post("/api/v1/auth/telegram-link").status_code, 409)
        self.client.post("/api/v1/auth/logout")
        login = self.client.post("/api/v1/auth/login", json={
            "email": "ui@example.com", "password": "test-password-strong-123"})
        self.assertEqual(login.status_code, 200)
        self.assertTrue(login.json()["telegram_connected"])

    def test_dashboard_and_existing_company_ui(self):
        self.register()
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIn('id="telegramCard"', response.text)
        self.assertIn('id="createCompanyButton"', response.text)
        self.assertIn("telegram_connected", response.text)
        self.assertNotIn("4000000000000", response.text)
        self.assertNotIn("WEB_OWNER_OFFSET", response.text)
        self.assertNotIn("TELEGRAM_BOT_TOKEN", response.text)

    def test_bounded_refresh_and_secret_storage(self):
        html = dashboard_html()
        self.assertIn("120000", html)
        self.assertIn("2500", html)
        self.assertIn("pagehide", html)
        self.assertIn("AbortController", html)
        self.assertNotIn("localStorage", html)
        self.assertNotIn("sessionStorage", html)
        self.assertNotIn("console.log", html)
