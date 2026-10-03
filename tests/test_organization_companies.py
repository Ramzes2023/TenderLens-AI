import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.config import ApiSettings
from app.api.main import create_app
from app.api.runtime import ApiRuntime
from app.api.security import SESSION_COOKIE
from app.auth import AuthRepository, AuthService
from app.companies import CompanyRepository, CompanyService
from app.organizations import OrganizationRepository, OrganizationService, Role


class OrganizationCompanyApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.path = Path(self.temp.name) / "org-companies.db"

        auth_repository = AuthRepository(self.path)
        auth_repository.initialize()

        organization_repository = OrganizationRepository(self.path)
        organization_repository.initialize()

        company_repository = CompanyRepository(self.path)
        company_repository.initialize()

        self.auth = AuthService(auth_repository)
        self.org_repo = organization_repository
        self.organizations = OrganizationService(
            organization_repository
        )
        self.companies = CompanyService(
            company_repository
        )

        self.owner = self.auth.register(
            "owner@example.com",
            "very secure password 123",
        )
        self.member = self.auth.register(
            "member@example.com",
            "very secure password 123",
        )
        self.viewer = self.auth.register(
            "viewer@example.com",
            "very secure password 123",
        )
        self.admin = self.auth.register(
            "admin@example.com",
            "very secure password 123",
        )
        self.outsider = self.auth.register(
            "outsider@example.com",
            "very secure password 123",
        )

        self.organization = self.org_repo.create(
            "Shared Procurement Team",
            self.owner.id,
        )

        self.org_repo.add_membership(
            self.organization.id,
            self.member.id,
            Role.MEMBER,
        )
        self.org_repo.add_membership(
            self.organization.id,
            self.viewer.id,
            Role.VIEWER,
        )
        self.org_repo.add_membership(
            self.organization.id,
            self.admin.id,
            Role.ADMIN,
        )

        runtime = ApiRuntime(
            auth_service=self.auth,
            organization_service=self.organizations,
            company_service=self.companies,
        )

        settings = ApiSettings(
            host="127.0.0.1",
            port=8000,
            reload=False,
            api_key="legacy-secret",
        )

        self.context = TestClient(
            create_app(
                runtime=runtime,
                settings=settings,
            )
        )
        self.client = self.context.__enter__()
        self.addCleanup(
            self.context.__exit__,
            None,
            None,
            None,
        )

    def as_account(self, account):
        self.client.cookies.clear()
        token = self.auth.create_session(account)
        self.client.cookies.set(
            SESSION_COOKIE,
            token,
        )

    @staticmethod
    def profile(name="AluTrade", keyword="aluminium"):
        return {
            "profile_version": "org-company-test",
            "company_name": name,
            "business_mode": "sell",
            "product_keywords": [keyword],
            "search_keywords": [keyword],
            "accepted_currencies": ["RUB"],
        }

    def url(self, suffix=""):
        base = (
            f"/api/v1/organizations/"
            f"{self.organization.id}/companies"
        )
        return base + suffix

    def test_shared_company_is_visible_to_other_member(self):
        self.as_account(self.owner)

        created = self.client.post(
            self.url(),
            json={
                "name": "AluTrade",
                "profile": self.profile(),
            },
        )
        self.assertEqual(
            created.status_code,
            201,
            created.text,
        )

        company_id = created.json()["id"]

        self.assertEqual(
            created.json()["organization_id"],
            self.organization.id,
        )

        # Shared organization companies must not appear through the
        # creator's legacy owner_user_id company namespace.
        legacy = self.client.get(
            "/api/v1/companies",
            params={
                "owner_user_id": self.owner.owner_user_id,
            },
        )
        self.assertEqual(
            legacy.status_code,
            200,
            legacy.text,
        )
        self.assertNotIn(
            company_id,
            [item["id"] for item in legacy.json()],
        )
        self.assertIsNone(
            self.companies.get(
                self.owner.owner_user_id,
                company_id,
            )
        )

        self.as_account(self.member)

        listed = self.client.get(self.url())
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(
            [item["id"] for item in listed.json()],
            [company_id],
        )

        detail = self.client.get(
            self.url(f"/{company_id}")
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(
            detail.json()["name"],
            "AluTrade",
        )

    def test_member_can_create_and_update(self):
        self.as_account(self.member)

        created = self.client.post(
            self.url(),
            json={
                "name": "Member Company",
                "profile": self.profile(
                    "Member Company",
                    "cable",
                ),
            },
        )
        self.assertEqual(created.status_code, 201)

        company_id = created.json()["id"]

        updated = self.client.patch(
            self.url(f"/{company_id}"),
            json={
                "name": "Updated Member Company",
            },
        )

        self.assertEqual(
            updated.status_code,
            200,
            updated.text,
        )
        self.assertEqual(
            updated.json()["name"],
            "Updated Member Company",
        )

    def test_viewer_is_read_only(self):
        self.as_account(self.owner)

        created = self.client.post(
            self.url(),
            json={
                "name": "Read Only",
                "profile": self.profile(
                    "Read Only",
                    "steel",
                ),
            },
        )
        company_id = created.json()["id"]

        self.as_account(self.viewer)

        self.assertEqual(
            self.client.get(self.url()).status_code,
            200,
        )

        create = self.client.post(
            self.url(),
            json={
                "name": "Forbidden",
                "profile": self.profile(
                    "Forbidden",
                    "forbidden",
                ),
            },
        )
        self.assertEqual(create.status_code, 403)

        update = self.client.patch(
            self.url(f"/{company_id}"),
            json={"name": "Forbidden Update"},
        )
        self.assertEqual(update.status_code, 403)

        delete = self.client.delete(
            self.url(f"/{company_id}")
        )
        self.assertEqual(delete.status_code, 403)

    def test_member_cannot_delete_but_admin_can(self):
        self.as_account(self.owner)

        created = self.client.post(
            self.url(),
            json={
                "name": "Delete Test",
                "profile": self.profile(
                    "Delete Test",
                    "pipes",
                ),
            },
        )
        company_id = created.json()["id"]

        self.as_account(self.member)
        denied = self.client.delete(
            self.url(f"/{company_id}")
        )
        self.assertEqual(denied.status_code, 403)

        self.as_account(self.admin)
        deleted = self.client.delete(
            self.url(f"/{company_id}")
        )
        self.assertEqual(deleted.status_code, 204)

        missing = self.client.get(
            self.url(f"/{company_id}")
        )
        self.assertEqual(missing.status_code, 404)

    def test_outsider_cannot_access_organization_companies(self):
        self.as_account(self.outsider)

        self.assertEqual(
            self.client.get(self.url()).status_code,
            403,
        )

        create = self.client.post(
            self.url(),
            json={
                "name": "No Access",
                "profile": self.profile(
                    "No Access",
                    "none",
                ),
            },
        )
        self.assertEqual(create.status_code, 403)

    def test_company_from_another_organization_is_not_visible(self):
        second = self.org_repo.create(
            "Second Organization",
            self.outsider.id,
        )

        company = self.companies.create_for_organization(
            self.outsider,
            second.id,
            "Second Company",
            self._profile_model(
                "Second Company",
                "second",
            ),
        )

        self.as_account(self.owner)

        response = self.client.get(
            self.url(f"/{company.id}")
        )

        self.assertEqual(response.status_code, 404)

    def _profile_model(self, name, keyword):
        from app.scoring.models import CompanyProfile

        return CompanyProfile.model_validate(
            self.profile(name, keyword)
        )

    def test_duplicate_name_is_unique_inside_organization(self):
        self.as_account(self.owner)

        first = self.client.post(
            self.url(),
            json={
                "name": "Unique Company",
                "profile": self.profile(
                    "Unique Company",
                    "one",
                ),
            },
        )
        self.assertEqual(first.status_code, 201)

        self.as_account(self.member)

        duplicate = self.client.post(
            self.url(),
            json={
                "name": "Unique Company",
                "profile": self.profile(
                    "Unique Company 2",
                    "two",
                ),
            },
        )

        self.assertEqual(duplicate.status_code, 409)

    def test_api_key_alone_is_not_organization_identity(self):
        self.client.cookies.clear()

        response = self.client.get(
            self.url(),
            headers={
                "X-API-Key": "legacy-secret",
            },
        )

        self.assertEqual(response.status_code, 401)

    def test_legacy_api_key_cannot_read_synthetic_organization_owner(self):
        from app.companies.repository import ORGANIZATION_OWNER_OFFSET

        self.as_account(self.owner)

        created = self.client.post(
            self.url(),
            json={
                "name": "Synthetic Isolation",
                "profile": self.profile(
                    "Synthetic Isolation",
                    "isolation",
                ),
            },
        )
        self.assertEqual(created.status_code, 201, created.text)

        self.client.cookies.clear()

        response = self.client.get(
            "/api/v1/companies",
            params={
                "owner_user_id":
                    ORGANIZATION_OWNER_OFFSET + self.organization.id,
            },
            headers={
                "X-API-Key": "legacy-secret",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_cross_origin_write_is_rejected(self):
        self.as_account(self.owner)

        response = self.client.post(
            self.url(),
            json={
                "name": "Blocked",
                "profile": self.profile(
                    "Blocked",
                    "blocked",
                ),
            },
            headers={
                "Origin": "https://evil.example",
                "Sec-Fetch-Site": "cross-site",
            },
        )

        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
