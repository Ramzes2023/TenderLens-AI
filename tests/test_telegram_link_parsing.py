import unittest
from types import SimpleNamespace

from app.bot.linking import command_link_token, start_link_token, telegram_owner


class TelegramLinkParsingTests(unittest.TestCase):
    @staticmethod
    def message(text: str, owner=1844282717):
        return SimpleNamespace(text=text, from_user=SimpleNamespace(id=owner))

    def test_start_deep_link_token(self):
        self.assertEqual(
            start_link_token(self.message("/start link_abc123")),
            "abc123",
        )
        self.assertIsNone(start_link_token(self.message("/start")))

    def test_link_command_token(self):
        self.assertEqual(
            command_link_token(self.message("/link abc123")),
            "abc123",
        )
        self.assertIsNone(command_link_token(self.message("/link")))

    def test_owner(self):
        self.assertEqual(telegram_owner(self.message("/start")), 1844282717)


if __name__ == "__main__":
    unittest.main()
