import importlib.util
import math
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.llm.config import GigaChatSettings
from app.llm.models import LLMResponse
from app.parsers.pdf import PdfSummary
from app.rag.chunking import chunk_pages, normalize_page
from app.rag.config import RagSettings, load_rag_settings
from app.rag.embedding import FastEmbedEmbeddingProvider, GigaChatEmbeddingProvider
from app.rag.models import DocumentChunk
from app.rag.qdrant_store import QdrantVectorStore
from app.rag.service import RagService

HAS_QDRANT = importlib.util.find_spec("qdrant_client") is not None


class RagChunkingTests(unittest.TestCase):
    def test_page_aware_chunks(self):
        chunks = chunk_pages(["Первая страница " * 30, "Срок поставки 30 дней."], 120, 20)
        self.assertGreater(len(chunks), 2)
        self.assertEqual(chunks[-1].page_number, 2)
        self.assertIn("Срок поставки", chunks[-1].text)

    def test_normalization(self):
        self.assertEqual(normalize_page("  A\t B\n\n\nC  "), "A B\n\nC")


class RagConfigTests(unittest.TestCase):
    def test_semantic_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            env = Path(directory) / ".env"
            env.write_text("RAG_ENABLED=true\nRAG_QDRANT_COLLECTION=test_collection\n", encoding="utf-8")
            keys = [
                "RAG_ENABLED", "RAG_QDRANT_PATH", "RAG_QDRANT_COLLECTION", "RAG_EMBEDDING_MODEL",
                "RAG_EMBEDDING_PROVIDER", "RAG_CHUNK_SIZE", "RAG_CHUNK_OVERLAP", "RAG_TOP_K", "RAG_MAX_CONTEXT_CHARS",
            ]
            old = {key: os.environ.pop(key, None) for key in keys}
            try:
                settings = load_rag_settings(env)
            finally:
                for key, value in old.items():
                    if value is not None:
                        os.environ[key] = value
            self.assertEqual(settings.embedding_provider, "fastembed")
            self.assertEqual(settings.embedding_model, "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
            self.assertEqual(settings.qdrant_collection, "test_collection")
            self.assertEqual(settings.qdrant_path.parts[-2:], ("data", "qdrant"))


class FakeGigaChatClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def embeddings(self, texts, model):
        data = []
        for index, text in enumerate(texts):
            seed = float(len(text))
            data.append(SimpleNamespace(index=index, embedding=[seed, 1.0, 0.5]))
        return SimpleNamespace(data=data)


class SemanticEmbeddingTests(unittest.TestCase):
    def test_gigachat_embeddings_are_ordered_and_validated(self):
        settings = GigaChatSettings("secret", "GigaChat-2", timeout=5)
        with patch("app.rag.embedding.GigaChat", FakeGigaChatClient):
            embedder = GigaChatEmbeddingProvider(settings, "Embeddings-2")
            vectors = embedder.embed_many(["abc", "abcdef"])
        self.assertEqual(len(vectors), 2)
        self.assertEqual(len(vectors[0]), 3)
        self.assertEqual(vectors[0][0], 3.0)
        self.assertEqual(vectors[1][0], 6.0)
        self.assertTrue(all(math.isfinite(v) for vector in vectors for v in vector))


class FakeFastEmbedModel:
    def __init__(self, model_name):
        self.model_name = model_name
        self.seen = []

    def embed(self, texts):
        self.seen.extend(texts)
        for text in texts:
            yield [float(len(text)), 2.0, 1.0]


class LocalEmbeddingTests(unittest.TestCase):
    def test_fastembed_default_minilm_uses_plain_text(self):
        with patch("app.rag.embedding.TextEmbedding", FakeFastEmbedModel):
            embedder = FastEmbedEmbeddingProvider(
                "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
            )
            docs = embedder.embed_many(["Срок поставки 30 дней"])
            query = embedder.embed("Когда поставка?")
            self.assertEqual(len(docs[0]), 3)
            self.assertEqual(len(query), 3)
            self.assertEqual(embedder._client.seen[0], "Срок поставки 30 дней")
            self.assertEqual(embedder._client.seen[1], "Когда поставка?")

    def test_fastembed_e5_models_use_query_and_passage_prefixes(self):
        with patch("app.rag.embedding.TextEmbedding", FakeFastEmbedModel):
            embedder = FastEmbedEmbeddingProvider("intfloat/multilingual-e5-small")
            embedder.embed_many(["Срок поставки 30 дней"])
            embedder.embed("Когда поставка?")
            self.assertTrue(embedder._client.seen[0].startswith("passage: "))
            self.assertTrue(embedder._client.seen[1].startswith("query: "))


class FakeSemanticEmbedder:
    """Small semantic-like mapping for deterministic unit tests."""

    @staticmethod
    def _vector(text: str) -> tuple[float, ...]:
        lower = text.casefold()
        if "срок" in lower or "дней" in lower or "постав" in lower:
            return (1.0, 0.0, 0.0, 0.0)
        if "сертифик" in lower or "еаэс" in lower:
            return (0.0, 1.0, 0.0, 0.0)
        if "москва" in lower or "адрес" in lower:
            return (0.0, 0.0, 1.0, 0.0)
        return (0.0, 0.0, 0.0, 1.0)

    def embed(self, text: str) -> tuple[float, ...]:
        return self._vector(text)

    def embed_many(self, texts):
        return [self._vector(text) for text in texts]


@unittest.skipUnless(HAS_QDRANT, "qdrant-client is not installed")
class QdrantStoreTests(unittest.TestCase):
    def test_persistent_search_is_user_and_document_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            store = QdrantVectorStore(Path(directory) / "qdrant", "test_chunks")
            store.initialize()
            first = DocumentChunk(0, 1, "Обеспечение и сертификат ЕАЭС.")
            second = DocumentChunk(1, 2, "Адрес поставки Москва.")
            store.replace_document(1, "a" * 64, [
                (first, (0.0, 1.0, 0.0, 0.0)),
                (second, (0.0, 0.0, 1.0, 0.0)),
            ])
            result = store.search(1, "a" * 64, (0.0, 1.0, 0.0, 0.0), 1)
            self.assertEqual(result[0].page_number, 1)
            self.assertEqual(store.search(2, "a" * 64, (0.0, 1.0, 0.0, 0.0), 5), [])
            self.assertFalse(store.has_document(1, "b" * 64))
        # TemporaryDirectory cleanup succeeding also verifies Qdrant released Windows file locks.


class FakeProvider:
    def __init__(self):
        self.prompts = []

    async def generate(self, prompt: str, *, max_tokens: int = 512):
        self.prompts.append(prompt)
        return LLMResponse("Срок поставки — 30 дней [стр. 2].", "mock", "mock")


@unittest.skipUnless(HAS_QDRANT, "qdrant-client is not installed")
class RagServiceTests(unittest.IsolatedAsyncioTestCase):
    def settings(self, directory):
        return RagSettings(
            True,
            Path(directory) / "qdrant",
            "service_chunks",
            "mock-embeddings",
            300,
            40,
            3,
            2000,
        )

    async def test_index_retrieve_and_grounded_answer(self):
        with tempfile.TemporaryDirectory() as directory:
            service = RagService(self.settings(directory), embedder=FakeSemanticEmbedder())
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
            self.assertIn("semantic search", provider.prompts[0])
            self.assertIn("стр. 2", provider.prompts[0])

    async def test_organization_namespace_isolated_from_legacy_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            service = RagService(
                self.settings(directory),
                embedder=FakeSemanticEmbedder(),
            )

            digest = "e" * 64

            legacy_summary = PdfSummary(
                "ok",
                1,
                40,
                0,
                "???? ???????? legacy 10 ????.",
                ("???? ???????? legacy 10 ????.",),
            )

            organization_summary = PdfSummary(
                "ok",
                1,
                50,
                0,
                "???? ???????? organization 20 ????.",
                ("???? ???????? organization 20 ????.",),
            )

            service.index_pdf(
                42,
                digest,
                legacy_summary,
            )

            service.index_pdf_for_organization(
                42,
                digest,
                organization_summary,
            )

            self.assertTrue(
                service.has_document(
                    42,
                    digest,
                )
            )

            self.assertTrue(
                service.has_document_for_organization(
                    42,
                    digest,
                )
            )

            self.assertFalse(
                service.has_document_for_organization(
                    43,
                    digest,
                )
            )

            legacy = service.retrieve(
                42,
                digest,
                "????? ???? ?????????",
            )

            organization = service.retrieve_for_organization(
                42,
                digest,
                "????? ???? ?????????",
            )

            self.assertTrue(legacy)
            self.assertTrue(organization)

            self.assertIn(
                "legacy 10",
                legacy[0].text,
            )

            self.assertIn(
                "organization 20",
                organization[0].text,
            )

    async def test_same_hash_isolated_across_legacy_and_two_organizations(self):
        with tempfile.TemporaryDirectory() as directory:
            service = RagService(
                self.settings(directory),
                embedder=FakeSemanticEmbedder(),
            )

            digest = "f" * 64

            legacy_summary = PdfSummary(
                "ok",
                1,
                30,
                0,
                "???? legacy 11 ????.",
                ("???? legacy 11 ????.",),
            )

            organization_a_summary = PdfSummary(
                "ok",
                1,
                30,
                0,
                "???? organization A 22 ???.",
                ("???? organization A 22 ???.",),
            )

            organization_b_summary = PdfSummary(
                "ok",
                1,
                30,
                0,
                "???? organization B 33 ???.",
                ("???? organization B 33 ???.",),
            )

            service.index_pdf(
                42,
                digest,
                legacy_summary,
            )

            service.index_pdf_for_organization(
                42,
                digest,
                organization_a_summary,
            )

            service.index_pdf_for_organization(
                43,
                digest,
                organization_b_summary,
            )

            legacy = service.retrieve(
                42,
                digest,
                "????? ?????",
            )

            organization_a = (
                service.retrieve_for_organization(
                    42,
                    digest,
                    "????? ?????",
                )
            )

            organization_b = (
                service.retrieve_for_organization(
                    43,
                    digest,
                    "????? ?????",
                )
            )

            self.assertTrue(legacy)
            self.assertTrue(organization_a)
            self.assertTrue(organization_b)

            self.assertIn(
                "legacy 11",
                legacy[0].text,
            )

            self.assertIn(
                "organization A 22",
                organization_a[0].text,
            )

            self.assertIn(
                "organization B 33",
                organization_b[0].text,
            )

            self.assertNotIn(
                "organization",
                legacy[0].text,
            )

            self.assertNotIn(
                "legacy",
                organization_a[0].text,
            )

            self.assertNotIn(
                "organization B",
                organization_a[0].text,
            )

            self.assertNotIn(
                "organization A",
                organization_b[0].text,
            )

    async def test_fallback_to_full_text_when_page_texts_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            service = RagService(self.settings(directory), embedder=FakeSemanticEmbedder())
            summary = PdfSummary("ok", 1, 10, 0, "Нужный текст")
            self.assertEqual(service.index_pdf(1, "d" * 64, summary), 1)
            self.assertTrue(service.has_document(1, "d" * 64))


if __name__ == "__main__":
    unittest.main()
