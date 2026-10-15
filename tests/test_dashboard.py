import unittest

from app.api.auth_pages import (
    login_html,
    register_html,
)
from app.api.dashboard import dashboard_html
from app.api.invitation_page import (
    invitation_page_html,
)
from app.api.routes import (
    _safe_next_path,
    router,
)


class DashboardTests(unittest.TestCase):
    def test_routes_registered(self):
        paths = {getattr(route, "path", None) for route in router.routes}
        for path in (
            "/",
            "/login",
            "/register",
            "/verify-email",
            "/invite/{token}",
            "/dashboard",
        ):
            self.assertIn(path, paths)

    def test_core_sections(self):
        html = dashboard_html()
        for text in (
            "VALYQON AI",
            "Company workspaces",
            "Recent analyzed documents",
            "Live EIS scan",
            "Team &amp; organizations",
            "Create organization",
            "Copy invite link",
            "/api/v1/companies",
            "/api/v1/monitoring/status",
            "/api/v1/monitoring/scan",
            "/api/v1/organizations",
            "/invitations",
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

    def test_invitation_page_uses_preview_and_accept_api(self):
        html = invitation_page_html(
            "sample-token"
        )

        self.assertIn(
            "/api/v1/organizations/invitations/",
            html,
        )

        self.assertIn(
            "/accept",
            html,
        )

        self.assertIn(
            "/login?next=",
            html,
        )

        self.assertIn(
            "/register?next=",
            html,
        )

        self.assertNotIn(
            "X-API-Key",
            html,
        )

    def test_auth_pages_preserve_invitation_return(self):
        next_path = (
            "/invite/sample-token"
        )

        login = login_html(
            next_path
        )

        register = register_html(
            next_path
        )

        self.assertIn(
            'encodeURIComponent("/invite/sample-token")',
            login,
        )

        self.assertIn(
            'encodeURIComponent("/invite/sample-token")',
            register,
        )

        self.assertIn(
            '"/invite/sample-token"',
            login,
        )

        self.assertIn(
            "/verify-email?email=",
            register,
        )

        self.assertIn(
            "?next=",
            login,
        )

        self.assertIn(
            "?next=",
            register,
        )

    def test_auth_return_path_rejects_external_redirects(self):
        self.assertEqual(
            _safe_next_path(
                "https://evil.example"
            ),
            "/dashboard",
        )

        self.assertEqual(
            _safe_next_path(
                "//evil.example"
            ),
            "/dashboard",
        )

        self.assertEqual(
            _safe_next_path(
                "/invite/sample-token"
            ),
            "/invite/sample-token",
        )

    def test_inline_invitation_values_are_script_safe(self):
        malicious = (
            "</script><script>alert(1)</script>"
        )

        invitation = invitation_page_html(
            malicious
        )

        auth = login_html(
            "/invite/" + malicious
        )

        self.assertNotIn(
            'const token="</script>',
            invitation,
        )

        self.assertNotIn(
            'window.location.replace("/invite/</script>',
            auth,
        )

        self.assertIn(
            "\\u003c",
            invitation,
        )

        self.assertIn(
            "\\u003c",
            auth,
        )

    def test_dashboard_preserves_personal_and_shared_workspace_routes(self):
        html = dashboard_html()

        # Personal/legacy compatibility.
        self.assertIn(
            "/api/v1/companies?owner_user_id=",
            html,
        )

        self.assertIn(
            "/api/v1/tenders?owner_user_id=",
            html,
        )

        self.assertIn(
            "/api/v1/monitoring/status?owner_user_id=",
            html,
        )

        # Shared organization workspace.
        self.assertIn(
            "/companies",
            html,
        )

        self.assertIn(
            "/monitoring/status",
            html,
        )

        self.assertIn(
            "/monitoring/scan",
            html,
        )

        self.assertIn(
            "/tenders?limit=20",
            html,
        )

        self.assertIn(
            "/membership/me",
            html,
        )

        self.assertIn(
            "usingSharedOrganization",
            html,
        )

        self.assertIn(
            "canWriteWorkspace",
            html,
        )

    def test_no_secrets_embedded(self):
        html = dashboard_html()
        for secret in ("GIGACHAT_CREDENTIALS", "TELEGRAM_BOT_TOKEN", "TENDERLENS_API_KEY"):
            self.assertNotIn(secret, html)


if __name__ == "__main__":
    unittest.main()
