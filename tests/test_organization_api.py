import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.config import ApiSettings
from app.api.main import create_app
from app.api.runtime import ApiRuntime
from app.api.security import SESSION_COOKIE
from app.auth import AuthRepository, AuthService
from app.organizations import OrganizationRepository, OrganizationService


class OrganizationApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.path = Path(self.temp.name) / "organization-api.db"

        auth_repository = AuthRepository(self.path)
        auth_repository.initialize()

        organization_repository = OrganizationRepository(self.path)
        organization_repository.initialize()

        self.auth = AuthService(auth_repository)
        self.organizations = OrganizationService(
            organization_repository
        )

        self.a = self.auth.register(
            "a@example.com",
            "very secure password 123",
        )
        self.b = self.auth.register(
            "b@example.com",
            "very secure password 123",
        )
        self.c = self.auth.register(
            "c@example.com",
            "very secure password 123",
        )

        runtime = ApiRuntime(
            auth_service=self.auth,
            organization_service=self.organizations,
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

    def create_shared(self, name="Shared Workspace"):
        response = self.client.post(
            "/api/v1/organizations",
            json={"name": name},
        )
        self.assertEqual(
            response.status_code,
            201,
            response.text,
        )
        return response.json()

    def test_session_required_and_api_key_is_not_identity(self):
        self.client.cookies.clear()

        response = self.client.get(
            "/api/v1/organizations",
            headers={"X-API-Key": "legacy-secret"},
        )

        self.assertEqual(response.status_code, 401)

    def test_list_default_create_and_cross_org_isolation(self):
        self.as_account(self.a)

        listed = self.client.get(
            "/api/v1/organizations"
        )
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()), 1)
        self.assertTrue(listed.json()[0]["personal"])

        default = self.client.get(
            "/api/v1/organizations/default"
        )
        self.assertEqual(default.status_code, 200)
        personal_id = default.json()["id"]

        shared = self.create_shared()

        listed = self.client.get(
            "/api/v1/organizations"
        )
        self.assertEqual(len(listed.json()), 2)

        self.as_account(self.b)
        forbidden = self.client.get(
            f"/api/v1/organizations/{shared['id']}"
        )
        self.assertEqual(forbidden.status_code, 403)

        own = self.client.get(
            "/api/v1/organizations/default"
        )
        self.assertNotEqual(
            own.json()["id"],
            personal_id,
        )

    def test_owner_and_admin_member_management(self):
        self.as_account(self.a)
        organization = self.create_shared()
        org_id = organization["id"]

        add_admin = self.client.post(
            f"/api/v1/organizations/{org_id}/members",
            json={
                "account_id": self.b.id,
                "role": "admin",
            },
        )
        self.assertEqual(
            add_admin.status_code,
            201,
            add_admin.text,
        )

        self.as_account(self.b)

        members = self.client.get(
            f"/api/v1/organizations/{org_id}/members"
        )
        self.assertEqual(members.status_code, 200)

        add_viewer = self.client.post(
            f"/api/v1/organizations/{org_id}/members",
            json={
                "account_id": self.c.id,
                "role": "viewer",
            },
        )
        self.assertEqual(
            add_viewer.status_code,
            201,
            add_viewer.text,
        )

        cannot_grant_owner = self.client.patch(
            f"/api/v1/organizations/{org_id}/members/{self.c.id}",
            json={"role": "owner"},
        )
        self.assertEqual(
            cannot_grant_owner.status_code,
            409,
        )

        self.as_account(self.a)

        promote = self.client.patch(
            f"/api/v1/organizations/{org_id}/members/{self.c.id}",
            json={"role": "owner"},
        )
        self.assertEqual(
            promote.status_code,
            200,
            promote.text,
        )
        self.assertEqual(
            promote.json()["role"],
            "owner",
        )

    def test_last_owner_cannot_be_demoted_or_removed(self):
        self.as_account(self.a)
        organization = self.create_shared(
            "Last Owner Test"
        )
        org_id = organization["id"]

        demote = self.client.patch(
            f"/api/v1/organizations/{org_id}/members/{self.a.id}",
            json={"role": "admin"},
        )
        self.assertEqual(demote.status_code, 409)

        remove = self.client.delete(
            f"/api/v1/organizations/{org_id}/members/{self.a.id}"
        )
        self.assertEqual(remove.status_code, 409)

    def test_personal_owner_is_permanent_even_with_second_owner(self):
        self.as_account(self.a)

        personal = self.client.get(
            "/api/v1/organizations/default"
        ).json()
        org_id = personal["id"]

        added = self.client.post(
            f"/api/v1/organizations/{org_id}/members",
            json={
                "account_id": self.b.id,
                "role": "owner",
            },
        )
        self.assertEqual(added.status_code, 201)

        demote = self.client.patch(
            f"/api/v1/organizations/{org_id}/members/{self.a.id}",
            json={"role": "member"},
        )
        self.assertEqual(demote.status_code, 409)

        remove = self.client.delete(
            f"/api/v1/organizations/{org_id}/members/{self.a.id}"
        )
        self.assertEqual(remove.status_code, 409)

    def test_member_can_read_own_role_without_manager_access(self):
        self.as_account(self.a)

        organization = self.create_shared(
            "Own Membership Test"
        )

        org_id = organization["id"]

        added = self.client.post(
            f"/api/v1/organizations/{org_id}/members",
            json={
                "account_id": self.b.id,
                "role": "viewer",
            },
        )

        self.assertEqual(
            added.status_code,
            201,
            added.text,
        )

        self.as_account(self.b)

        own = self.client.get(
            f"/api/v1/organizations/{org_id}/membership/me"
        )

        self.assertEqual(
            own.status_code,
            200,
            own.text,
        )

        self.assertEqual(
            own.json()["account_id"],
            self.b.id,
        )

        self.assertEqual(
            own.json()["role"],
            "viewer",
        )

        manager_list = self.client.get(
            f"/api/v1/organizations/{org_id}/members"
        )

        self.assertEqual(
            manager_list.status_code,
            403,
        )

        self.as_account(self.c)

        outsider = self.client.get(
            f"/api/v1/organizations/{org_id}/membership/me"
        )

        self.assertEqual(
            outsider.status_code,
            403,
        )

    def test_non_manager_cannot_list_or_manage_members(self):
        self.as_account(self.a)
        organization = self.create_shared(
            "Viewer Test"
        )
        org_id = organization["id"]

        add_viewer = self.client.post(
            f"/api/v1/organizations/{org_id}/members",
            json={
                "account_id": self.b.id,
                "role": "viewer",
            },
        )
        self.assertEqual(add_viewer.status_code, 201)

        self.as_account(self.b)

        listed = self.client.get(
            f"/api/v1/organizations/{org_id}/members"
        )
        self.assertEqual(listed.status_code, 403)

        mutation = self.client.post(
            f"/api/v1/organizations/{org_id}/members",
            json={
                "account_id": self.c.id,
                "role": "member",
            },
        )
        self.assertEqual(mutation.status_code, 403)

    def test_cross_origin_write_is_rejected(self):
        self.as_account(self.a)

        response = self.client.post(
            "/api/v1/organizations",
            json={"name": "Blocked"},
            headers={
                "Origin": "https://evil.example",
                "Sec-Fetch-Site": "cross-site",
            },
        )

        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
