import unittest

from app.api.dashboard import dashboard_html


class DashboardCompanyCreationTests(unittest.TestCase):
    def test_dashboard_has_authenticated_company_creation_form(self):
        html = dashboard_html()
        self.assertIn("Add company", html)
        self.assertIn('id="companyCreator"', html)
        self.assertIn('id="companyName"', html)
        self.assertIn('id="businessMode"', html)
        self.assertIn('id="keywords"', html)
        self.assertIn("Create & activate", html)

    def test_dashboard_creates_company_through_session_api(self):
        html = dashboard_html()
        self.assertIn("async function createCompany()", html)
        self.assertIn("await api('/api/v1/companies'", html)
        self.assertIn("owner_user_id:owner()", html)
        self.assertIn("make_active:true", html)
        self.assertNotIn("X-API-Key", html)
        self.assertNotIn("sessionStorage", html)
        self.assertNotIn("Owner / Telegram user ID", html)

    def test_company_creation_refreshes_monitoring(self):
        html = dashboard_html()
        self.assertIn("Company created and activated.", html)
        self.assertIn("Promise.all([loadCompanies(),loadMonitoring()])", html)
        self.assertIn("state.hasActiveCompany", html)


if __name__ == "__main__":
    unittest.main()
