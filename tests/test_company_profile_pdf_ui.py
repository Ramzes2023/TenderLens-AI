import unittest

from app.api.dashboard import dashboard_html


class CompanyProfilePdfUiTests(
    unittest.TestCase
):
    def html(self):
        return dashboard_html()

    def function(
        self,
        name,
        next_name,
    ):
        html = self.html()

        start = html.index(
            f"async function {name}()"
        )

        end = html.index(
            (
                f"async function "
                f"{next_name}()"
            ),
            start,
        )

        return html[start:end]

    def test_edit_company_exposes_pdf_assistant(self):
        html = self.html()

        self.assertIn(
            'id="companyPdfAssistant"',
            html,
        )

        self.assertIn(
            'id="companyPdfFile"',
            html,
        )

        self.assertIn(
            'accept=".pdf,application/pdf"',
            html,
        )

        self.assertIn(
            "Build search profile from company PDF",
            html,
        )

        self.assertIn(
            "Apply AI profile",
            html,
        )

        self.assertIn(
            "Protected settings",
            html,
        )

        edit_start = html.index(
            "function editCompany(id)"
        )

        edit_end = html.index(
            "function companyProfileDisplay",
            edit_start,
        )

        edit_script = html[
            edit_start:edit_end
        ]

        self.assertIn(
            "companyPdfAssistant",
            edit_script,
        )

        self.assertIn(
            "classList.remove('hidden')",
            edit_script,
        )

    def test_preview_posts_pdf_without_mutating_company(self):
        script = self.function(
            "previewCompanyProfilePdf",
            "applyCompanyPdfProfile",
        )

        self.assertIn(
            "new FormData()",
            script,
        )

        self.assertIn(
            "profile-from-pdf/preview",
            script,
        )

        self.assertIn(
            "method:'POST'",
            script,
        )

        self.assertIn(
            "state.companyPdfPreview=preview",
            script,
        )

        self.assertNotIn(
            "method:'PATCH'",
            script,
        )

    def test_apply_rechecks_profile_then_uses_existing_patch(self):
        html = self.html()

        start = html.index(
            "async function applyCompanyPdfProfile()"
        )

        end = html.index(
            "async function createCompany()",
            start,
        )

        script = html[
            start:end
        ]

        self.assertIn(
            "const latest=await api",
            script,
        )

        self.assertIn(
            "JSON.stringify(latest.profile)",
            script,
        )

        self.assertIn(
            "preview.current_profile",
            script,
        )

        self.assertIn(
            "profile changed after this AI preview",
            script,
        )

        self.assertIn(
            "method:'PATCH'",
            script,
        )

        self.assertIn(
            "profile:preview.suggested_profile",
            script,
        )

        self.assertIn(
            "await loadCompanies()",
            script,
        )

    def test_ui_explains_protected_constraints(self):
        html = self.html()

        self.assertIn(
            "Budget limits, currencies",
            html,
        )

        self.assertIn(
            "hard-stop rules",
            html,
        )

        self.assertIn(
            "are preserved",
            html,
        )


if __name__ == "__main__":
    unittest.main()
