"""Telegram commands and PDF entry point for analysis/scoring."""

from aiogram import F, Router
from .documents import pdf_handler
from .history import history_handler
from .rag import ask_handler
from .monitoring import (monitor_off_handler, monitor_on_handler, monitor_status_handler,
                         tenders_handler)
from .companies import (companies_handler, company_add_handler, company_show_handler,
                        company_use_handler)
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

START_TEXT = (
    "Здравствуйте! TenderLens AI — система мониторинга тендеров и анализа "
    "тендерной документации с применением искусственного интеллекта.\n\n"
    "Отправьте PDF: я сообщу число страниц и объём извлечённого текста. "
    "При настроенном GigaChat текст отправляется в AI для извлечения фактов, затем Python сравнивает результат с профилем компании по прозрачным правилам. "
    "Система также читает настроенные RSS-ленты ЕИС и присылает новые подходящие закупки.\nИспользуйте /help для списка команд."
)
HELP_TEXT = (
    "Доступные команды:\n/start — знакомство с TenderLens AI\n"
    "/help — список команд\n/status — проверка работы бота\n/history — последние обработанные тендеры\n/ask <вопрос> — вопрос по последнему PDF через RAG\n"
    "/tenders — проверить новые закупки из настроенных RSS ЕИС\n"
    "/monitor_on — включить автоуведомления о новых закупках\n"
    "/monitor_off — выключить автоуведомления\n"
    "/monitor_status — статус мониторинга\n"
    "/companies — список профилей компаний\n/company_show — активная компания\n"
    "/company_add ... — создать профиль компании\n/company_use <id> — переключить активную компанию\n\n"
    "Отправьте PDF как документ: до 10 МиБ и 200 страниц. "
    "Покажу имя, страницы и количество символов. Текст читаемого PDF отправляется в GigaChat для AI-сводки; затем доступен детерминированный fit-score по профилю компании. OCR недоступен."
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
    router.message.register(history_handler, Command("history"))
    router.message.register(ask_handler, Command("ask"))
    router.message.register(tenders_handler, Command("tenders"))
    router.message.register(monitor_on_handler, Command("monitor_on"))
    router.message.register(monitor_off_handler, Command("monitor_off"))
    router.message.register(monitor_status_handler, Command("monitor_status"))
    router.message.register(companies_handler, Command("companies"))
    router.message.register(company_show_handler, Command("company_show"))
    router.message.register(company_add_handler, Command("company_add"))
    router.message.register(company_use_handler, Command("company_use"))
    router.message.register(pdf_handler, F.document)
    return router
