import unittest

from fastapi.testclient import TestClient

from app.api.config import ApiSettings
from app.api.main import create_app
from app.api.runtime import ApiRuntime


class InvitationPageHeaderTests(unittest.TestCase):
    def setUp(self):
        settings = ApiSettings(
            host="127.0.0.1",
            port=8000,
            reload=False,
            api_key=None,
        )

        self.context = TestClient(
            create_app(
                runtime=ApiRuntime(),
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

    def test_invitation_page_prevents_referrer_token_leakage(self):
        response = self.client.get(
            "/invite/sample-token"
        )

        self.assertEqual(
            response.status_code,
            200,
            response.text,
        )

        self.assertEqual(
            response.headers.get(
                "cache-control"
            ),
            "no-store",
        )

        self.assertEqual(
            response.headers.get(
                "referrer-policy"
            ),
            "no-referrer",
        )

    def test_login_with_invitation_return_prevents_referrer_leakage(self):
        response = self.client.get(
            "/login",
            params={
                "next":
                    "/invite/sample-token"
            },
        )

        self.assertEqual(
            response.status_code,
            200,
            response.text,
        )

        self.assertEqual(
            response.headers.get(
                "referrer-policy"
            ),
            "no-referrer",
        )

    def test_register_with_invitation_return_prevents_referrer_leakage(self):
        response = self.client.get(
            "/register",
            params={
                "next":
                    "/invite/sample-token"
            },
        )

        self.assertEqual(
            response.status_code,
            200,
            response.text,
        )

        self.assertEqual(
            response.headers.get(
                "referrer-policy"
            ),
            "no-referrer",
        )


if __name__ == "__main__":
    unittest.main()
