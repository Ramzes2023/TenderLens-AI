import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from app.api.main import create_app
from app.api.config import ApiSettings
from app.api.runtime import ApiRuntime
from app.api.dashboard import dashboard_html
from app.auth import AuthRepository, AuthService


class TelegramDashboardTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        repository = AuthRepository(Path(temp.name) / "test.db")
        repository.initialize()
        self.service = AuthService(repository)
        context = TestClient(create_app(
            runtime=ApiRuntime(auth_service=self.service),
            settings=ApiSettings(host="127.0.0.1", port=8000, reload=False),
        ))
        self.client = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)

    def register(self):
        response = self.client.post("/api/v1/auth/register", json={
            "email": "ui@example.com", "password": "test-password-strong-123"})
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.json()["telegram_connected"])
        return response.json()

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
