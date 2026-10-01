"""PDF upload handler. PDF bytes and extracted full text are not retained."""
import asyncio
import hashlib
import logging

from aiogram import Bot
from aiogram.types import Message

from app.parsers.pdf import MAX_BYTES, PdfSummary
from app.services.pdf import LimitedBuffer, summarize_pdf

logger = logging.getLogger(__name__)

STATUS = {
    "ok": "Да, текст извлечён.",
    "no_text": "PDF открыт, но текст не найден. Возможно, это скан: требуется OCR (пока не подключён).",
    "encrypted": "Нет: PDF защищён паролем.",
    "invalid": "Нет: файл не является читаемым PDF или повреждён.",
    "too_large": "Нет: файл превышает лимит 10 МиБ.",
    "too_many_pages": "Нет: больше 200 страниц.",
    "too_much_text": "Нет: превышен лимит 2 000 000 символов; обработка остановлена.",
    "timeout": "Нет: превышено время обработки.",
    "download_error": "Нет: не удалось скачать файл. Попробуйте отправить его позже.",
}


def format_summary(name: str, result: PdfSummary) -> str:
    safe_name = "".join(c for c in name if c.isprintable())[:200] or "document.pdf"
    pages = str(result.pages) if result.pages is not None else "не определено"
    text = (f"Файл: {safe_name}\nСтраниц: {pages}\n"
            f"Извлечено символов: {result.characters}\n"
            f"Результат чтения: {STATUS[result.status]}")
    if result.status == "ok" and result.empty_pages:
        text += f"\nСтраниц без текста: {result.empty_pages}. Их содержимое не распознано."
    return text


def _identity(message: Message) -> tuple[int | None, int | None]:
    user_id = getattr(getattr(message, "from_user", None), "id", None)
    chat_id = getattr(getattr(message, "chat", None), "id", None)
    user_id = user_id if isinstance(user_id, int) and not isinstance(user_id, bool) else None
    chat_id = chat_id if isinstance(chat_id, int) and not isinstance(chat_id, bool) else None
    return user_id, chat_id


async def _send_stored(message: Message, record) -> None:
    from app.services.tender_analysis import AnalysisResult
    from .tender import format_tender

    await message.answer(
        "♻️ Этот PDF уже был обработан ранее. Новый запрос к AI не выполнялся.\n"
        f"Сохранённая запись: #{record.id}",
        parse_mode=None,
    )
    result = AnalysisResult(record.analysis, record.analysis_truncated)
    for chunk in format_tender(result):
        await message.answer(chunk, parse_mode=None)
    if record.scoring is not None:
        from .scoring import format_scoring
        for chunk in format_scoring(record.scoring):
            await message.answer(chunk, parse_mode=None)


async def pdf_handler(message: Message, bot: Bot, tender_provider=None, tender_max_chars: int = 20000,
                      company_profile=None, tender_repository=None) -> None:
    document = message.document
    if document is None:
        return
    name = document.file_name or "document.pdf"
    if document.mime_type != "application/pdf" and not name.lower().endswith(".pdf"):
        await message.answer("Отправьте PDF как файл (документ). Другие форматы пока не поддерживаются.")
        return
    if document.file_size is not None and document.file_size > MAX_BYTES:
        result = PdfSummary("too_large")
        data = None
        pdf_hash = None
    else:
        await message.answer("Получен PDF. Скачиваю и проверяю документ…")
        with LimitedBuffer() as buffer:
            try:
                await asyncio.wait_for(bot.download(document, destination=buffer, timeout=60), timeout=65)
            except ValueError:
                result = PdfSummary("too_large")
                data = None
                pdf_hash = None
            except TimeoutError:
                result = PdfSummary("download_error")
                data = None
                pdf_hash = None
            except Exception:
                result = PdfSummary("download_error")
                data = None
                pdf_hash = None
            else:
                data = buffer.getvalue()
                pdf_hash = hashlib.sha256(data).hexdigest()
                owner_id, _ = _identity(message)
                if tender_repository is not None and owner_id is not None:
                    try:
                        existing = await asyncio.to_thread(tender_repository.find_by_hash, owner_id, pdf_hash)
                    except Exception as error:
                        existing = None
                        logger.warning("Не удалось проверить PDF на дубликат (%s).", type(error).__name__)
                    if existing is not None:
                        await _send_stored(message, existing)
                        return
                try:
                    result = await summarize_pdf(data)
                except Exception:
                    result = PdfSummary("invalid")
    summary = format_summary(name, result)
    if result.status == "ok" and tender_provider is None:
        summary += "\nAI-анализ не настроен. Администратору нужно проверить конфигурацию GigaChat."
    await message.answer(summary, parse_mode=None)

    if result.status != "ok" or tender_provider is None:
        return
    await message.answer("Документ успешно прочитан.\nНачинаю AI-анализ тендерной документации…")
    from app.llm.base import LLMError
    from app.services.tender_analysis import AnalysisError, analyze_tender
    from .tender import format_tender
    try:
        analysis = await analyze_tender(result.text, tender_provider, tender_max_chars)
    except LLMError:
        await message.answer("AI-анализ недоступен: ошибка подключения, авторизации или времени ожидания. Администратору нужно проверить настройки GigaChat. PDF прочитан успешно.")
        return
    except AnalysisError as error:
        await message.answer(str(error), parse_mode=None)
        return
    for chunk in format_tender(analysis):
        await message.answer(chunk, parse_mode=None)

    scoring = None
    if company_profile is not None:
        from app.scoring.engine import score_tender
        from .scoring import format_scoring
        scoring = score_tender(analysis.analysis, company_profile)
        for chunk in format_scoring(scoring):
            await message.answer(chunk, parse_mode=None)

    owner_id, chat_id = _identity(message)
    if (tender_repository is not None and owner_id is not None and chat_id is not None
            and pdf_hash is not None):
        try:
            stored = await asyncio.to_thread(
                tender_repository.save_success,
                owner_user_id=owner_id,
                chat_id=chat_id,
                pdf_sha256=pdf_hash,
                source_filename=name,
                pages=result.pages,
                characters=result.characters,
                analysis=analysis.analysis,
                scoring=scoring,
                analysis_truncated=analysis.truncated,
            )
            await message.answer(f"💾 Результат сохранён в истории под номером #{stored.id}.", parse_mode=None)
        except Exception as error:
            logger.warning("Не удалось сохранить результат в БД (%s).", type(error).__name__)
