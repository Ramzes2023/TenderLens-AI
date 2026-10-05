import asyncio
import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram import Bot
from aiogram.types import Update, User

from app.bot.config import ConfigurationError, Settings, load_settings
from app.bot.handlers import HELP_TEXT, START_TEXT, STATUS_TEXT
from app.bot.main import TokenRedactingFormatter, create_dispatcher, main, run_bot

# Synthetic test value; never used against Telegram.
TOKEN = "123456789:" + "X" * 35


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env_file = Path(self.tmp.name) / ".env"
        self.env_patch = patch.dict(os.environ, {}, clear=True)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def test_missing_and_blank_token(self):
        for token in ("", "   "):
            os.environ["TELEGRAM_BOT_TOKEN"] = token
            with self.assertRaisesRegex(ConfigurationError, "Не задан TELEGRAM_BOT_TOKEN"):
                load_settings(self.env_file)

    def test_invalid_token_is_not_disclosed(self):
        os.environ["TELEGRAM_BOT_TOKEN"] = "private-invalid-value"
        with self.assertRaises(ConfigurationError) as error:
            load_settings(self.env_file)
        self.assertNotIn("private-invalid-value", str(error.exception))

    def test_dotenv_and_environment_precedence(self):
        self.env_file.write_text(f"TELEGRAM_BOT_TOKEN={TOKEN}\nLOG_LEVEL=WARNING\n", encoding="utf-8-sig")
        self.assertEqual(load_settings(self.env_file).token, TOKEN)
        os.environ["TELEGRAM_BOT_TOKEN"] = "987654321:" + "Y" * 35
        self.assertTrue(load_settings(self.env_file).token.startswith("987654321:"))
        self.assertNotIn(TOKEN, repr(Settings(TOKEN)))

    def test_invalid_log_level(self):
        os.environ.update(TELEGRAM_BOT_TOKEN=TOKEN, LOG_LEVEL="INVALID")
        with self.assertRaisesRegex(ConfigurationError, "LOG_LEVEL"):
            load_settings(self.env_file)

    def test_optional_proxy_configuration(self):
        os.environ["TELEGRAM_BOT_TOKEN"] = TOKEN
        self.assertIsNone(load_settings(self.env_file).proxy_url)
        os.environ["TELEGRAM_PROXY_URL"] = "   "
        self.assertIsNone(load_settings(self.env_file).proxy_url)
        proxy = "http://test-user:test-password@localhost:8080"
        os.environ["TELEGRAM_PROXY_URL"] = proxy
        settings = load_settings(self.env_file)
        self.assertEqual(settings.proxy_url, proxy)
        self.assertNotIn("test-password", repr(settings))

    def test_invalid_proxy_does_not_disclose_credentials(self):
        os.environ.update(TELEGRAM_BOT_TOKEN=TOKEN, TELEGRAM_PROXY_URL="http://private-user:private-pass@localhost:bad")
        with self.assertRaises(ConfigurationError) as error:
            load_settings(self.env_file)
        self.assertNotIn("private-pass", str(error.exception))

    def test_proxy_credentials_redacted(self):
        proxy = "http://test-user:secret%21value@localhost:8080"
        record = logging.LogRecord("test", logging.ERROR, "", 0,
                                   "%s secret!value secret%%21value test-user", (proxy,), None)
        output = TokenRedactingFormatter(TOKEN, proxy).format(record)
        for secret in (proxy, "test-user", "secret!value", "secret%21value"):
            self.assertNotIn(secret, output)

    def test_missing_configuration_exits_before_polling(self):
        with patch("app.bot.main.load_settings", side_effect=ConfigurationError("Не задан TELEGRAM_BOT_TOKEN")), patch("app.bot.main.asyncio.run") as runner, patch("sys.stderr"):
            self.assertEqual(main(), 2)
            runner.assert_not_called()

    def test_log_formatter_redacts_token(self):
        record = logging.LogRecord("test", logging.ERROR, "", 0, "URL=%s", (TOKEN,), None)
        output = TokenRedactingFormatter(TOKEN).format(record)
        self.assertNotIn(TOKEN, output)
        self.assertIn("[REDACTED]", output)


class RoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_commands_through_dispatcher_without_network(self):
        bot = Bot(TOKEN)
        self.addAsyncCleanup(bot.session.close)
        bot.get_me = AsyncMock(return_value=User(id=123456789, is_bot=True, first_name="Test", username="TenderLensTestBot"))
        bot.session.make_request = AsyncMock(return_value=True)
        dispatcher = create_dispatcher()
        cases = [("/start", START_TEXT), ("/help", HELP_TEXT), ("/status", STATUS_TEXT),
                 ("/status@TenderLensTestBot", STATUS_TEXT), ("/unknown", None),
                 ("обычный текст", None)]
        for index, (command, expected) in enumerate(cases):
            with self.subTest(command=command):
                bot.session.make_request.reset_mock()
                update = Update.model_validate({"update_id": index, "message": {
                    "message_id": index + 1, "date": 0,
                    "chat": {"id": 42, "type": "private"},
                    "from": {"id": 42, "is_bot": False, "first_name": "Test"},
                    "text": command,
                    "entities": [{"type": "bot_command", "offset": 0, "length": len(command)}] if command.startswith("/") else [],
                }})
                await dispatcher.feed_update(bot, update)
                if expected is None:
                    bot.session.make_request.assert_not_awaited()
                else:
                    bot.session.make_request.assert_awaited_once()
                    method = bot.session.make_request.call_args.args[1]
                    self.assertEqual(method.text, expected)
                    self.assertEqual(method.chat_id, 42)
        self.assertEqual(STATUS_TEXT, "VALYQON AI is running.")


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_global_discovery_service_is_injected_without_background_monitoring(self):
        bot = MagicMock()
        bot.get_me = AsyncMock()
        bot.session.close = AsyncMock()

        dispatcher = MagicMock()
        dispatcher.resolve_used_update_types.return_value = [
            "message"
        ]
        dispatcher.start_polling = AsyncMock()

        discovery_service = MagicMock()
        source_catalog = MagicMock()

        with (
            patch(
                "app.bot.main.Bot",
                return_value=bot,
            ),
            patch(
                "app.bot.main.create_dispatcher",
                return_value=dispatcher,
            ),
        ):
            await run_bot(
                Settings(TOKEN),
                monitoring_service=None,
                source_catalog=source_catalog,
                tender_discovery_service=discovery_service,
            )

        dispatcher.__setitem__.assert_any_call(
            "source_catalog",
            source_catalog,
        )

        dispatcher.__setitem__.assert_any_call(
            "tender_discovery_service",
            discovery_service,
        )

        monitoring_injections = [
            call
            for call
            in dispatcher.__setitem__.call_args_list
            if call.args
            and call.args[0]
            == "monitoring_service"
        ]

        self.assertEqual(
            monitoring_injections,
            [],
        )

        dispatcher.start_polling.assert_awaited_once()
        bot.session.close.assert_awaited_once()

    async def test_direct_and_proxy_bot_construction(self):
        for proxy in (None, "http://localhost:8080"):
            with self.subTest(proxy_enabled=bool(proxy)):
                bot = MagicMock()
                bot.get_me = AsyncMock()
                bot.session.close = AsyncMock()
                dispatcher = MagicMock()
                dispatcher.start_polling = AsyncMock()
                with patch("app.bot.main.Bot", return_value=bot) as factory, patch("app.bot.main.AiohttpSession") as session, patch("app.bot.main.create_dispatcher", return_value=dispatcher):
                    await run_bot(Settings(TOKEN, proxy_url=proxy))
                    if proxy:
                        session.assert_called_once_with(proxy=proxy)
                        factory.assert_called_once_with(token=TOKEN, session=session.return_value)
                    else:
                        session.assert_not_called()
                        factory.assert_called_once_with(token=TOKEN)
                bot.session.close.assert_awaited_once()

    async def test_real_proxy_session_can_be_constructed_without_network(self):
        from aiogram.client.session.aiohttp import AiohttpSession
        session = AiohttpSession(proxy="http://localhost:8080")
        await session.close()

    async def test_session_closed_after_success_failure_and_cancel(self):
        for failure in (None, RuntimeError("offline"), asyncio.CancelledError()):
            with self.subTest(failure=type(failure).__name__):
                bot = MagicMock()
                bot.get_me = AsyncMock()
                bot.session.close = AsyncMock()
                dispatcher = MagicMock()
                dispatcher.resolve_used_update_types.return_value = ["message"]
                dispatcher.start_polling = AsyncMock(side_effect=failure)
                with patch("app.bot.main.Bot", return_value=bot), patch("app.bot.main.create_dispatcher", return_value=dispatcher):
                    if failure is None:
                        await run_bot(Settings(TOKEN))
                    else:
                        with self.assertRaises(type(failure)):
                            await run_bot(Settings(TOKEN))
                bot.session.close.assert_awaited_once()
                self.assertFalse(dispatcher.start_polling.call_args.kwargs["close_bot_session"])

    async def test_session_closed_when_startup_fails(self):
        bot = MagicMock()
        bot.get_me = AsyncMock(side_effect=RuntimeError("startup failure"))
        bot.session.close = AsyncMock()
        with patch("app.bot.main.Bot", return_value=bot), self.assertRaises(RuntimeError):
            await run_bot(Settings(TOKEN))
        bot.session.close.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
