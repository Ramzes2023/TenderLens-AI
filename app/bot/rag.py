"""Telegram /ask command backed by the latest indexed tender for the user."""
from __future__ import annotations

import asyncio

from aiogram.types import Message

from app.database.repository import DatabaseError, TenderRepository
from app.llm.base import LLMError, LLMProvider
from app.rag.service import RagError, RagService
from app.rag.qdrant_store import QdrantStoreError
from .tender import split_messages


def _owner_id(message: Message) -> int | None:
    value = getattr(getattr(message, "from_user", None), "id", None)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _question(message: Message) -> str:
    text = (getattr(message, "text", None) or "").strip()
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) == 2 else ""


def format_rag_answer(answer, source_filename: str) -> list[str]:
    pages = sorted({chunk.page_number for chunk in answer.sources})
    page_text = ", ".join(str(page) for page in pages) if pages else "—"
    body = (
        "🔎 ОТВЕТ ПО ДОКУМЕНТУ\n\n"
        f"{answer.answer}\n\n"
        f"📄 Документ: {source_filename}\n"
        f"📚 Найденные страницы: {page_text}\n\n"
        "Ответ сформирован только из найденных фрагментов документа. Проверяйте критичные условия по оригиналу."
    )
    return split_messages(body)


async def ask_handler(message: Message, tender_repository: TenderRepository | None = None,
                      rag_service: RagService | None = None,
                      tender_provider: LLMProvider | None = None) -> None:
    question = _question(message)
    if not question:
        await message.answer(
            "Напишите вопрос после команды. Например:\n/ask Какой срок поставки?\n"
            "/ask Какие сертификаты нужны?",
            parse_mode=None,
        )
        return
    owner = _owner_id(message)
    if owner is None:
        await message.answer("Не удалось определить пользователя для RAG-поиска.")
        return
    if tender_repository is None or rag_service is None or tender_provider is None:
        await message.answer("RAG временно недоступен: проверьте настройки базы, индекса и GigaChat.")
        return
    try:
        records = await asyncio.to_thread(tender_repository.list_recent, owner, 1)
    except DatabaseError:
        await message.answer("Не удалось определить последний тендер. Попробуйте позже.")
        return
    if not records:
        await message.answer("История пуста. Сначала отправьте PDF тендера.")
        return
    record = records[0]
    try:
        indexed = await asyncio.to_thread(rag_service.has_document, owner, record.pdf_sha256)
    except QdrantStoreError:
        await message.answer("Не удалось прочитать RAG-индекс. Попробуйте позже.")
        return
    if not indexed:
        await message.answer(
            "Для последнего тендера ещё нет RAG-индекса. Отправьте этот PDF ещё раз: "
            "AI-анализ повторно расходоваться не будет, но локальный индекс будет создан.",
            parse_mode=None,
        )
        return
    await message.answer("Ищу релевантные фрагменты документа…", parse_mode=None)
    try:
        answer = await rag_service.answer(owner, record.pdf_sha256, question, tender_provider)
    except (RagError, QdrantStoreError):
        await message.answer("Не удалось выполнить поиск по документу. Попробуйте переформулировать вопрос.")
        return
    except LLMError:
        await message.answer("Не удалось сформировать ответ через GigaChat. Проверьте сеть и настройки LLM.")
        return
    for chunk in format_rag_answer(answer, record.source_filename):
        await message.answer(chunk, parse_mode=None)
