import unittest
from app.api.dashboard import dashboard_html
from app.api.routes import router


class DashboardTests(unittest.TestCase):
    def test_routes_registered(self):
        paths = {getattr(route, "path", None) for route in router.routes}
        for path in ("/", "/login", "/register", "/dashboard"):
            self.assertIn(path, paths)

    def test_core_sections(self):
        html = dashboard_html()
        for text in (
            "TenderLens AI", "Company workspaces", "Recent analyzed documents",
            "Live EIS scan", "/api/v1/companies", "/api/v1/monitoring/status",
            "/api/v1/monitoring/scan",
        ):
            self.assertIn(text, html)

    def test_dashboard_uses_session_not_manual_credentials(self):
        html = dashboard_html()
        self.assertIn("/api/v1/auth/me", html)
        self.assertIn("/api/v1/auth/logout", html)
        self.assertIn("credentials:'same-origin'", html)
        self.assertNotIn("X-API-Key", html)
        self.assertNotIn("sessionStorage", html)
        self.assertNotIn('id="ownerId"', html)
        self.assertNotIn('id="apiKey"', html)

    def test_no_secrets_embedded(self):
        html = dashboard_html()
        for secret in ("GIGACHAT_CREDENTIALS", "TELEGRAM_BOT_TOKEN", "TENDERLENS_API_KEY"):
            self.assertNotIn(secret, html)


if __name__ == "__main__":
    unittest.main()
