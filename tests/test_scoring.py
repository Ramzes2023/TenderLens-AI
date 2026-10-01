import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.bot.documents import pdf_handler
from app.bot.scoring import format_scoring
from app.llm.models import LLMResponse
from app.models.tender import TenderAnalysis
from app.parsers.pdf import PdfSummary
from app.scoring.config import ScoringConfigurationError, load_company_profile
from app.scoring.engine import score_tender
from app.scoring.models import CompanyProfile


def profile(**overrides):
    data = {
        "profile_version": "test-1",
        "company_name": "Test Supplier",
        "product_keywords": ["электротехническое оборудование", "контакторы"],
        "allowed_regions": ["Москва"],
        "accepted_currencies": ["RUB"],
        "max_contract_value": 15_000_000,
        "max_bid_security_percent": 3,
        "max_contract_security_percent": 10,
        "available_document_keywords": ["ЕГРЮЛ", "техническое предложение", "сертификат соответствия ЕАЭС"],
        "hard_stop_on_region": True,
        "hard_stop_on_budget": True,
        "hard_stop_on_currency": True,
        "hard_stop_on_bid_security": False,
        "hard_stop_on_contract_security": False,
    }
    data.update(overrides)
    return CompanyProfile.model_validate(data)


def tender(**overrides):
    data = {
        "title": "Поставка электротехнического оборудования",
        "tender_number": "T-1",
        "customer": "ООО Заказчик",
        "initial_price": 4_850_000.0,
        "currency": "рубль (RUB)",
        "submission_deadline": "15.10.2026",
        "contract_term": "30 дней",
        "delivery_region": "Москва",
        "delivery_address": "г. Москва",
        "bid_security_amount": 48_500.0,
        "bid_security_percent": 1.0,
        "contract_security_amount": 242_500.0,
        "contract_security_percent": 5.0,
        "procurement_object": "автоматические выключатели и контакторы",
        "quantity": "320 единиц",
        "participant_requirements": ["Опыт поставки"],
        "required_documents": [
            "Выписка из ЕГРЮЛ",
            "Техническое предложение",
            "Сертификат соответствия ЕАЭС",
        ],
        "technical_requirements": ["Новое оборудование"],
        "risks": ["Неустойка 0,1% за день"],
        "important_conditions": ["Поставка одной партией"],
        "missing_information": [],
    }
    data.update(overrides)
    return TenderAnalysis.model_validate(data)


class EngineTests(unittest.TestCase):
    def test_full_match_is_reproducible(self):
        result = score_tender(tender(), profile())
        self.assertEqual(result.fit_score, 100.0)
        self.assertEqual(result.scorable_weight, 100)
        self.assertEqual(result.completeness_percent, 100)
        self.assertEqual(result.stop_factors, [])
        self.assertEqual(result.document_risks, ["Неустойка 0,1% за день"])
        self.assertTrue(all(item.status == "matched" for item in result.criteria))

    def test_budget_failure_creates_hard_stop(self):
        result = score_tender(tender(initial_price=20_000_000.0), profile())
        budget = next(item for item in result.criteria if item.code == "budget")
        self.assertEqual(budget.status, "failed")
        self.assertEqual(budget.earned_points, 0)
        self.assertTrue(any("превышает лимит" in item for item in result.stop_factors))
        self.assertLess(result.fit_score, 100)

    def test_region_failure_creates_hard_stop(self):
        result = score_tender(tender(delivery_region="Казань", delivery_address="Казань"), profile())
        region = next(item for item in result.criteria if item.code == "region")
        self.assertEqual(region.status, "failed")
        self.assertTrue(result.stop_factors)

    def test_missing_data_is_not_silently_failed(self):
        result = score_tender(tender(
            initial_price=None, currency=None, delivery_region=None, delivery_address=None,
            bid_security_percent=None, contract_security_percent=None, required_documents=[]), profile())
        statuses = {item.code: item.status for item in result.criteria}
        self.assertEqual(statuses["budget"], "not_scored")
        self.assertEqual(statuses["region"], "not_scored")
        self.assertEqual(statuses["documents"], "not_scored")
        self.assertLess(result.scorable_weight, 100)
        self.assertLess(result.completeness_percent, 100)

    def test_partial_document_readiness(self):
        result = score_tender(tender(required_documents=["Выписка из ЕГРЮЛ", "Лицензия ФСБ"]), profile())
        docs = next(item for item in result.criteria if item.code == "documents")
        self.assertEqual(docs.status, "partial")
        self.assertEqual(docs.earned_points, 7.5)
        self.assertTrue(any("Не подтверждено" in item for item in docs.evidence))

    def test_security_is_separate_from_document_risk(self):
        result = score_tender(tender(bid_security_percent=5.0), profile())
        bid = next(item for item in result.criteria if item.code == "bid_security")
        self.assertEqual(bid.status, "failed")
        self.assertFalse(any("Обеспечение заявки" in item for item in result.stop_factors))
        self.assertEqual(result.document_risks, ["Неустойка 0,1% за день"])


class FormattingTests(unittest.TestCase):
    def test_output_does_not_claim_win_probability_or_recommendation(self):
        text = "\n".join(format_scoring(score_tender(tender(), profile())))
        self.assertIn("100/100", text)
        self.assertIn("Полнота", text)
        self.assertIn("не вероятность победы", text)
        self.assertIn("не рекомендация", text)
        self.assertNotIn("участвуйте", text.lower())


class ConfigTests(unittest.TestCase):
    def test_load_profile_from_explicit_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            path.write_text(json.dumps(profile().model_dump(), ensure_ascii=False), encoding="utf-8")
            with patch.dict(os.environ, {"COMPANY_PROFILE_FILE": str(path)}, clear=False):
                loaded = load_company_profile(Path(directory) / "missing.env")
            self.assertEqual(loaded.company_name, "Test Supplier")

    def test_invalid_profile_is_safe_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            path.write_text("{bad", encoding="utf-8")
            with patch.dict(os.environ, {"COMPANY_PROFILE_FILE": str(path)}, clear=False):
                with self.assertRaises(ScoringConfigurationError):
                    load_company_profile(Path(directory) / "missing.env")


class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_pdf_workflow_appends_deterministic_score(self):
        message = MagicMock()
        message.document.file_name = "test.pdf"
        message.document.file_size = 10
        message.answer = AsyncMock()
        bot = MagicMock(download=AsyncMock())
        provider = MagicMock(generate=AsyncMock(return_value=LLMResponse(
            json.dumps(tender().model_dump(), ensure_ascii=False), "mock", "mock")))
        with patch("app.bot.documents.summarize_pdf", AsyncMock(
            return_value=PdfSummary("ok", 1, 100, 0, "text"))):
            await pdf_handler(message, bot, provider, 20000, profile())
        replies = [call.args[0] for call in message.answer.call_args_list]
        self.assertTrue(any("СООТВЕТСТВИЕ ПРОФИЛЮ" in item for item in replies))
        self.assertTrue(any("не вероятность победы" in item for item in replies))
