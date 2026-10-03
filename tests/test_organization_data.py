import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.config import ApiSettings
from app.api.main import create_app
from app.api.runtime import ApiRuntime
from app.api.security import SESSION_COOKIE
from app.auth import AuthRepository, AuthService
from app.database import (
    DatabaseAuthorizationError,
    TenderRepository,
)
from app.models.tender import TenderAnalysis
from app.organizations import (
    OrganizationRepository,
    OrganizationService,
    Role,
)
from app.tenancy import organization_owner_id


class OrganizationDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.path = (
            Path(self.temp.name)
            / "organization-data.db"
        )

        auth_repository = AuthRepository(self.path)
        auth_repository.initialize()

        organization_repository = OrganizationRepository(
            self.path
        )
        organization_repository.initialize()

        tender_repository = TenderRepository(
            self.path
        )
        tender_repository.initialize()

        self.auth = AuthService(
            auth_repository
        )
        self.org_repo = organization_repository
        self.organizations = OrganizationService(
            organization_repository
        )
        self.tenders = tender_repository

        self.owner = self.auth.register(
            "data-owner@example.com",
            "very secure password 123",
        )
        self.member = self.auth.register(
            "data-member@example.com",
            "very secure password 123",
        )
        self.viewer = self.auth.register(
            "data-viewer@example.com",
            "very secure password 123",
        )
        self.outsider = self.auth.register(
            "data-outsider@example.com",
            "very secure password 123",
        )

        self.organization = self.org_repo.create(
            "Shared Tender Data",
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

        runtime = ApiRuntime(
            auth_service=self.auth,
            organization_service=self.organizations,
            tender_repository=self.tenders,
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

        self.record = self.save(
            self.owner,
            self.organization.id,
            "a" * 64,
            "Shared tender",
        )

    def as_account(self, account):
        self.client.cookies.clear()

        token = self.auth.create_session(account)

        self.client.cookies.set(
            SESSION_COOKIE,
            token,
        )

    def base(self, suffix=""):
        return (
            f"/api/v1/organizations/"
            f"{self.organization.id}"
            f"{suffix}"
        )

    def save(
        self,
        account,
        organization_id,
        digest,
        title,
    ):
        return self.tenders.save_success_for_organization(
            account_id=account.id,
            organization_id=organization_id,
            pdf_sha256=digest,
            source_filename="shared.pdf",
            pages=2,
            characters=123,
            analysis=TenderAnalysis(
                title=title,
                tender_number="ORG-1",
                customer="Shared Customer",
                initial_price=1000,
                currency="RUB",
            ),
            scoring=None,
            analysis_truncated=False,
        )

    def test_history_is_shared_across_members(self):
        self.as_account(self.member)

        listed = self.client.get(
            self.base("/tenders")
        )

        self.assertEqual(
            listed.status_code,
            200,
            listed.text,
        )
        self.assertEqual(
            [item["id"] for item in listed.json()],
            [self.record.id],
        )

        detail = self.client.get(
            self.base(
                f"/tenders/{self.record.id}"
            )
        )

        self.assertEqual(
            detail.status_code,
            200,
            detail.text,
        )
        self.assertEqual(
            detail.json()["analysis"]["title"],
            "Shared tender",
        )

        self.assertNotIn(
            "owner_user_id",
            detail.json(),
        )

        self.as_account(self.viewer)

        viewer = self.client.get(
            self.base(
                f"/tenders/{self.record.id}"
            )
        )

        self.assertEqual(
            viewer.status_code,
            200,
        )

    def test_outsider_cannot_read_organization_history(self):
        self.as_account(self.outsider)

        listed = self.client.get(
            self.base("/tenders")
        )

        self.assertEqual(
            listed.status_code,
            403,
        )

        detail = self.client.get(
            self.base(
                f"/tenders/{self.record.id}"
            )
        )

        self.assertEqual(
            detail.status_code,
            403,
        )

    def test_cross_organization_tender_id_is_hidden(self):
        second = self.org_repo.create(
            "Other Tender Data",
            self.outsider.id,
        )

        foreign = self.save(
            self.outsider,
            second.id,
            "b" * 64,
            "Foreign tender",
        )

        self.as_account(self.owner)

        response = self.client.get(
            self.base(
                f"/tenders/{foreign.id}"
            )
        )

        self.assertEqual(
            response.status_code,
            404,
        )

    def test_member_can_persist_shared_organization_tender(self):
        record = self.save(
            self.member,
            self.organization.id,
            "e" * 64,
            "Member saved tender",
        )

        self.assertEqual(
            record.analysis.title,
            "Member saved tender",
        )

        self.as_account(self.owner)

        detail = self.client.get(
            self.base(
                f"/tenders/{record.id}"
            )
        )

        self.assertEqual(
            detail.status_code,
            200,
            detail.text,
        )
        self.assertEqual(
            detail.json()["analysis"]["title"],
            "Member saved tender",
        )

    def test_same_pdf_hash_is_isolated_between_organizations(self):
        digest = "f" * 64

        first = self.save(
            self.owner,
            self.organization.id,
            digest,
            "First organization copy",
        )

        second_organization = self.org_repo.create(
            "Second PDF Namespace",
            self.outsider.id,
        )

        second = self.save(
            self.outsider,
            second_organization.id,
            digest,
            "Second organization copy",
        )

        self.assertNotEqual(
            first.id,
            second.id,
        )
        self.assertEqual(
            first.pdf_sha256,
            second.pdf_sha256,
        )
        self.assertNotEqual(
            first.owner_user_id,
            second.owner_user_id,
        )

        found_first = self.tenders.find_by_hash_for_organization(
            self.owner.id,
            self.organization.id,
            digest,
        )

        found_second = self.tenders.find_by_hash_for_organization(
            self.outsider.id,
            second_organization.id,
            digest,
        )

        self.assertEqual(
            found_first.id,
            first.id,
        )
        self.assertEqual(
            found_second.id,
            second.id,
        )

    def test_viewer_cannot_persist_organization_tender(self):
        with self.assertRaises(
            DatabaseAuthorizationError
        ):
            self.save(
                self.viewer,
                self.organization.id,
                "c" * 64,
                "Viewer write",
            )

    def test_revoked_member_cannot_read_history(self):
        self.org_repo.remove_membership(
            self.organization.id,
            self.member.id,
        )

        self.as_account(self.member)

        response = self.client.get(
            self.base("/tenders")
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_api_key_is_not_organization_identity(self):
        self.client.cookies.clear()

        response = self.client.get(
            self.base("/tenders"),
            headers={
                "X-API-Key": "legacy-secret",
            },
        )

        self.assertEqual(
            response.status_code,
            401,
        )

    def test_legacy_api_key_cannot_guess_organization_owner(self):
        self.client.cookies.clear()

        response = self.client.get(
            "/api/v1/tenders",
            params={
                "owner_user_id":
                    organization_owner_id(
                        self.organization.id
                    ),
            },
            headers={
                "X-API-Key": "legacy-secret",
            },
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_legacy_owner_history_remains_separate(self):
        legacy = self.tenders.save_success(
            owner_user_id=self.owner.owner_user_id,
            chat_id=self.owner.owner_user_id,
            pdf_sha256="d" * 64,
            source_filename="legacy.pdf",
            pages=1,
            characters=10,
            analysis=TenderAnalysis(
                title="Legacy tender",
            ),
            scoring=None,
            analysis_truncated=False,
        )

        self.as_account(self.owner)

        organization = self.client.get(
            self.base("/tenders")
        )

        self.assertEqual(
            [item["id"] for item in organization.json()],
            [self.record.id],
        )

        legacy_response = self.client.get(
            "/api/v1/tenders",
            params={
                "owner_user_id":
                    self.owner.owner_user_id,
            },
        )

        self.assertEqual(
            legacy_response.status_code,
            200,
        )
        self.assertEqual(
            [item["id"] for item in legacy_response.json()],
            [legacy.id],
        )


if __name__ == "__main__":
    unittest.main()
