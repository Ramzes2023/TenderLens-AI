"""Phase 2 command handlers; no tender analysis is implemented yet."""

from aiogram import F, Router
from .documents import pdf_handler
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

START_TEXT = (
    "Здравствуйте! TenderLens AI — система мониторинга тендеров и анализа "
    "тендерной документации с применением искусственного интеллекта.\n\n"
    "Отправьте PDF: я сообщу число страниц и объём извлечённого текста. "
    "Мониторинг и AI-анализ пока не подключены.\nИспользуйте /help для списка команд."
)
HELP_TEXT = (
    "Доступные команды:\n/start — знакомство с TenderLens AI\n"
    "/help — список команд\n/status — проверка работы бота\n\n"
    "Отправьте PDF как документ: до 10 МиБ и 200 страниц. "
    "Покажу имя, страницы и количество символов. OCR и AI-анализ пока недоступны."
)
STATUS_TEXT = "TenderLens AI is running."


async def start_handler(message: Message) -> None:
    await message.answer(START_TEXT)


async def help_handler(message: Message) -> None:
    await message.answer(HELP_TEXT)


async def status_handler(message: Message) -> None:
    await message.answer(STATUS_TEXT)


def create_router() -> Router:
    router = Router(name="commands")
    router.message.register(start_handler, CommandStart())
    router.message.register(help_handler, Command("help"))
    router.message.register(status_handler, Command("status"))
    router.message.register(pdf_handler, F.document)
    return router
