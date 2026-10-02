import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.config import ApiSettings
from app.api.main import create_app
from app.api.runtime import ApiRuntime
from app.companies import CompanyRepository, CompanyService
from app.database.repository import TenderRepository
from app.models.tender import TenderAnalysis
from app.scoring.models import CompanyProfile
from app.sources.models import TenderNotice


class FakeProvider:
    async def generate(self, prompt: str, *, max_tokens: int = 512):
        raise AssertionError("Provider should not be called in this test")


class FakeRag:
    async def answer(self, owner_user_id, pdf_sha256, question, provider):
        source = SimpleNamespace(chunk_index=0, page_number=1, text="Срок 30 дней", score=0.91)
        return SimpleNamespace(answer="Срок поставки 30 дней [стр. 1].", sources=(source,))


class FakeMonitoring:
    def __init__(self):
        self.settings = SimpleNamespace(enabled=True, interval_seconds=600, eis_rss_urls=("a", "b"))

    async def subscription(self, owner_user_id):
        return SimpleNamespace(enabled=True)

    async def scan_new(self, owner_user_id):
        notice = TenderNotice(
            source="eis", external_id="n1", title="Поставка оборудования",
            url="https://zakupki.gov.ru/example", tender_number="123",
            initial_price=1000, currency="RUB", region="Москва",
        )
        return [SimpleNamespace(notice=notice, reasons=("Направление совпадает",))]


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        db_path = Path(self.tmp.name) / "api.db"
        repo = TenderRepository(db_path)
        repo.initialize()
        company_repo = CompanyRepository(db_path)
        company_repo.initialize()
        self.record = repo.save_success(
            owner_user_id=42,
            chat_id=42,
            pdf_sha256="a" * 64,
            source_filename="tender.pdf",
            pages=2,
            characters=123,
            analysis=TenderAnalysis(
                title="Поставка электрооборудования",
                tender_number="T-1",
                customer="Заказчик",
                initial_price=1000,
                currency="RUB",
                delivery_region="Москва",
                procurement_object="электротехническое оборудование",
            ),
            scoring=None,
            analysis_truncated=False,
        )
        profile = CompanyProfile(
            profile_version="1",
            company_name="Demo",
            product_keywords=["электротехническое оборудование"],
            allowed_regions=["Москва"],
            max_contract_value=5000,
        )
        company_service = CompanyService(company_repo, fallback_profile=profile)
        runtime = ApiRuntime(
            provider=FakeProvider(),
            company_profile=profile,
            company_service=company_service,
            tender_repository=repo,
            rag_service=FakeRag(),
            monitoring_service=FakeMonitoring(),
        )
        settings = ApiSettings(host="127.0.0.1", port=8000, reload=False, api_key=None)
        self.client_context = TestClient(create_app(runtime=runtime, settings=settings))
        self.client = self.client_context.__enter__()
        self.addCleanup(self.client_context.__exit__, None, None, None)

    def test_health_and_openapi(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["version"], "1.2.0")
        self.assertNotIn("phase", body)
        self.assertEqual(body["components"]["database"], "ready")
        self.assertEqual(self.client.get("/openapi.json").status_code, 200)

    def test_history_is_owner_scoped(self):
        response = self.client.get("/api/v1/tenders", params={"owner_user_id": 42})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["id"], self.record.id)
        other = self.client.get("/api/v1/tenders", params={"owner_user_id": 99})
        self.assertEqual(other.json(), [])

    def test_detail_and_not_found(self):
        response = self.client.get(
            f"/api/v1/tenders/{self.record.id}", params={"owner_user_id": 42}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["analysis"]["title"], "Поставка электрооборудования")
        hidden = self.client.get(
            f"/api/v1/tenders/{self.record.id}", params={"owner_user_id": 99}
        )
        self.assertEqual(hidden.status_code, 404)

    def test_scoring_endpoint(self):
        payload = TenderAnalysis(
            title="Поставка электрооборудования",
            initial_price=1000,
            currency="RUB",
            delivery_region="Москва",
            procurement_object="электротехническое оборудование",
        ).model_dump(mode="json")
        response = self.client.post("/api/v1/scoring/evaluate", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["fit_score"], 100.0)

    def test_rag_endpoint(self):
        response = self.client.post(
            "/api/v1/rag/ask",
            json={"owner_user_id": 42, "pdf_sha256": "a" * 64, "question": "Какой срок?"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("30 дней", response.json()["answer"])
        self.assertEqual(response.json()["sources"][0]["page_number"], 1)

    def test_pdf_duplicate_reuses_saved_analysis(self):
        import hashlib

        data = b"%PDF-existing-test"
        digest = hashlib.sha256(data).hexdigest()
        self.client.app.state.runtime.tender_repository.save_success(
            owner_user_id=42, chat_id=42, pdf_sha256=digest, source_filename="existing.pdf",
            pages=1, characters=10, analysis=TenderAnalysis(title="Already analyzed"),
            scoring=None, analysis_truncated=False,
        )
        response = self.client.post(
            "/api/v1/analysis/pdf",
            data={"owner_user_id": "42"},
            files={"file": ("same.pdf", data, "application/pdf")},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["duplicate"])
        self.assertEqual(response.json()["analysis"]["title"], "Already analyzed")

    def test_monitoring_endpoints(self):
        response = self.client.get("/api/v1/monitoring/status", params={"owner_user_id": 42})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["rss_feeds"], 2)
        self.assertTrue(response.json()["subscription_enabled"])
        scan = self.client.post("/api/v1/monitoring/scan", json={"owner_user_id": 42})
        self.assertEqual(scan.status_code, 200)
        self.assertEqual(scan.json()[0]["external_id"], "n1")

    def test_company_workspace_endpoints_and_owner_specific_scoring(self):
        profile_payload = {
            "profile_version": "workspace-1",
            "company_name": "AluTrade",
            "business_mode": "sell",
            "product_keywords": ["алюминий"],
            "search_keywords": ["алюминий", "алюминиевый профиль"],
            "accepted_currencies": ["RUB"],
            "max_contract_value": 50000000
        }
        created = self.client.post(
            "/api/v1/companies",
            json={"owner_user_id": 42, "name": "AluTrade", "profile": profile_payload, "make_active": True},
        )
        self.assertEqual(created.status_code, 200)
        company_id = created.json()["id"]
        self.assertTrue(created.json()["is_active"])
        listed = self.client.get("/api/v1/companies", params={"owner_user_id": 42})
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()[0]["id"], company_id)

        analysis = TenderAnalysis(
            title="Поставка алюминия", procurement_object="алюминий",
            initial_price=1000000, currency="RUB"
        ).model_dump(mode="json")
        score = self.client.post(
            "/api/v1/scoring/evaluate", params={"owner_user_id": 42}, json=analysis
        )
        self.assertEqual(score.status_code, 200)
        self.assertEqual(score.json()["profile_name"], "AluTrade")


class ApiRuntimeBuildTests(unittest.TestCase):
    def test_build_runtime_initializes_real_database_without_name_errors(self):
        import os
        from unittest.mock import patch

        from app.api.runtime import build_runtime

        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "runtime.db"
            profile = CompanyProfile(
                profile_version="1",
                company_name="Runtime test",
                product_keywords=["электротехническое оборудование"],
            )
            with (
                patch("app.llm.config.load_settings", side_effect=RuntimeError("disabled in test")),
                patch("app.scoring.config.load_company_profile", return_value=profile),
                patch("app.database.load_database_settings", return_value=SimpleNamespace(path=db_path)),
                patch("app.rag.load_rag_settings", return_value=SimpleNamespace(enabled=False)),
                patch("app.monitoring.load_monitoring_settings", return_value=SimpleNamespace(source_configured=False)),
            ):
                runtime = build_runtime()

            self.assertIsNotNone(runtime.tender_repository)
            self.assertIs(runtime.company_profile, profile)
            self.assertEqual(runtime.component_status()["database"], "ready")
            self.assertEqual(runtime.component_status()["scoring"], "ready")
            self.assertNotIn("database", runtime.component_errors)


class ApiKeyTests(unittest.TestCase):
    def test_api_key_protects_v1_but_not_health(self):
        settings = ApiSettings(host="127.0.0.1", port=8000, reload=False, api_key="secret")
        runtime = ApiRuntime()
        with TestClient(create_app(runtime=runtime, settings=settings)) as client:
            self.assertEqual(client.get("/health").status_code, 200)
            self.assertEqual(
                client.get("/api/v1/tenders", params={"owner_user_id": 1}).status_code,
                401,
            )
            authorized = client.get(
                "/api/v1/tenders",
                params={"owner_user_id": 1},
                headers={"X-API-Key": "secret"},
            )
            self.assertEqual(authorized.status_code, 503)


if __name__ == "__main__":
    unittest.main()
