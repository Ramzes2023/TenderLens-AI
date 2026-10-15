import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

from app.api.config import ApiSettings
from app.api.main import create_app
from app.api.runtime import ApiRuntime
from app.auth import AuthRepository, AuthService


class RecordingEmailSender:
    public_base_url = "http://testserver"

    def __init__(self):
        self.messages = []

    def send_verification(
        self,
        *,
        recipient,
        verification_url,
        expires_at,
    ):
        self.messages.append(
            {
                "recipient": recipient,
                "verification_url":
                    verification_url,
                "expires_at":
                    expires_at,
            }
        )


class EmailVerificationApiTests(
    unittest.TestCase
):
    def setUp(self):
        self.tmp = (
            tempfile.TemporaryDirectory()
        )
        self.addCleanup(
            self.tmp.cleanup
        )

        self.repository = AuthRepository(
            Path(self.tmp.name)
            / "verify-api.db"
        )
        self.repository.initialize()

        self.service = AuthService(
            self.repository
        )

        self.sender = (
            RecordingEmailSender()
        )

        runtime = ApiRuntime(
            auth_service=self.service,
            email_sender=self.sender,
        )

        settings = ApiSettings(
            host="127.0.0.1",
            port=8000,
            reload=False,
            api_key="legacy",
        )

        self.ctx = TestClient(
            create_app(
                runtime=runtime,
                settings=settings,
            ),
            follow_redirects=False,
        )

        self.client = (
            self.ctx.__enter__()
        )

        self.addCleanup(
            self.ctx.__exit__,
            None,
            None,
            None,
        )

    def register(self):
        return self.client.post(
            "/api/v1/auth/register",
            json={
                "email":
                    "User@Example.COM",
                "password":
                    "very secure password 123",
            },
        )

    def latest_token(self):
        url = self.sender.messages[
            -1
        ]["verification_url"]

        values = parse_qs(
            urlsplit(url).query
        )

        return values["token"][0]

    def verify_latest(self):
        return self.client.post(
            "/api/v1/auth/verify-email",
            json={
                "token":
                    self.latest_token()
            },
        )

    def test_registration_requires_verification_and_does_not_create_session(self):
        response = self.register()

        self.assertEqual(
            response.status_code,
            201,
        )

        body = response.json()

        self.assertEqual(
            body["email"],
            "user@example.com",
        )

        self.assertTrue(
            body["verification_required"]
        )

        self.assertTrue(
            body["verification_sent"]
        )

        self.assertEqual(
            len(self.sender.messages),
            1,
        )

        self.assertNotIn(
            "token",
            body,
        )

        self.assertNotIn(
            "tenderlens_session=",
            response.headers.get(
                "set-cookie",
                "",
            ),
        )

        self.assertEqual(
            self.client.get(
                "/api/v1/auth/me"
            ).status_code,
            401,
        )

    def test_verification_creates_authenticated_session(self):
        self.assertEqual(
            self.register().status_code,
            201,
        )

        verified = (
            self.verify_latest()
        )

        self.assertEqual(
            verified.status_code,
            200,
        )

        self.assertTrue(
            verified.json()[
                "email_verified"
            ]
        )

        self.assertIn(
            "tenderlens_session=",
            verified.headers.get(
                "set-cookie",
                "",
            ),
        )

        me = self.client.get(
            "/api/v1/auth/me"
        )

        self.assertEqual(
            me.status_code,
            200,
        )

        self.assertTrue(
            me.json()[
                "email_verified"
            ]
        )

    def test_unverified_account_cannot_login(self):
        self.assertEqual(
            self.register().status_code,
            201,
        )

        login = self.client.post(
            "/api/v1/auth/login",
            json={
                "email":
                    "user@example.com",
                "password":
                    "very secure password 123",
            },
        )

        self.assertEqual(
            login.status_code,
            403,
        )

        self.assertEqual(
            login.json()["detail"],
            "Email verification required.",
        )

        self.assertNotIn(
            "tenderlens_session=",
            login.headers.get(
                "set-cookie",
                "",
            ),
        )

    def test_verified_account_can_login_after_logout(self):
        self.register()
        self.verify_latest()

        self.assertEqual(
            self.client.post(
                "/api/v1/auth/logout"
            ).status_code,
            204,
        )

        login = self.client.post(
            "/api/v1/auth/login",
            json={
                "email":
                    "user@example.com",
                "password":
                    "very secure password 123",
            },
        )

        self.assertEqual(
            login.status_code,
            200,
        )

    def test_verification_token_is_one_time(self):
        self.register()

        token = self.latest_token()

        first = self.client.post(
            "/api/v1/auth/verify-email",
            json={
                "token": token
            },
        )

        self.assertEqual(
            first.status_code,
            200,
        )

        self.client.post(
            "/api/v1/auth/logout"
        )

        replay = self.client.post(
            "/api/v1/auth/verify-email",
            json={
                "token": token
            },
        )

        self.assertEqual(
            replay.status_code,
            422,
        )

    def test_resend_is_enumeration_safe(self):
        self.register()

        initial_count = len(
            self.sender.messages
        )

        known = self.client.post(
            "/api/v1/auth/resend-verification",
            json={
                "email":
                    "user@example.com"
            },
        )

        unknown = self.client.post(
            "/api/v1/auth/resend-verification",
            json={
                "email":
                    "unknown@example.com"
            },
        )

        self.assertEqual(
            known.status_code,
            202,
        )

        self.assertEqual(
            unknown.status_code,
            202,
        )

        self.assertEqual(
            known.json(),
            unknown.json(),
        )

        # Immediate known-account resend is
        # suppressed by the cooldown.
        self.assertEqual(
            len(self.sender.messages),
            initial_count,
        )

    def test_cross_origin_verification_write_is_blocked(self):
        self.register()

        blocked = self.client.post(
            "/api/v1/auth/verify-email",
            headers={
                "Origin":
                    "https://evil.example"
            },
            json={
                "token":
                    self.latest_token()
            },
        )

        self.assertEqual(
            blocked.status_code,
            403,
        )

    def test_registration_fails_closed_when_delivery_not_configured(self):
        other_repository = (
            AuthRepository(
                Path(self.tmp.name)
                / "no-mail.db"
            )
        )
        other_repository.initialize()

        runtime = ApiRuntime(
            auth_service=AuthService(
                other_repository
            ),
            email_sender=None,
        )

        settings = ApiSettings(
            host="127.0.0.1",
            port=8000,
            reload=False,
            api_key=None,
        )

        with TestClient(
            create_app(
                runtime=runtime,
                settings=settings,
            )
        ) as client:
            response = client.post(
                "/api/v1/auth/register",
                json={
                    "email":
                        "blocked@example.com",
                    "password":
                        "very secure password 123",
                },
            )

        self.assertEqual(
            response.status_code,
            503,
        )

        self.assertIsNone(
            other_repository
            .find_account_by_email(
                "blocked@example.com"
            )
        )

    def test_verification_page_is_no_referrer(self):
        page = self.client.get(
            "/verify-email",
            params={
                "email":
                    "user@example.com"
            },
        )

        self.assertEqual(
            page.status_code,
            200,
        )

        self.assertEqual(
            page.headers.get(
                "referrer-policy"
            ),
            "no-referrer",
        )

        self.assertIn(
            "Verify your email",
            page.text,
        )


if __name__ == "__main__":
    unittest.main()
