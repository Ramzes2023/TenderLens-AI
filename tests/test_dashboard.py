import unittest

from app.api.dashboard import dashboard_html
from app.api.routes import router


class DashboardTests(unittest.TestCase):
    def test_dashboard_route_is_registered(self):
        paths = {getattr(route, "path", None) for route in router.routes}
        self.assertIn("/dashboard", paths)

    def test_dashboard_contains_core_workspace_sections(self):
        html = dashboard_html()
        self.assertIn("TenderLens AI", html)
        self.assertIn("Company workspaces", html)
        self.assertIn("Recent analyzed documents", html)
        self.assertIn("Live EIS scan", html)
        self.assertIn("/api/v1/companies", html)
        self.assertIn("/api/v1/monitoring/status", html)
        self.assertIn("/api/v1/monitoring/scan", html)

    def test_dashboard_does_not_embed_api_key(self):
        html = dashboard_html()
        self.assertIn('type="password"', html)
        self.assertIn("sessionStorage", html)
        self.assertNotIn("GIGACHAT_CREDENTIALS", html)
        self.assertNotIn("TELEGRAM_BOT_TOKEN", html)

    def test_dashboard_uses_existing_api_key_header(self):
        html = dashboard_html()
        self.assertIn("X-API-Key", html)


if __name__ == "__main__":
    unittest.main()
