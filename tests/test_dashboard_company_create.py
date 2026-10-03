import unittest

from app.api.dashboard import dashboard_html


class DashboardCompanyCreationTests(unittest.TestCase):
    def _create_company_script(self):
        html = dashboard_html()

        start = html.index(
            "async function createCompany()"
        )

        end = html.index(
            "async function activateCompany",
            start,
        )

        return html[start:end]

    def test_dashboard_has_authenticated_company_creation_form(self):
        html = dashboard_html()

        self.assertIn(
            "Add company",
            html,
        )

        self.assertIn(
            'id="companyCreator"',
            html,
        )

        self.assertIn(
            'id="companyName"',
            html,
        )

        self.assertIn(
            'id="businessMode"',
            html,
        )

        self.assertIn(
            'id="keywords"',
            html,
        )

        self.assertIn(
            "Create & activate",
            html,
        )

    def test_dashboard_creates_company_through_session_api(self):
        html = dashboard_html()
        script = self._create_company_script()

        self.assertIn(
            "async function createCompany()",
            html,
        )

        # Personal workspace keeps the v1.5 session API.
        self.assertIn(
            "'/api/v1/companies'",
            script,
        )

        self.assertIn(
            "owner_user_id:owner()",
            script,
        )

        self.assertIn(
            "make_active:true",
            script,
        )

        # Shared workspace uses organization-scoped companies.
        self.assertIn(
            "usingSharedOrganization()",
            script,
        )

        self.assertIn(
            "${organizationBase()}/companies",
            script,
        )

        self.assertIn(
            "/activate",
            script,
        )

        self.assertNotIn(
            "X-API-Key",
            html,
        )

        self.assertNotIn(
            "sessionStorage",
            html,
        )

        self.assertNotIn(
            "Owner / Telegram user ID",
            html,
        )

    def test_company_creation_refreshes_monitoring(self):
        html = dashboard_html()
        script = self._create_company_script()

        self.assertIn(
            "Company created and activated.",
            script,
        )

        self.assertIn(
            "await Promise.all",
            script,
        )

        self.assertIn(
            "loadCompanies()",
            script,
        )

        self.assertIn(
            "loadMonitoring()",
            script,
        )

        self.assertIn(
            "state.hasActiveCompany",
            html,
        )


if __name__ == "__main__":
    unittest.main()
