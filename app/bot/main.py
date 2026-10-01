"""Long-polling entry point with owned HTTP-session cleanup."""

import asyncio
import logging
import sys
from urllib.parse import unquote, urlsplit

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramUnauthorizedError

from .config import ConfigurationError, Settings, load_settings
from .handlers import create_router

logger = logging.getLogger(__name__)


class TokenRedactingFormatter(logging.Formatter):
    def __init__(self, token: str, proxy_url: str | None = None):
        super().__init__("%(asctime)s %(levelname)s %(name)s: %(message)s")
        self.secrets = [token]
        if proxy_url:
            parsed = urlsplit(proxy_url)
            self.secrets.extend([proxy_url, parsed.username, parsed.password,
                                 unquote(parsed.username or ""), unquote(parsed.password or "")])

    def format(self, record: logging.LogRecord) -> str:
        output = super().format(record)
        for secret in sorted((s for s in self.secrets if s), key=len, reverse=True):
            output = output.replace(secret, "[REDACTED]")
        return output


def configure_logging(settings: Settings) -> None:
    # Do not propagate vendor HTTP diagnostics (headers/payloads) to bot logs.
    for name in ("gigachat", "httpx", "httpcore"):
        vendor_logger = logging.getLogger(name)
        vendor_logger.handlers = [logging.NullHandler()]
        vendor_logger.propagate = False
    handler = logging.StreamHandler()
    handler.setFormatter(TokenRedactingFormatter(settings.token, settings.proxy_url))
    logging.basicConfig(level=settings.log_level, handlers=[handler], force=True)


def create_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.include_router(create_router())
    return dispatcher


async def run_bot(settings: Settings, tender_provider=None, tender_max_chars: int = 20000,
                  company_profile=None, tender_repository=None, rag_service=None) -> None:
    if settings.proxy_url:
        session = AiohttpSession(proxy=settings.proxy_url)
        try:
            bot = Bot(token=settings.token, session=session)
        except BaseException:
            await session.close()
            raise
    else:
        bot = Bot(token=settings.token)
    try:
        dispatcher = create_dispatcher()
        if tender_provider is not None:
            dispatcher["tender_provider"] = tender_provider
            dispatcher["tender_max_chars"] = tender_max_chars
        if company_profile is not None:
            dispatcher["company_profile"] = company_profile
        if tender_repository is not None:
            dispatcher["tender_repository"] = tender_repository
        if rag_service is not None:
            dispatcher["rag_service"] = rag_service
        await bot.get_me()  # Validate credentials before announcing successful startup.
        logger.info("TenderLens AI запущен. Остановка: Ctrl+C.")
        await dispatcher.start_polling(
            bot,
            allowed_updates=dispatcher.resolve_used_update_types(),
            handle_as_tasks=False,
            handle_signals=sys.platform != "win32",
            close_bot_session=False,
        )
    finally:
        await bot.session.close()
        logger.info("Сессия Telegram закрыта.")


def main() -> int:
    try:
        settings = load_settings()
    except ConfigurationError as error:
        print(f"Ошибка конфигурации: {error}", file=sys.stderr)
        return 2
    configure_logging(settings)
    from app.llm.config import load_settings as load_llm_settings
    from app.llm.gigachat import GigaChatProvider
    from app.llm.base import LLMConfigurationError
    from app.services.tender_analysis import configured_max_chars, AnalysisError
    provider, max_chars = None, 20000
    try:
        llm_settings = load_llm_settings()
        max_chars = configured_max_chars()
        provider = GigaChatProvider(llm_settings)
    except (LLMConfigurationError, AnalysisError):
        logger.warning("AI-анализ отключён: проверьте настройки LLM и лимит текста.")

    from app.scoring.config import ScoringConfigurationError, load_company_profile
    company_profile = None
    try:
        company_profile = load_company_profile()
    except ScoringConfigurationError:
        logger.warning("Scoring отключён: проверьте профиль компании.")

    from app.database import (DatabaseConfigurationError, DatabaseError,
                              TenderRepository, load_database_settings)
    tender_repository = None
    try:
        db_settings = load_database_settings()
        tender_repository = TenderRepository(db_settings.path)
        tender_repository.initialize()
    except (DatabaseConfigurationError, DatabaseError):
        logger.warning("История тендеров отключена: проверьте DATABASE_URL и доступ к файлу БД.")

    from app.rag import RagConfigurationError, RagError, RagService, RagStoreError, load_rag_settings
    rag_service = None
    try:
        rag_settings = load_rag_settings()
        if rag_settings.enabled:
            rag_service = RagService(rag_settings)
    except (RagConfigurationError, RagError, RagStoreError):
        logger.warning("RAG отключён: проверьте RAG_* настройки и доступ к локальному индексу.")

    try:
        asyncio.run(run_bot(settings, provider, max_chars, company_profile, tender_repository, rag_service))
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем.")
    except TelegramUnauthorizedError:
        logger.error("Telegram отклонил токен. Проверьте ключ BotFather.")
        return 1
    except Exception as error:
        # Never print exception payloads, which may contain credentials/request URLs.
        logger.error("Бот завершился с ошибкой (%s). Проверьте сеть и настройки Telegram.", type(error).__name__)
        return 1
    return 0
