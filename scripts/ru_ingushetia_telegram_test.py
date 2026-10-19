"""Real Telegram ACKs for an explicitly supplied, isolated test destination.

Never reads the application .env, production bot settings or subscriptions.
The caller must first verify live discovery and the Worker SQL snapshot.
"""
from __future__ import annotations

import asyncio

from dotenv import dotenv_values

from app.bot.monitoring import monitor_loop
from app.monitoring.repository import MonitoringRepository
from app.monitoring.service import TenderMonitorService


async def check_real_telegram(catalog, cfg, notices, db_path, test_env_file):
    from aiogram import Bot
    from aiogram.client.session.aiohttp import AiohttpSession

    settings = dotenv_values(test_env_file, interpolate=False)
    token = settings.get("INGUSHETIA_TEST_TELEGRAM_BOT_TOKEN")
    raw_chat = settings.get("INGUSHETIA_TEST_TELEGRAM_CHAT_ID")
    if not token or not raw_chat:
        raise ValueError("Dedicated Ingushetia test bot token and chat ID required")
    try:
        chat_id = int(raw_chat)
    except (ValueError, TypeError):
        raise ValueError("Dedicated Telegram test chat ID must be numeric") from None
    if not chat_id:
        raise ValueError("Dedicated Telegram test chat ID must be nonzero")

    repo = MonitoringRepository(db_path)
    repo.initialize()
    owner = 101
    repo.set_subscription(owner, chat_id, True)
    service = TenderMonitorService(cfg, None, repo, None)
    stop = asyncio.Event()
    acks = []
    expected = {notice.tender_number: notice for notice in notices}
    if len(expected) > cfg.max_notifications_per_cycle:
        raise ValueError("Test notification cap does not cover all verified notices")

    async with Bot(token=token, session=AiohttpSession(timeout=25)) as bot:
        class VerifiedTelegramSender:
            async def send_message(self, target, text, **kwargs):
                try:
                    if target != chat_id:
                        raise AssertionError("Unexpected test destination")
                    numbers = [number for number in expected if number in text]
                    if len(numbers) != 1 or expected[numbers[0]].title not in text:
                        raise AssertionError("Test message lost verified procurement identity")
                    reply = await bot.send_message(target, text, **kwargs)
                    if (reply.chat.id != chat_id or reply.message_id <= 0
                            or reply.text != text):
                        raise AssertionError("Telegram response did not confirm the exact message")
                    acks.append({"number": numbers[0], "message_id": reply.message_id})
                    if len(acks) == len(expected):
                        stop.set()
                    return reply
                except Exception:
                    # monitor_loop deliberately catches bot errors. End this
                    # acceptance cycle and fail below instead of waiting 600s.
                    stop.set()
                    raise

        await asyncio.wait_for(monitor_loop(
            VerifiedTelegramSender(), service, stop, source_catalog=catalog), timeout=90)
    if {ack["number"] for ack in acks} != set(expected) or len(acks) != len(expected):
        raise AssertionError("Telegram did not acknowledge every verified current notice")
    if not all(repo.seen(owner, "eis_44", number) for number in expected):
        raise AssertionError("Real Telegram ACKs did not survive notification persistence")
    return acks
