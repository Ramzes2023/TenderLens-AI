import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.config import ApiSettings
from app.api.main import create_app
from app.api.runtime import ApiRuntime
from app.auth import AuthRepository, AuthService


class AuthApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        repository = AuthRepository(Path(self.tmp.name) / "auth-api.db")
        repository.initialize()
        service = AuthService(repository)

        runtime = ApiRuntime(auth_service=service)
        settings = ApiSettings(
            host="127.0.0.1",
            port=8000,
            reload=False,
            api_key="legacy-api-secret",
        )
        self.client_context = TestClient(create_app(runtime=runtime, settings=settings))
        self.client = self.client_context.__enter__()
        self.addCleanup(self.client_context.__exit__, None, None, None)

    def register(self):
        return self.client.post(
            "/api/v1/auth/register",
            json={
                "email": "User@Example.COM",
                "password": "very secure password 123",
            },
        )

    def test_register_sets_http_only_session_and_me_works(self):
        response = self.register()
        self.assertEqual(response.status_code, 201)

        body = response.json()
        self.assertEqual(body["email"], "user@example.com")
        self.assertGreater(body["owner_user_id"], 0)
        self.assertNotIn("password", body)
        self.assertNotIn("token", body)

        cookie = response.headers.get("set-cookie", "")
        self.assertIn("tenderlens_session=", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=lax", cookie)

        me = self.client.get("/api/v1/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["id"], body["id"])
        self.assertEqual(me.headers.get("cache-control"), "no-store")

    def test_logout_invalidates_session(self):
        self.assertEqual(self.register().status_code, 201)
        self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 200)
        logout = self.client.post("/api/v1/auth/logout")
        self.assertEqual(logout.status_code, 204)
        self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 401)

    def test_login_after_logout(self):
        self.assertEqual(self.register().status_code, 201)
        self.assertEqual(self.client.post("/api/v1/auth/logout").status_code, 204)

        login = self.client.post(
            "/api/v1/auth/login",
            json={
                "email": "USER@example.com",
                "password": "very secure password 123",
            },
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json()["email"], "user@example.com")
        self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 200)

    def test_wrong_password_is_unauthorized(self):
        self.assertEqual(self.register().status_code, 201)
        self.client.post("/api/v1/auth/logout")

        response = self.client.post(
            "/api/v1/auth/login",
            json={
                "email": "user@example.com",
                "password": "definitely wrong password",
            },
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Invalid email or password.")

    def test_duplicate_registration_is_rejected(self):
        self.assertEqual(self.register().status_code, 201)
        self.client.post("/api/v1/auth/logout")

        duplicate = self.client.post(
            "/api/v1/auth/register",
            json={
                "email": "USER@example.com",
                "password": "another secure password 456",
            },
        )
        self.assertEqual(duplicate.status_code, 422)

    def test_short_registration_password_is_rejected(self):
        response = self.client.post(
            "/api/v1/auth/register",
            json={"email": "user@example.com", "password": "short"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("12", response.json()["detail"])

    def test_auth_routes_do_not_require_legacy_api_key(self):
        self.assertEqual(self.register().status_code, 201)
        self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 200)


if __name__ == "__main__":
    unittest.main()
