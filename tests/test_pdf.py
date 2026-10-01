import unittest
from unittest.mock import AsyncMock, MagicMock
import pymupdf
from app.parsers.pdf import MAX_BYTES, parse_pdf
from app.services.pdf import LimitedBuffer, summarize_pdf
from app.bot.documents import pdf_handler


def fixture(blank=False, encrypted=False):
    with pymupdf.open() as doc:
        page = doc.new_page()
        if not blank:
            page.insert_text((72, 72), "Tender test")
        doc.new_page()
        options = {"encryption": pymupdf.PDF_ENCRYPT_AES_256, "owner_pw": "owner", "user_pw": "test"} if encrypted else {}
        return doc.tobytes(**options)


class ParserTests(unittest.TestCase):
    def test_text_and_empty_page(self):
        result = parse_pdf(fixture())
        self.assertEqual((result.status, result.pages, result.characters, result.empty_pages), ("ok", 2, len("Tender test\n"), 1))
        self.assertEqual(len(result.page_texts), 2)
        self.assertIn("Tender test", result.page_texts[0])

    def test_blank_pdf_needs_ocr(self):
        result = parse_pdf(fixture(blank=True))
        self.assertEqual((result.status, result.characters), ("no_text", 0))

    def test_password_protection(self):
        self.assertEqual(parse_pdf(fixture(encrypted=True)).status, "encrypted")

    def test_invalid_and_empty(self):
        for data in (b"", b"not a pdf", b"%PDF-1.7 broken"):
            self.assertEqual(parse_pdf(data).status, "invalid")

    def test_page_limit(self):
        with pymupdf.open() as doc:
            for _ in range(201):
                doc.new_page()
            self.assertEqual(parse_pdf(doc.tobytes()).status, "too_many_pages")

    def test_download_limit(self):
        with LimitedBuffer() as stream:
            with self.assertRaises(ValueError):
                stream.write(b"x" * (MAX_BYTES + 1))
            self.assertEqual(len(stream.getvalue()), 0)


class PdfIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_worker(self):
        result = await summarize_pdf(fixture())
        self.assertEqual((result.status, result.pages), ("ok", 2))

    async def test_worker_timeout(self):
        self.assertEqual((await summarize_pdf(fixture(), timeout=0)).status, "timeout")

    async def test_download_parse_reply(self):
        message = MagicMock()
        message.document.file_name = "test.pdf"
        message.document.mime_type = "application/pdf"
        message.document.file_size = None
        message.answer = AsyncMock()
        data = fixture()
        async def download(*args, destination, **kwargs):
            destination.write(data)
        bot = MagicMock()
        bot.download = AsyncMock(side_effect=download)
        await pdf_handler(message, bot)
        reply = message.answer.call_args.args[0]
        self.assertIn("Файл: test.pdf", reply)
        self.assertIn("Страниц: 2", reply)
        self.assertIn("Извлечено символов: 12", reply)
        self.assertIn("Да, текст извлечён", reply)

    async def test_oversize_is_not_downloaded(self):
        message = MagicMock()
        message.document.file_name = "large.pdf"
        message.document.file_size = MAX_BYTES + 1
        message.answer = AsyncMock()
        bot = MagicMock(download=AsyncMock())
        await pdf_handler(message, bot)
        bot.download.assert_not_awaited()
        self.assertIn("превышает лимит", message.answer.call_args.args[0])

    async def test_download_error_no_details_leak(self):
        message = MagicMock()
        message.document.file_name = "file.pdf"
        message.document.file_size = 100
        message.answer = AsyncMock()
        bot = MagicMock(download=AsyncMock(side_effect=RuntimeError("SECRET URL")))
        await pdf_handler(message, bot)
        self.assertIn("не удалось скачать", message.answer.call_args.args[0])
        self.assertNotIn("SECRET", message.answer.call_args.args[0])
