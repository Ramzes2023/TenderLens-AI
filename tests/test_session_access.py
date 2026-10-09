import tempfile
import unittest
from dataclasses import replace
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

    def test_legacy_api_key_cannot_impersonate_personal_owner(self):
        response = self.client.get(
            "/api/v1/companies",
            params={"owner_user_id": 99},
            headers={"X-API-Key": "legacy-api-secret"},
        )
        self.assertEqual(response.status_code, 403)

    def _owner_requests(self, owner):
        profile = {"profile_version": "1", "company_name": "Blocked", "product_keywords": ["blocked"]}
        return [
            ("GET", "/api/v1/companies", {"params": {"owner_user_id": owner}}),
            ("GET", "/api/v1/tenders", {"params": {"owner_user_id": owner}}),
            ("GET", "/api/v1/tenders/1", {"params": {"owner_user_id": owner}}),
            ("GET", "/api/v1/monitoring/status", {"params": {"owner_user_id": owner}}),
            ("POST", "/api/v1/companies", {"json": {"owner_user_id": owner, "name": "Blocked", "profile": profile}}),
            ("POST", "/api/v1/companies/1/activate", {"json": {"owner_user_id": owner}}),
            ("POST", "/api/v1/scoring/evaluate", {"params": {"owner_user_id": owner}, "json": {"title": "Synthetic tender"}}),
            ("POST", "/api/v1/rag/ask", {"json": {"owner_user_id": owner, "pdf_sha256": "a" * 64, "question": "Synthetic question"}}),
            ("POST", "/api/v1/monitoring/scan", {"json": {"owner_user_id": owner}}),
            ("POST", "/api/v1/analysis/pdf", {"data": {"owner_user_id": str(owner)}, "files": {"file": ("synthetic.pdf", b"%PDF-synthetic", "application/pdf")}}),
        ]

    def test_anonymous_reads_and_writes_fail_closed_with_absent_or_configured_key(self):
        original = self.client.app.state.api_settings
        for configured in (None, "", "   ", "legacy-api-secret"):
            self.client.app.state.api_settings = replace(original, api_key=configured)
            for cookie in (None, "invalid-session"):
                self.client.cookies.clear()
                if cookie:
                    self.client.cookies.set("tenderlens_session", cookie)
                rejected_headers = [{}, {"X-API-Key": ""}, {"X-API-Key": "wrong"}]
                if configured != "legacy-api-secret":
                    rejected_headers.append({"X-API-Key": "legacy-api-secret"})
                for headers in rejected_headers:
                    for method, url, kwargs in self._owner_requests(99) + [
                        ("POST", "/api/v1/scoring/evaluate", {"json": {"title": "Synthetic tender"}}),
                    ]:
                        with self.subTest(configured=configured, cookie=cookie, headers=headers, url=url):
                            response = self.client.request(method, url, headers=headers, **kwargs)
                            self.assertEqual(response.status_code, 401, response.text)
            self.assertEqual(self.client.get("/health").status_code, 200)
        service = self.client.app.state.runtime.company_service
        self.assertEqual([c.name for c in service.list(99)], ["Other company"])
        self.assertEqual([c.name for c in service.list(self.account.owner_user_id)], ["Own company"])

    def test_integration_key_denies_all_personal_owner_reads_and_writes(self):
        for owner in (self.account.owner_user_id, 99):
            for method, url, kwargs in self._owner_requests(owner):
                with self.subTest(owner=owner, url=url):
                    response = self.client.request(method, url, headers={"X-API-Key": "legacy-api-secret"}, **kwargs)
                    self.assertEqual(response.status_code, 403, response.text)
        service = self.client.app.state.runtime.company_service
        self.assertEqual([c.name for c in service.list(99)], ["Other company"])

    def test_integration_key_preserves_ownerless_scoring_only_when_configured(self):
        original = self.client.app.state.api_settings
        for configured, expected in (("legacy-api-secret", 200), (None, 401), ("", 401), ("   ", 401)):
            self.client.app.state.api_settings = replace(original, api_key=configured)
            response = self.client.post("/api/v1/scoring/evaluate", headers={"X-API-Key": "legacy-api-secret"}, json={"title": "Synthetic tender"})
            self.assertEqual(response.status_code, expected, response.text)

    def test_sessions_work_without_configured_key_and_cannot_be_overridden_by_key(self):
        original = self.client.app.state.api_settings
        self._session()
        for configured in (None, "legacy-api-secret"):
            self.client.app.state.api_settings = replace(original, api_key=configured)
            for key in ("wrong", "legacy-api-secret"):
                headers = {"X-API-Key": key}
                own = self.client.get("/api/v1/companies", params={"owner_user_id": self.account.owner_user_id}, headers=headers)
                self.assertEqual(own.status_code, 200)
                for method, url, kwargs in self._owner_requests(99):
                    with self.subTest(configured=configured, key=key, url=url):
                        response = self.client.request(method, url, headers=headers, **kwargs)
                        self.assertEqual(response.status_code, 403, response.text)
            name = f"Session company {configured is not None}"
            created = self.client.post("/api/v1/companies", json={"owner_user_id": self.account.owner_user_id, "name": name, "profile": {"profile_version": "1", "company_name": name, "product_keywords": ["synthetic"]}, "make_active": True})
            self.assertEqual(created.status_code, 200, created.text)
            score = self.client.post("/api/v1/scoring/evaluate", json={"title": "Synthetic tender"})
            self.assertEqual(score.status_code, 200, score.text)

    def test_owner_resolution_authenticates_even_without_route_dependency(self):
        from fastapi import Request
        from app.api.security import resolve_owner

        @self.client.app.get("/test-owner-resolution")
        async def owner_resolution(request: Request, owner: int | None = None):
            return {"owner": await resolve_owner(request, owner)}

        self.assertEqual(self.client.get("/test-owner-resolution").status_code, 401)
        self.assertEqual(self.client.get("/test-owner-resolution", params={"owner": 99}).status_code, 401)
        headers = {"X-API-Key": "legacy-api-secret"}
        self.assertEqual(self.client.get("/test-owner-resolution", headers=headers).json(), {"owner": None})
        self.assertEqual(self.client.get("/test-owner-resolution", params={"owner": 99}, headers=headers).status_code, 403)
        self._session()
        self.assertEqual(self.client.get("/test-owner-resolution").json(), {"owner": self.account.owner_user_id})


if __name__ == "__main__":
    unittest.main()
