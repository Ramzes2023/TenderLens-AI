import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.auth_pages import login_html, register_html
from app.api.config import ApiSettings
from app.api.main import create_app
from app.api.runtime import ApiRuntime
from app.auth import AuthRepository, AuthService


class AuthPageHtmlTests(unittest.TestCase):
    def test_login_page(self):
        html = login_html()
        self.assertIn("Welcome back", html)
        self.assertIn("/api/v1/auth/login", html)
        self.assertNotIn("X-API-Key", html)

    def test_register_page(self):
        html = register_html()
        self.assertIn("Create your account", html)
        self.assertIn("/api/v1/auth/register", html)
        self.assertIn("at least 12 characters", html)


class AuthPageRoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        repo = AuthRepository(Path(self.tmp.name) / "web-auth.db")
        repo.initialize()
        service = AuthService(repo)
        runtime = ApiRuntime(auth_service=service)
        settings = ApiSettings(host="127.0.0.1", port=8000, reload=False, api_key="legacy")
        self.ctx = TestClient(create_app(runtime=runtime, settings=settings), follow_redirects=False)
        self.client = self.ctx.__enter__()
        self.addCleanup(self.ctx.__exit__, None, None, None)

    def test_anonymous_redirects(self):
        root = self.client.get("/")
        self.assertEqual(root.status_code, 303)
        self.assertEqual(root.headers["location"], "/login")
        dashboard = self.client.get("/dashboard")
        self.assertEqual(dashboard.status_code, 303)
        self.assertEqual(dashboard.headers["location"], "/login")

    def test_auth_pages_open_anonymously(self):
        self.assertEqual(self.client.get("/login").status_code, 200)
        self.assertEqual(self.client.get("/register").status_code, 200)

    def test_authenticated_dashboard(self):
        registered = self.client.post(
            "/api/v1/auth/register",
            json={"email": "user@example.com", "password": "very secure password 123"},
        )
        self.assertEqual(registered.status_code, 201)
        dashboard = self.client.get("/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn("authenticated web workspace", dashboard.text)
        self.assertEqual(dashboard.headers.get("cache-control"), "no-store")
        login = self.client.get("/login")
        self.assertEqual(login.status_code, 303)
        self.assertEqual(login.headers["location"], "/dashboard")


if __name__ == "__main__":
    unittest.main()
