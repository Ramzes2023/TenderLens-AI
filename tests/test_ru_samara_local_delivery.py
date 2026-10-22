"""Offline checks for local error injection. No real-source evidence or network."""
import asyncio

import pytest

from scripts.ci_ru_samara_telegram_query_delivery import LocalCaptureBot, SOURCE


def test_local_capture_distinguishes_attempt_from_confirmed_delivery():
    async def scenario():
        text = "🆕 НОВАЯ ЗАКУПКА\nИсточник: " + SOURCE + "\nЦена: 100 RUB"
        stop = asyncio.Event()
        failed = LocalCaptureBot(stop, fail_delivery=True)
        with pytest.raises(ConnectionError):
            await failed.send_message(99001, text, disable_web_page_preview=True)
        assert stop.is_set() and failed.attempted == [text] and failed.delivered == []
        successful = LocalCaptureBot(asyncio.Event())
        receipt = await successful.send_message(99001, text, disable_web_page_preview=True)
        assert receipt.message_id == 1
        assert receipt.chat.id == 99001
        assert successful.delivered == [text]
        # The exact same production monitor ACK gate must accept the
        # local-only synthetic receipt, not merely a non-raising coroutine.
        from app.bot.monitoring import _require_telegram_delivery_ack
        _require_telegram_delivery_ack(receipt, 99001)
        with pytest.raises(ValueError):
            _require_telegram_delivery_ack(receipt, 99002)
        with pytest.raises(AssertionError):
            await successful.send_message(99002, text, disable_web_page_preview=True)
    asyncio.run(scenario())
