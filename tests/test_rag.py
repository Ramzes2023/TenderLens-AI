import math
import tempfile
import unittest
from pathlib import Path

from app.llm.models import LLMResponse
from app.parsers.pdf import PdfSummary
from app.rag.chunking import chunk_pages, normalize_page
from app.rag.config import RagSettings
from app.rag.embedding import HashEmbeddingProvider
from app.rag.service import RagService
from app.rag.store import SQLiteVectorStore


class RagChunkingTests(unittest.TestCase):
    def test_page_aware_chunks(self):
        chunks = chunk_pages(["Первая страница " * 30, "Срок поставки 30 дней."], 120, 20)
        self.assertGreater(len(chunks), 2)
        self.assertEqual(chunks[-1].page_number, 2)
        self.assertIn("Срок поставки", chunks[-1].text)

    def test_normalization(self):
        self.assertEqual(normalize_page("  A\t B\n\n\nC  "), "A B\n\nC")


class HashEmbeddingTests(unittest.TestCase):
    def test_deterministic_and_normalized(self):
        embedder = HashEmbeddingProvider(128)
        a = embedder.embed("обеспечение контракта")
        b = embedder.embed("обеспечение контракта")
        self.assertEqual(a, b)
        self.assertAlmostEqual(math.sqrt(sum(x * x for x in a)), 1.0, places=5)

    def test_related_forms_have_overlap(self):
        embedder = HashEmbeddingProvider(128)
        a = embedder.embed("поставка оборудования")
        b = embedder.embed("срок поставки оборудования")
        self.assertGreater(sum(x * y for x, y in zip(a, b)), 0)


class VectorStoreTests(unittest.TestCase):
    def test_persistent_search_is_user_and_document_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteVectorStore(Path(directory) / "rag.db", 128)
            store.initialize()
            embedder = HashEmbeddingProvider(128)
            from app.rag.models import DocumentChunk
            first = DocumentChunk(0, 1, "Обеспечение контракта составляет пять процентов.")
            second = DocumentChunk(1, 2, "Адрес поставки Москва.")
            store.replace_document(1, "a" * 64, [
                (first, embedder.embed(first.text)), (second, embedder.embed(second.text))])
            result = store.search(1, "a" * 64, embedder.embed("обеспечение контракта"), 1)
            self.assertEqual(result[0].page_number, 1)
            self.assertEqual(store.search(2, "a" * 64, embedder.embed("обеспечение"), 5), [])
            self.assertFalse(store.has_document(1, "b" * 64))


class FakeProvider:
    def __init__(self):
        self.prompts = []

    async def generate(self, prompt: str, *, max_tokens: int = 512):
        self.prompts.append(prompt)
        return LLMResponse("Срок поставки — 30 дней [стр. 2].", "mock", "mock")


class RagServiceTests(unittest.IsolatedAsyncioTestCase):
    def settings(self, directory):
        return RagSettings(True, Path(directory) / "rag.db", 300, 40, 128, 3, 2000)

    async def test_index_retrieve_and_grounded_answer(self):
        with tempfile.TemporaryDirectory() as directory:
            service = RagService(self.settings(directory))
            summary = PdfSummary(
                "ok", 2, 100, 0,
                "Общие условия\nСрок поставки 30 дней",
                ("Общие условия закупки.", "Срок поставки составляет 30 календарных дней."),
            )
            count = service.index_pdf(42, "c" * 64, summary)
            self.assertGreaterEqual(count, 2)
            provider = FakeProvider()
            answer = await service.answer(42, "c" * 64, "Какой срок поставки?", provider)
            self.assertIn("30 дней", answer.answer)
            self.assertTrue(any(item.page_number == 2 for item in answer.sources))
            self.assertIn("только по фрагментам", provider.prompts[0])
            self.assertIn("стр. 2", provider.prompts[0])

    async def test_fallback_to_full_text_when_page_texts_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            service = RagService(self.settings(directory))
            summary = PdfSummary("ok", 1, 10, 0, "Нужный текст")
            self.assertEqual(service.index_pdf(1, "d" * 64, summary), 1)
            self.assertTrue(service.has_document(1, "d" * 64))


if __name__ == "__main__":
    unittest.main()
