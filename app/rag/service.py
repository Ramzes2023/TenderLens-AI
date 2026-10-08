"""Semantic RAG orchestration: PDF chunks -> GigaChat embeddings -> Qdrant -> grounded answer."""
from __future__ import annotations
from app.llm.cache import generate_operation, RAG_ANSWER

import asyncio

from app.llm.base import LLMProvider
from app.llm.config import load_settings as load_llm_settings
from app.parsers.pdf import PdfSummary
from app.tenancy import organization_owner_id

from .chunking import chunk_pages
from .config import RagSettings
from .embedding import (EmbeddingError, EmbeddingProvider, FastEmbedEmbeddingProvider,
                        GigaChatEmbeddingProvider)
from .models import RagAnswer, RetrievedChunk
from .qdrant_store import QdrantStoreError, QdrantVectorStore


class RagError(RuntimeError):
    pass


class RagService:
    def __init__(
        self,
        settings: RagSettings,
        *,
        embedder: EmbeddingProvider | None = None,
        store: QdrantVectorStore | None = None,
    ):
        self.settings = settings
        if embedder is None:
            if settings.embedding_provider == "fastembed":
                try:
                    embedder = FastEmbedEmbeddingProvider(settings.embedding_model)
                except EmbeddingError as error:
                    raise RagError(str(error)) from None
            elif settings.embedding_provider == "gigachat":
                try:
                    llm_settings = load_llm_settings()
                except Exception:
                    raise RagError("Для GigaChat embeddings не удалось загрузить настройки GigaChat.") from None
                embedder = GigaChatEmbeddingProvider(llm_settings, settings.embedding_model)
            else:
                raise RagError("Неизвестный RAG embedding provider.")
        self.embedder = embedder
        self.store = store or QdrantVectorStore(settings.qdrant_path, settings.qdrant_collection)
        self.store.initialize()

    def has_document(self, owner_user_id: int, pdf_sha256: str) -> bool:
        return self.store.has_document(owner_user_id, pdf_sha256)

    def has_document_for_organization(
        self,
        organization_id: int,
        pdf_sha256: str,
    ) -> bool:
        return self.has_document(
            organization_owner_id(organization_id),
            pdf_sha256,
        )

    def index_pdf_for_organization(
        self,
        organization_id: int,
        pdf_sha256: str,
        summary: PdfSummary,
    ) -> int:
        return self.index_pdf(
            organization_owner_id(organization_id),
            pdf_sha256,
            summary,
        )

    def retrieve_for_organization(
        self,
        organization_id: int,
        pdf_sha256: str,
        question: str,
    ) -> list[RetrievedChunk]:
        return self.retrieve(
            organization_owner_id(organization_id),
            pdf_sha256,
            question,
        )

    async def answer_for_organization(
        self,
        organization_id: int,
        pdf_sha256: str,
        question: str,
        provider: LLMProvider,
    ) -> RagAnswer:
        return await self.answer(
            organization_owner_id(organization_id),
            pdf_sha256,
            question,
            provider,
        )

    def index_pdf(self, owner_user_id: int, pdf_sha256: str, summary: PdfSummary) -> int:
        page_texts = tuple(summary.page_texts or ())
        if not page_texts and summary.text.strip():
            page_texts = (summary.text,)
        chunks = chunk_pages(page_texts, self.settings.chunk_size, self.settings.chunk_overlap)
        if not chunks:
            raise RagError("В документе нет текста для RAG-индекса.")
        try:
            vectors = self.embedder.embed_many([chunk.text for chunk in chunks])
        except EmbeddingError as error:
            raise RagError(str(error)) from None
        if len(vectors) != len(chunks):
            raise RagError("Embedding provider вернул неверное число векторов.")
        return self.store.replace_document(
            owner_user_id,
            pdf_sha256,
            list(zip(chunks, vectors, strict=True)),
        )

    def retrieve(self, owner_user_id: int, pdf_sha256: str, question: str) -> list[RetrievedChunk]:
        question = question.strip()
        if not question:
            raise RagError("Вопрос не должен быть пустым.")
        try:
            vector = self.embedder.embed(question)
        except EmbeddingError as error:
            raise RagError(str(error)) from None
        return self.store.search(owner_user_id, pdf_sha256, vector, self.settings.top_k)

    async def answer(
        self,
        owner_user_id: int,
        pdf_sha256: str,
        question: str,
        provider: LLMProvider,
    ) -> RagAnswer:
        # Embedding can be CPU-heavy or network-bound; keep it off the aiogram event loop.
        chunks = await asyncio.to_thread(self.retrieve, owner_user_id, pdf_sha256, question)
        if not chunks:
            raise RagError("Для этого документа semantic RAG-индекс пока не найден.")
        selected: list[RetrievedChunk] = []
        context_parts: list[str] = []
        total = 0
        for number, chunk in enumerate(chunks, start=1):
            block = f"[Источник {number}, стр. {chunk.page_number}, score={chunk.score:.3f}]\n{chunk.text}"
            if selected and total + len(block) > self.settings.max_context_chars:
                break
            context_parts.append(block)
            selected.append(chunk)
            total += len(block)
        context = "\n\n".join(context_parts)
        prompt = (
            "Ты отвечаешь на вопрос только по найденным фрагментам тендерной документации ниже.\n"
            "Фрагменты выбраны semantic search по embeddings и Qdrant.\n"
            "Не используй внешние знания и не додумывай отсутствующие факты.\n"
            "Если ответа в предоставленных фрагментах нет, прямо скажи: "
            "«В найденных фрагментах документа ответа нет».\n"
            "Дай краткий ответ на русском языке. После фактов указывай страницу в формате [стр. N].\n\n"
            f"ВОПРОС:\n{question.strip()}\n\nФРАГМЕНТЫ:\n{context}"
        )
        response = await generate_operation(provider, RAG_ANSWER, prompt, max_tokens=700)
        return RagAnswer(response.text.strip(), tuple(selected))
