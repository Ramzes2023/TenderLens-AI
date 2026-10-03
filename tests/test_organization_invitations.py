import hashlib
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from threading import Barrier
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.config import ApiSettings
from app.api.main import create_app
from app.api.runtime import ApiRuntime
from app.api.security import SESSION_COOKIE
from app.auth import AuthRepository, AuthService
from app.organizations import (
    OrganizationError,
    OrganizationRepository,
    OrganizationService,
    Role,
)


class OrganizationInvitationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.path = (
            Path(self.temp.name)
            / "organization-invitations.db"
        )

        auth_repository = AuthRepository(
            self.path
        )
        auth_repository.initialize()

        organization_repository = (
            OrganizationRepository(
                self.path
            )
        )
        organization_repository.initialize()

        self.auth = AuthService(
            auth_repository
        )

        self.org_repo = (
            organization_repository
        )

        self.organizations = (
            OrganizationService(
                organization_repository
            )
        )

        self.owner = self.auth.register(
            "invite-owner@example.com",
            "very secure password 123",
        )

        self.invitee = self.auth.register(
            "invitee@example.com",
            "very secure password 123",
        )

        self.other = self.auth.register(
            "other@example.com",
            "very secure password 123",
        )

        self.organization = (
            self.org_repo.create(
                "Invitation Workspace",
                self.owner.id,
            )
        )

        runtime = ApiRuntime(
            auth_service=self.auth,
            organization_service=(
                self.organizations
            ),
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

        self.client = (
            self.context.__enter__()
        )

        self.addCleanup(
            self.context.__exit__,
            None,
            None,
            None,
        )

    def as_account(self, account):
        self.client.cookies.clear()

        token = self.auth.create_session(
            account
        )

        self.client.cookies.set(
            SESSION_COOKIE,
            token,
        )

    def invitation_url(self):
        return (
            f"/api/v1/organizations/"
            f"{self.organization.id}"
            f"/invitations"
        )

    def create_invite(
        self,
        email="invitee@example.com",
        role="member",
    ):
        self.as_account(self.owner)

        response = self.client.post(
            self.invitation_url(),
            json={
                "email": email,
                "role": role,
            },
        )

        self.assertEqual(
            response.status_code,
            201,
            response.text,
        )

        return response.json()

    def test_create_preview_accept_and_token_is_hashed_at_rest(self):
        created = self.create_invite()

        token = created["token"]

        self.assertTrue(token)
        self.assertEqual(
            created["role"],
            "member",
        )

        with closing(
            sqlite3.connect(
                self.path
            )
        ) as conn:
            row = conn.execute(
                """SELECT token_hash
                   FROM organization_invitations
                   WHERE id=?""",
                (created["id"],),
            ).fetchone()

        self.assertIsNotNone(row)

        self.assertNotEqual(
            row[0],
            token,
        )

        self.assertEqual(
            row[0],
            hashlib.sha256(
                token.encode("utf-8")
            ).hexdigest(),
        )

        self.client.cookies.clear()

        preview = self.client.get(
            f"/api/v1/organizations/invitations/{token}"
        )

        self.assertEqual(
            preview.status_code,
            200,
            preview.text,
        )

        self.assertEqual(
            preview.json()[
                "organization_name"
            ],
            "Invitation Workspace",
        )

        self.assertNotEqual(
            preview.json()["email_hint"],
            "invitee@example.com",
        )

        self.as_account(
            self.invitee
        )

        accepted = self.client.post(
            f"/api/v1/organizations/invitations/{token}/accept"
        )

        self.assertEqual(
            accepted.status_code,
            200,
            accepted.text,
        )

        self.assertEqual(
            accepted.json()["role"],
            "member",
        )

        organizations = self.client.get(
            "/api/v1/organizations"
        )

        ids = {
            item["id"]
            for item in organizations.json()
        }

        self.assertIn(
            self.organization.id,
            ids,
        )

        replay = self.client.post(
            f"/api/v1/organizations/invitations/{token}/accept"
        )

        self.assertEqual(
            replay.status_code,
            410,
        )

    def test_invite_can_exist_before_account_registration(self):
        created = self.create_invite(
            email="future-user@example.com",
            role="viewer",
        )

        token = created["token"]

        future = self.auth.register(
            "future-user@example.com",
            "very secure password 123",
        )

        self.as_account(future)

        accepted = self.client.post(
            f"/api/v1/organizations/invitations/{token}/accept"
        )

        self.assertEqual(
            accepted.status_code,
            200,
            accepted.text,
        )

        self.assertEqual(
            accepted.json()["role"],
            "viewer",
        )

    def test_wrong_email_cannot_accept_invitation(self):
        created = self.create_invite()

        self.as_account(
            self.other
        )

        response = self.client.post(
            f"/api/v1/organizations/invitations/"
            f"{created['token']}/accept"
        )

        self.assertEqual(
            response.status_code,
            403,
        )

        membership = (
            self.org_repo.get_membership(
                self.organization.id,
                self.other.id,
            )
        )

        self.assertIsNone(
            membership
        )

    def test_manager_list_does_not_expose_token(self):
        created = self.create_invite()

        self.as_account(
            self.owner
        )

        response = self.client.get(
            self.invitation_url()
        )

        self.assertEqual(
            response.status_code,
            200,
            response.text,
        )

        self.assertEqual(
            len(response.json()),
            1,
        )

        self.assertNotIn(
            "token",
            response.json()[0],
        )

        self.assertNotIn(
            created["token"],
            response.text,
        )

    def test_duplicate_invite_and_existing_member_are_blocked(self):
        self.create_invite()

        self.as_account(
            self.owner
        )

        duplicate = self.client.post(
            self.invitation_url(),
            json={
                "email":
                    "invitee@example.com",
                "role": "member",
            },
        )

        self.assertEqual(
            duplicate.status_code,
            409,
        )

        self.org_repo.add_membership(
            self.organization.id,
            self.other.id,
            Role.VIEWER,
        )

        existing = self.client.post(
            self.invitation_url(),
            json={
                "email":
                    "other@example.com",
                "role": "member",
            },
        )

        self.assertEqual(
            existing.status_code,
            409,
        )

    def test_owner_role_cannot_be_granted_by_invitation(self):
        self.as_account(
            self.owner
        )

        response = self.client.post(
            self.invitation_url(),
            json={
                "email":
                    "invitee@example.com",
                "role": "owner",
            },
        )

        self.assertEqual(
            response.status_code,
            422,
        )

    def test_revoke_blocks_acceptance(self):
        created = self.create_invite()

        self.as_account(
            self.owner
        )

        revoked = self.client.delete(
            f"{self.invitation_url()}/"
            f"{created['id']}"
        )

        self.assertEqual(
            revoked.status_code,
            204,
            revoked.text,
        )

        self.as_account(
            self.invitee
        )

        denied = self.client.post(
            f"/api/v1/organizations/invitations/"
            f"{created['token']}/accept"
        )

        self.assertEqual(
            denied.status_code,
            410,
        )

    def test_non_manager_cannot_create_or_list_invitations(self):
        self.org_repo.add_membership(
            self.organization.id,
            self.invitee.id,
            Role.MEMBER,
        )

        self.as_account(
            self.invitee
        )

        create = self.client.post(
            self.invitation_url(),
            json={
                "email":
                    "other@example.com",
                "role": "viewer",
            },
        )

        self.assertEqual(
            create.status_code,
            403,
        )

        listed = self.client.get(
            self.invitation_url()
        )

        self.assertEqual(
            listed.status_code,
            403,
        )

    def test_concurrent_accept_consumes_token_exactly_once(self):
        created = self.create_invite()

        token = created["token"]
        barrier = Barrier(2)

        def accept():
            barrier.wait()

            try:
                membership = (
                    self.organizations.accept_invitation(
                        self.invitee,
                        token,
                    )
                )

                return (
                    "accepted",
                    membership.role.value,
                )

            except OrganizationError as error:
                return (
                    "rejected",
                    str(error),
                )

        with ThreadPoolExecutor(
            max_workers=2
        ) as pool:
            futures = [
                pool.submit(accept)
                for _ in range(2)
            ]

            results = [
                future.result(timeout=15)
                for future in futures
            ]

        accepted = [
            item
            for item in results
            if item[0] == "accepted"
        ]

        rejected = [
            item
            for item in results
            if item[0] == "rejected"
        ]

        self.assertEqual(
            len(accepted),
            1,
            results,
        )

        self.assertEqual(
            accepted[0][1],
            "member",
        )

        self.assertEqual(
            len(rejected),
            1,
            results,
        )

        self.assertIn(
            "invalid or expired",
            rejected[0][1].lower(),
        )

        membership = (
            self.org_repo.get_membership(
                self.organization.id,
                self.invitee.id,
            )
        )

        self.assertIsNotNone(
            membership
        )

        self.assertEqual(
            membership.role,
            Role.MEMBER,
        )

        with closing(
            sqlite3.connect(
                self.path
            )
        ) as conn:
            membership_count = conn.execute(
                """SELECT COUNT(*)
                   FROM organization_members
                   WHERE organization_id=?
                     AND account_id=?""",
                (
                    self.organization.id,
                    self.invitee.id,
                ),
            ).fetchone()[0]

            invitation = conn.execute(
                """SELECT accepted_at
                   FROM organization_invitations
                   WHERE id=?""",
                (
                    created["id"],
                ),
            ).fetchone()

        self.assertEqual(
            membership_count,
            1,
        )

        self.assertIsNotNone(
            invitation
        )

        self.assertIsNotNone(
            invitation[0],
        )

    def test_api_key_is_not_invitation_accept_identity(self):
        created = self.create_invite()

        self.client.cookies.clear()

        response = self.client.post(
            f"/api/v1/organizations/invitations/"
            f"{created['token']}/accept",
            headers={
                "X-API-Key":
                    "legacy-secret",
            },
        )

        self.assertEqual(
            response.status_code,
            401,
        )

    def test_cross_origin_invitation_writes_are_rejected(self):
        self.as_account(
            self.owner
        )

        headers = {
            "Origin":
                "https://evil.example",
            "Sec-Fetch-Site":
                "cross-site",
        }

        create = self.client.post(
            self.invitation_url(),
            json={
                "email":
                    "other@example.com",
                "role": "viewer",
            },
            headers=headers,
        )

        self.assertEqual(
            create.status_code,
            403,
        )

        created = self.create_invite()

        self.as_account(
            self.invitee
        )

        accept = self.client.post(
            f"/api/v1/organizations/invitations/"
            f"{created['token']}/accept",
            headers=headers,
        )

        self.assertEqual(
            accept.status_code,
            403,
        )


if __name__ == "__main__":
    unittest.main()
