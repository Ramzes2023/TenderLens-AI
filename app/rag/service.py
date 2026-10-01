"""RAG orchestration: page chunks -> vectors -> retrieval -> grounded LLM answer."""
from __future__ import annotations

from app.llm.base import LLMProvider
from app.parsers.pdf import PdfSummary

from .chunking import chunk_pages
from .config import RagSettings
from .embedding import HashEmbeddingProvider
from .models import RagAnswer, RetrievedChunk
from .store import RagStoreError, SQLiteVectorStore


class RagError(RuntimeError):
    pass


class RagService:
    def __init__(self, settings: RagSettings):
        self.settings = settings
        self.embedder = HashEmbeddingProvider(settings.vector_dimensions)
        self.store = SQLiteVectorStore(settings.database_path, settings.vector_dimensions)
        self.store.initialize()

    def has_document(self, owner_user_id: int, pdf_sha256: str) -> bool:
        return self.store.has_document(owner_user_id, pdf_sha256)

    def index_pdf(self, owner_user_id: int, pdf_sha256: str, summary: PdfSummary) -> int:
        page_texts = tuple(summary.page_texts or ())
        if not page_texts and summary.text.strip():
            page_texts = (summary.text,)
        chunks = chunk_pages(page_texts, self.settings.chunk_size, self.settings.chunk_overlap)
        if not chunks:
            raise RagError("В документе нет текста для RAG-индекса.")
        items = [(chunk, self.embedder.embed(chunk.text)) for chunk in chunks]
        return self.store.replace_document(owner_user_id, pdf_sha256, items)

    def retrieve(self, owner_user_id: int, pdf_sha256: str, question: str) -> list[RetrievedChunk]:
        question = question.strip()
        if not question:
            raise RagError("Вопрос не должен быть пустым.")
        vector = self.embedder.embed(question)
        return self.store.search(owner_user_id, pdf_sha256, vector, self.settings.top_k)

    async def answer(self, owner_user_id: int, pdf_sha256: str, question: str,
                     provider: LLMProvider) -> RagAnswer:
        chunks = self.retrieve(owner_user_id, pdf_sha256, question)
        if not chunks:
            raise RagError("Для этого документа RAG-индекс пока не найден.")
        selected: list[RetrievedChunk] = []
        context_parts: list[str] = []
        total = 0
        for number, chunk in enumerate(chunks, start=1):
            block = f"[Источник {number}, стр. {chunk.page_number}]\n{chunk.text}"
            if selected and total + len(block) > self.settings.max_context_chars:
                break
            context_parts.append(block)
            selected.append(chunk)
            total += len(block)
        context = "\n\n".join(context_parts)
        prompt = (
            "Ты отвечаешь на вопрос только по фрагментам тендерной документации ниже.\n"
            "Не используй внешние знания и не додумывай отсутствующие факты.\n"
            "Если ответа в предоставленных фрагментах нет, прямо скажи: "
            "«В найденных фрагментах документа ответа нет».\n"
            "Дай краткий ответ на русском языке. После утверждений при возможности указывай "
            "номер страницы в формате [стр. N].\n\n"
            f"ВОПРОС:\n{question.strip()}\n\nФРАГМЕНТЫ:\n{context}"
        )
        response = await provider.generate(prompt, max_tokens=700)
        return RagAnswer(response.text.strip(), tuple(selected))
