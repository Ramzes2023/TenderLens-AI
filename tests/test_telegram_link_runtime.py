import unittest
from unittest.mock import AsyncMock, MagicMock

from aiogram import Bot
from aiogram.types import Update, User

from app.bot.handlers import START_TEXT
from app.bot.main import create_dispatcher


TOKEN = "123456789:" + "X" * 35


class TelegramLinkRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = Bot(token=TOKEN)
        self.addAsyncCleanup(self.bot.session.close)
        self.bot.get_me = AsyncMock(
            return_value=User(
                id=123456789,
                is_bot=True,
                first_name="Test",
                username="TenderLensTestBot",
            )
        )
        self.bot.session.make_request = AsyncMock(return_value=True)
        self.auth_service = MagicMock()
        self.auth_service.consume_telegram_link.return_value = object()
        self.dispatcher = create_dispatcher()
        self.dispatcher["auth_service"] = self.auth_service

    @staticmethod
    def update(text: str, update_id: int = 1) -> Update:
        command = text.split(maxsplit=1)[0]
        return Update.model_validate(
            {
                "update_id": update_id,
                "message": {
                    "message_id": update_id,
                    "date": 0,
                    "chat": {"id": 42, "type": "private"},
                    "from": {
                        "id": 1844282717,
                        "is_bot": False,
                        "first_name": "Ramzes",
                    },
                    "text": text,
                    "entities": [
                        {
                            "type": "bot_command",
                            "offset": 0,
                            "length": len(command),
                        }
                    ],
                },
            }
        )

    async def test_start_deep_link_redeems_token(self):
        await self.dispatcher.feed_update(
            self.bot,
            self.update("/start link_test-token", update_id=1),
        )
        self.auth_service.consume_telegram_link.assert_called_once_with(
            "test-token",
            1844282717,
        )

    async def test_link_command_redeems_token(self):
        await self.dispatcher.feed_update(
            self.bot,
            self.update("/link test-token", update_id=2),
        )
        self.auth_service.consume_telegram_link.assert_called_once_with(
            "test-token",
            1844282717,
        )

    async def test_plain_start_keeps_existing_start_flow(self):
        await self.dispatcher.feed_update(
            self.bot,
            self.update("/start", update_id=3),
        )
        self.auth_service.consume_telegram_link.assert_not_called()
        request = self.bot.session.make_request.call_args.args[1]
        self.assertEqual(request.text, START_TEXT)

    async def test_link_without_token_does_not_redeem(self):
        await self.dispatcher.feed_update(
            self.bot,
            self.update("/link", update_id=4),
        )
        self.auth_service.consume_telegram_link.assert_not_called()


if __name__ == "__main__":
    unittest.main()
