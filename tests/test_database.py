import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.database.config import DatabaseConfigurationError, load_database_settings
from app.database.repository import TenderRepository
from app.models.tender import TenderAnalysis
from app.scoring.models import CriterionResult, ScoringResult
from app.bot.history import format_history, history_handler
from app.bot.documents import pdf_handler
from app.parsers.pdf import PdfSummary


class DatabaseConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env_file = Path(self.tmp.name) / ".env"
        self.patch = patch.dict(os.environ, {}, clear=True)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_default_and_relative_sqlite(self):
        settings = load_database_settings(self.env_file)
        self.assertTrue(str(settings.path).endswith(str(Path("data") / "tenderlens.db")))
        os.environ["DATABASE_URL"] = "sqlite:///./local/history.db"
        settings = load_database_settings(self.env_file)
        self.assertTrue(str(settings.path).endswith(str(Path("local") / "history.db")))

    def test_postgresql_supported(self):
        os.environ["DATABASE_URL"] = "postgresql://localhost/tenderlens"
        settings = load_database_settings(self.env_file)
        self.assertEqual(settings.backend, "postgresql")
        self.assertIsNone(settings.path)


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = TenderRepository(Path(self.tmp.name) / "db.sqlite3")
        self.repo.initialize()
        self.analysis = TenderAnalysis(title="Поставка", customer="Заказчик", initial_price=100)
        self.scoring = ScoringResult(
            profile_name="Demo", profile_version="1", fit_score=80, scorable_weight=100,
            completeness_percent=70,
            criteria=[CriterionResult(code="x", label="Тест", weight=10, earned_points=8,
                                      status="partial", explanation="ok")],
        )

    def save(self, user=1, digest="a" * 64, filename="a.pdf"):
        return self.repo.save_success(
            owner_user_id=user, chat_id=user, pdf_sha256=digest, source_filename=filename,
            pages=2, characters=1234, analysis=self.analysis, scoring=self.scoring,
            analysis_truncated=False,
        )

    def test_save_find_and_list(self):
        stored = self.save()
        self.assertEqual(stored.analysis.title, "Поставка")
        self.assertEqual(stored.scoring.fit_score, 80)
        found = self.repo.find_by_hash(1, "a" * 64)
        self.assertEqual(found.id, stored.id)
        self.assertEqual(self.repo.find_by_id(1, stored.id).id, stored.id)
        self.assertIsNone(self.repo.find_by_id(2, stored.id))
        self.assertEqual(len(self.repo.list_recent(1)), 1)

    def test_user_isolation_and_upsert(self):
        first = self.save(user=1, digest="b" * 64, filename="first.pdf")
        self.assertIsNone(self.repo.find_by_hash(2, "b" * 64))
        second = self.save(user=1, digest="b" * 64, filename="renamed.pdf")
        self.assertEqual(first.id, second.id)
        self.assertEqual(second.source_filename, "renamed.pdf")
        other = self.save(user=2, digest="b" * 64)
        self.assertNotEqual(first.id, other.id)

    def test_database_does_not_store_raw_pdf_or_text(self):
        self.save()
        raw = (Path(self.tmp.name) / "db.sqlite3").read_bytes()
        self.assertNotIn(b"%PDF", raw)
        self.assertNotIn(b"FULL EXTRACTED SECRET TEXT", raw)


class HistoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_and_records(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repo = TenderRepository(Path(tmp.name) / "db.sqlite")
        repo.initialize()
        self.assertIn("пуста", format_history([])[0])
        repo.save_success(owner_user_id=42, chat_id=42, pdf_sha256="c" * 64,
                          source_filename="file.pdf", pages=1, characters=10,
                          analysis=TenderAnalysis(title="История"), scoring=None,
                          analysis_truncated=False)
        rendered = "\n".join(format_history(repo.list_recent(42)))
        self.assertIn("История", rendered)
        self.assertIn("#1", rendered)

        message = MagicMock()
        message.from_user.id = 42
        message.answer = AsyncMock()
        await history_handler(message, repo)
        self.assertIn("ПОСЛЕДНИЕ", message.answer.call_args.args[0])

    async def test_history_is_user_scoped(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repo = TenderRepository(Path(tmp.name) / "db.sqlite")
        repo.initialize()
        repo.save_success(owner_user_id=1, chat_id=1, pdf_sha256="d" * 64,
                          source_filename="private.pdf", pages=1, characters=5,
                          analysis=TenderAnalysis(title="Private"), scoring=None,
                          analysis_truncated=False)
        message = MagicMock()
        message.from_user.id = 2
        message.answer = AsyncMock()
        await history_handler(message, repo)
        self.assertIn("пуста", message.answer.call_args.args[0])
        self.assertNotIn("Private", message.answer.call_args.args[0])


class DedupWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_skips_parser_and_llm(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repo = TenderRepository(Path(tmp.name) / "db.sqlite")
        repo.initialize()
        data = b"same pdf bytes"
        import hashlib
        digest = hashlib.sha256(data).hexdigest()
        repo.save_success(owner_user_id=42, chat_id=42, pdf_sha256=digest,
                          source_filename="old.pdf", pages=1, characters=10,
                          analysis=TenderAnalysis(title="Stored tender"), scoring=None,
                          analysis_truncated=False)

        message = MagicMock()
        message.document.file_name = "same.pdf"
        message.document.mime_type = "application/pdf"
        message.document.file_size = len(data)
        message.from_user.id = 42
        message.chat.id = 42
        message.answer = AsyncMock()
        async def download(*args, destination, **kwargs):
            destination.write(data)
        bot = MagicMock(download=AsyncMock(side_effect=download))
        provider = MagicMock(generate=AsyncMock())
        with patch("app.bot.documents.summarize_pdf", AsyncMock()) as parser:
            await pdf_handler(message, bot, provider, tender_repository=repo)
        parser.assert_not_awaited()
        provider.generate.assert_not_awaited()
        replies = [call.args[0] for call in message.answer.call_args_list]
        self.assertTrue(any("уже был обработан" in text for text in replies))
        self.assertTrue(any("Stored tender" in text for text in replies))

    async def test_success_is_saved(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repo = TenderRepository(Path(tmp.name) / "db.sqlite")
        repo.initialize()
        data = b"new pdf bytes"
        message = MagicMock()
        message.document.file_name = "new.pdf"
        message.document.mime_type = "application/pdf"
        message.document.file_size = len(data)
        message.from_user.id = 55
        message.chat.id = 55
        message.answer = AsyncMock()
        async def download(*args, destination, **kwargs):
            destination.write(data)
        bot = MagicMock(download=AsyncMock(side_effect=download))
        from app.llm.models import LLMResponse
        provider = MagicMock(generate=AsyncMock(return_value=LLMResponse(
            json.dumps({"title": "Saved"}), "mock", "mock")))
        with patch("app.bot.documents.summarize_pdf", AsyncMock(
                return_value=PdfSummary("ok", 1, 4, 0, "text"))):
            await pdf_handler(message, bot, provider, tender_repository=repo)
        import hashlib
        stored = repo.find_by_hash(55, hashlib.sha256(data).hexdigest())
        self.assertIsNotNone(stored)
        self.assertEqual(stored.analysis.title, "Saved")
        self.assertTrue(any("Результат сохранён" in c.args[0] for c in message.answer.call_args_list))


if __name__ == "__main__":
    unittest.main()
