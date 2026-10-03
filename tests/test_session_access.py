import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.config import ApiSettings
from app.api.main import create_app
from app.api.runtime import ApiRuntime
from app.auth import AuthRepository, AuthService
from app.companies import CompanyRepository, CompanyService
from app.database import TenderRepository
from app.scoring.models import CompanyProfile


class SessionScopedAccessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        db_path = Path(self.tmp.name) / "session-access.db"

        tender_repository = TenderRepository(db_path)
        tender_repository.initialize()

        company_repository = CompanyRepository(db_path)
        company_repository.initialize()
        fallback = CompanyProfile(
            profile_version="1",
            company_name="Fallback",
            product_keywords=["fallback"],
        )
        company_service = CompanyService(company_repository, fallback_profile=fallback)

        auth_repository = AuthRepository(db_path)
        auth_repository.initialize()
        auth_service = AuthService(auth_repository)
        self.account = auth_service.register(
            "owner@example.com",
            "very secure password 123",
        )
        self.token = auth_service.create_session(self.account)

        company_service.create(
            self.account.owner_user_id,
            "Own company",
            CompanyProfile(
                profile_version="1",
                company_name="Own company",
                product_keywords=["aluminium"],
            ),
        )
        company_service.create(
            99,
            "Other company",
            CompanyProfile(
                profile_version="1",
                company_name="Other company",
                product_keywords=["secret"],
            ),
        )

        runtime = ApiRuntime(
            company_profile=fallback,
            company_service=company_service,
            tender_repository=tender_repository,
            auth_service=auth_service,
        )
        settings = ApiSettings(
            host="127.0.0.1",
            port=8000,
            reload=False,
            api_key="legacy-api-secret",
        )
        self.client_context = TestClient(create_app(runtime=runtime, settings=settings))
        self.client = self.client_context.__enter__()
        self.addCleanup(self.client_context.__exit__, None, None, None)

    def _session(self):
        self.client.cookies.set("tenderlens_session", self.token)

    def test_session_can_use_protected_api_without_api_key(self):
        self._session()
        response = self.client.get(
            "/api/v1/companies",
            params={"owner_user_id": self.account.owner_user_id},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["name"] for item in response.json()], ["Own company"])

    def test_session_cannot_read_another_owner(self):
        self._session()
        response = self.client.get("/api/v1/companies", params={"owner_user_id": 99})
        self.assertEqual(response.status_code, 403)

    def test_session_cannot_create_for_another_owner(self):
        self._session()
        response = self.client.post(
            "/api/v1/companies",
            json={
                "owner_user_id": 99,
                "name": "Forbidden company",
                "profile": {
                    "profile_version": "1",
                    "company_name": "Forbidden company",
                    "product_keywords": ["forbidden"],
                },
                "make_active": True,
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_missing_session_and_missing_api_key_is_unauthorized(self):
        response = self.client.get(
            "/api/v1/companies",
            params={"owner_user_id": self.account.owner_user_id},
        )
        self.assertEqual(response.status_code, 401)

    def test_legacy_api_key_access_is_preserved(self):
        response = self.client.get(
            "/api/v1/companies",
            params={"owner_user_id": 99},
            headers={"X-API-Key": "legacy-api-secret"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["name"] for item in response.json()], ["Other company"])


if __name__ == "__main__":
    unittest.main()
