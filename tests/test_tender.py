import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from pydantic import ValidationError
from app.models.tender import TenderAnalysis
from app.services.tender_analysis import AnalysisError, AnalysisResult, analyze_tender, prepare_text
from app.llm.models import LLMResponse
from app.llm.base import LLMAuthenticationError, LLMNetworkError, LLMTimeoutError
from app.bot.tender import format_tender, split_messages
from app.bot.documents import pdf_handler
from app.parsers.pdf import PdfSummary


class ModelTests(unittest.TestCase):
    def test_valid(self):
        result = TenderAnalysis(title="Закупка", initial_price=100, bid_security_percent=1)
        self.assertEqual(result.initial_price, 100)

    def test_missing_null(self):
        result = TenderAnalysis(title=None)
        self.assertIsNone(result.customer)
        self.assertEqual(result.risks, [])

    def test_malformed(self):
        for data in ({"initial_price": "100"}, {"initial_price": -1},
                     {"initial_price": float("nan")}, {"initial_price": True},
                     {"bid_security_percent": 101}, {"customer": []},
                     {"risks": "risk"}, {"risks": [123]}, {"extra": 1}):
            with self.subTest(data=data), self.assertRaises(ValidationError):
                TenderAnalysis.model_validate(data)

    def test_normalize_and_truncate(self):
        self.assertEqual(prepare_text("  A   B\r\n\r\n\nC ").text, "A B\n\nC")
        result = prepare_text("abcdef", 3)
        self.assertEqual(result.text, "abc")
        self.assertTrue(result.truncated)
        self.assertEqual(result.original_chars, 6)
        self.assertFalse(prepare_text("abc", 3).truncated)

    def test_empty(self):
        with self.assertRaises(AnalysisError):
            prepare_text(" \n ")

    def test_format(self):
        output = "\n".join(format_tender(AnalysisResult(TenderAnalysis(
            title="<Название>", initial_price=4850000, currency="RUB",
            risks=["Условие документа"], bid_security_percent=0), True)))
        self.assertIn("4 850 000", output)
        self.assertIn("<Название>", output)
        self.assertIn("начальной частью", output)
        self.assertNotIn("None", output)
        self.assertIn("0", output)

    def test_split(self):
        chunks = split_messages(("😀" * 3000) + "\n" + ("текст\n" * 2000))
        self.assertGreater(len(chunks), 2)
        self.assertTrue(all(len(c.encode("utf-16-le")) // 2 <= 3500 for c in chunks))
        self.assertEqual(sum(c.count("😀") for c in chunks), 3000)


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_valid_json(self):
        provider = MagicMock(generate=AsyncMock(return_value=LLMResponse(
            json.dumps({"title": "Поставка", "initial_price": 50}), "mock", "mock")))
        result = await analyze_tender("Документ", provider, 4)
        self.assertEqual(result.analysis.title, "Поставка")
        self.assertTrue(result.truncated)
        self.assertIn("недоверенные", provider.generate.call_args.args[0])

    async def test_invalid_json_and_schema(self):
        for text in ("not json", '[]', '{"initial_price":"10"}', 'NaN',
                     '{"title":"a","title":"b"}', '```json\n{}\n```'):
            provider = MagicMock(generate=AsyncMock(return_value=LLMResponse(text, "mock", "mock")))
            with self.subTest(text=text), self.assertRaises(AnalysisError):
                await analyze_tender("doc", provider)

    async def test_llm_errors(self):
        for error in (LLMAuthenticationError, LLMNetworkError, LLMTimeoutError):
            provider = MagicMock(generate=AsyncMock(side_effect=error("safe")))
            with self.assertRaises(error):
                await analyze_tender("doc", provider)

    async def test_empty_no_call(self):
        provider = MagicMock(generate=AsyncMock())
        with self.assertRaises(AnalysisError):
            await analyze_tender("", provider)
        provider.generate.assert_not_called()

    async def test_truncated_response(self):
        provider = MagicMock(generate=AsyncMock(return_value=LLMResponse(
            "{}", "mock", "mock", finish_reason="length")))
        with self.assertRaises(AnalysisError):
            await analyze_tender("doc", provider)


class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def run_workflow(self, provider, status="ok"):
        message = MagicMock()
        message.document.file_name = "test.pdf"
        message.document.file_size = 10
        message.answer = AsyncMock()
        bot = MagicMock(download=AsyncMock())
        with patch("app.bot.documents.summarize_pdf", AsyncMock(
            return_value=PdfSummary(status, 1, 4, 0, "text"))):
            await pdf_handler(message, bot, provider)
        return message

    async def test_success(self):
        provider = MagicMock(generate=AsyncMock(return_value=LLMResponse(
            '{"title":"Поставка"}', "mock", "mock")))
        message = await self.run_workflow(provider)
        replies = [c.args[0] for c in message.answer.call_args_list]
        self.assertIn("Файл:", replies[1])
        self.assertIn("Начинаю AI-анализ", replies[2])
        self.assertIn("Поставка", replies[3])
        self.assertIsNone(message.answer.call_args.kwargs["parse_mode"])

    async def test_user_errors_safe(self):
        for error in (LLMAuthenticationError, LLMNetworkError, LLMTimeoutError):
            provider = MagicMock(generate=AsyncMock(side_effect=error("SECRET")))
            message = await self.run_workflow(provider)
            self.assertNotIn("SECRET", message.answer.call_args.args[0])
            self.assertIn("AI-анализ недоступен", message.answer.call_args.args[0])

    async def test_textless_skips_model(self):
        provider = MagicMock(generate=AsyncMock())
        await self.run_workflow(provider, "no_text")
        provider.generate.assert_not_called()
