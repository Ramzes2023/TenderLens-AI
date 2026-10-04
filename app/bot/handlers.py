"""Telegram commands and PDF entry point for analysis/scoring."""

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from .companies import (
    CompanyDelete,
    CompanyEdit,
    CompanySetup,
    companies_handler,
    company_add_handler,
    company_delete_confirm_handler,
    company_delete_handler,
    company_edit_budget_handler,
    company_edit_confirm_handler,
    company_edit_handler,
    company_edit_keywords_handler,
    company_edit_mode_handler,
    company_edit_name_handler,
    company_edit_regions_handler,
    company_setup_budget_handler,
    company_setup_cancel_handler,
    company_setup_confirm_handler,
    company_setup_handler,
    company_setup_keywords_handler,
    company_setup_mode_handler,
    company_setup_name_handler,
    company_setup_regions_handler,
    company_show_handler,
    company_use_callback_handler,
    company_use_handler,
)
from .documents import pdf_handler
from .history import history_handler
from .linking import command_link_token, redeem_link, start_link_token
from .monitoring import (
    monitor_off_handler,
    monitor_on_handler,
    monitor_status_handler,
    tenders_handler,
)
from .rag import ask_handler

START_TEXT = (
    "Здравствуйте! VALYQON AI — система мониторинга тендеров и анализа "
    "тендерной документации с применением искусственного интеллекта.\n\n"
    "Создать персональный профиль компании можно пошагово через /company_setup. "
    "Управлять профилями можно через /companies, /company_edit и /company_delete. "
    "После этого мониторинг и scoring будут работать по активному профилю.\n\n"
    "Отправьте PDF: я сообщу число страниц и объём извлечённого текста. "
    "При настроенном GigaChat текст отправляется в AI для извлечения фактов, затем Python сравнивает результат с профилем компании по прозрачным правилам. "
    "Система также читает настроенные RSS-ленты ЕИС и присылает новые подходящие закупки.\nИспользуйте /help для списка команд."
)
HELP_TEXT = (
    "Доступные команды:\n/start — знакомство с VALYQON AI\n"
    "/link <код> — подключить Telegram к VALYQON AI Web\n"
    "/help — список команд\n/status — проверка работы бота\n/history — последние обработанные тендеры\n/ask <вопрос> — вопрос по последнему PDF через RAG\n"
    "/tenders — проверить новые закупки из настроенных RSS ЕИС\n"
    "/monitor_on — включить автоуведомления о новых закупках\n"
    "/monitor_off — выключить автоуведомления\n"
    "/monitor_status — статус мониторинга\n"
    "/companies — список компаний и кнопки переключения\n/company_show — активная компания\n"
    "/company_setup — пошагово создать профиль компании\n"
    "/company_edit [id] — изменить активную или указанную компанию\n"
    "/company_delete [id] — безопасно удалить активную или указанную компанию\n"
    "/company_cancel — отменить текущую операцию с компанией\n"
    "/company_add ... — быстрый технический формат создания\n"
    "/company_use [id] — переключить активную компанию; без id покажет кнопки\n\n"
    "Отправьте PDF как документ: до 10 МиБ и 200 страниц. "
    "Покажу имя, страницы и количество символов. Текст читаемого PDF отправляется в GigaChat для AI-сводки; затем доступен детерминированный fit-score по профилю компании. OCR недоступен."
)
STATUS_TEXT = "VALYQON AI is running."


async def start_handler(message: Message, auth_service=None) -> None:
    token = start_link_token(message)
    if token is not None and await redeem_link(message, token, auth_service):
        return
    await message.answer(START_TEXT)


async def link_handler(message: Message, auth_service=None) -> None:
    token = command_link_token(message)
    if token is None:
        await message.answer("Использование: /link <код>.")
        return
    await redeem_link(message, token, auth_service)


async def help_handler(message: Message) -> None:
    await message.answer(HELP_TEXT)


async def status_handler(message: Message) -> None:
    await message.answer(STATUS_TEXT)


def create_router() -> Router:
    router = Router(name="commands")
    router.message.register(start_handler, CommandStart())
    router.message.register(link_handler, Command("link"))
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
    router.message.register(company_setup_handler, Command("company_setup"))
    router.message.register(company_edit_handler, Command("company_edit"))
    router.message.register(company_delete_handler, Command("company_delete"))
    router.message.register(company_setup_cancel_handler, Command("company_cancel"))
    router.message.register(company_add_handler, Command("company_add"))
    router.message.register(company_use_handler, Command("company_use"))

    router.callback_query.register(company_use_callback_handler, F.data.startswith("company_use:"))

    # FSM handlers must be registered after explicit commands so /company_cancel wins.
    router.message.register(company_setup_name_handler, CompanySetup.name)
    router.message.register(company_setup_mode_handler, CompanySetup.mode)
    router.message.register(company_setup_keywords_handler, CompanySetup.keywords)
    router.message.register(company_setup_regions_handler, CompanySetup.regions)
    router.message.register(company_setup_budget_handler, CompanySetup.budget)
    router.message.register(company_setup_confirm_handler, CompanySetup.confirm)

    router.message.register(company_edit_name_handler, CompanyEdit.name)
    router.message.register(company_edit_mode_handler, CompanyEdit.mode)
    router.message.register(company_edit_keywords_handler, CompanyEdit.keywords)
    router.message.register(company_edit_regions_handler, CompanyEdit.regions)
    router.message.register(company_edit_budget_handler, CompanyEdit.budget)
    router.message.register(company_edit_confirm_handler, CompanyEdit.confirm)

    router.message.register(company_delete_confirm_handler, CompanyDelete.confirm)

    router.message.register(pdf_handler, F.document)
    return router
