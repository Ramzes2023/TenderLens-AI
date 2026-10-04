import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.config import ApiSettings
from app.api.main import create_app
from app.api.runtime import ApiRuntime
from app.auth import AuthRepository, AuthService
from app.companies import CompanyRepository, CompanyService
from app.scoring.models import CompanyProfile


class FakeMonitoring:
    def __init__(self):
        self.settings = SimpleNamespace(
            enabled=True,
            interval_seconds=600,
            eis_rss_urls=("fallback-feed",),
            profile_feeds_enabled=True,
            profile_feed_limit=5,
        )
        self.scan_calls = 0

    async def subscription(self, owner_user_id):
        return SimpleNamespace(enabled=True)

    async def scan_new(self, owner_user_id):
        self.scan_calls += 1
        return []


class NoCompanySaasGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        db_path = Path(self.tmp.name) / "no-company.db"

        fallback = CompanyProfile(
            profile_version="1",
            company_name="VALYQON AI Demo Supplier",
            product_keywords=["demo"],
            search_keywords=["demo"],
        )

        company_repository = CompanyRepository(db_path)
        company_repository.initialize()
        company_service = CompanyService(company_repository, fallback_profile=fallback)

        auth_repository = AuthRepository(db_path)
        auth_repository.initialize()
        auth_service = AuthService(auth_repository)
        account = auth_service.register("user@example.com", "very secure password 123")
        token = auth_service.create_session(account)

        self.account = account
        self.monitoring = FakeMonitoring()
        runtime = ApiRuntime(
            company_profile=fallback,
            company_service=company_service,
            auth_service=auth_service,
            monitoring_service=self.monitoring,
        )
        settings = ApiSettings(host="127.0.0.1", port=8000, reload=False, api_key="legacy")
        self.client_context = TestClient(create_app(runtime=runtime, settings=settings))
        self.client = self.client_context.__enter__()
        self.addCleanup(self.client_context.__exit__, None, None, None)
        self.client.cookies.set("tenderlens_session", token)

    def test_status_does_not_expose_fallback_company(self):
        response = self.client.get(
            "/api/v1/monitoring/status",
            params={"owner_user_id": self.account.owner_user_id},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIsNone(body["active_company"])
        self.assertEqual(body["feed_mode"], "no-company")
        self.assertEqual(body["rss_feeds"], 0)
        self.assertFalse(body["subscription_enabled"])

    def test_scan_is_blocked_before_source_fetch(self):
        response = self.client.post(
            "/api/v1/monitoring/scan",
            json={"owner_user_id": self.account.owner_user_id},
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("Create a company profile", response.json()["detail"])
        self.assertEqual(self.monitoring.scan_calls, 0)

    def test_scoring_is_blocked_without_active_company(self):
        response = self.client.post(
            "/api/v1/scoring/evaluate",
            params={"owner_user_id": self.account.owner_user_id},
            json={"title": "Demo tender"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("Create a company profile", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
