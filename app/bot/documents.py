"""PDF upload handler. Files and extracted text are not logged or retained."""
import asyncio
from aiogram import Bot
from aiogram.types import Message
from app.parsers.pdf import MAX_BYTES, PdfSummary
from app.services.pdf import LimitedBuffer, summarize_pdf

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


async def pdf_handler(message: Message, bot: Bot) -> None:
    document = message.document
    if document is None:
        return
    name = document.file_name or "document.pdf"
    if document.mime_type != "application/pdf" and not name.lower().endswith(".pdf"):
        await message.answer("Отправьте PDF как файл (документ). Другие форматы пока не поддерживаются.")
        return
    if document.file_size is not None and document.file_size > MAX_BYTES:
        result = PdfSummary("too_large")
    else:
        await message.answer("Получен PDF. Скачиваю и проверяю документ…")
        with LimitedBuffer() as buffer:
            try:
                await asyncio.wait_for(bot.download(document, destination=buffer, timeout=60), timeout=65)
            except ValueError:
                result = PdfSummary("too_large")
            except TimeoutError:
                result = PdfSummary("download_error")
            except Exception:
                result = PdfSummary("download_error")
            else:
                try:
                    result = await summarize_pdf(buffer.getvalue())
                except Exception:
                    result = PdfSummary("invalid")
    await message.answer(format_summary(name, result), parse_mode=None)
