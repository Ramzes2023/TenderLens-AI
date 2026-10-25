"""Explicit one-message Bot API transport test; never loads application config.

No network by default. Requires separate TEST_* configuration AND --send AND
confirmation of the numeric test chat. No production DB/subscriptions or retry.
This synthetic diagnostic is not evidence of live procurement acquisition.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field
import json
import os
import re
import uuid

import httpx


class TestDeliveryError(RuntimeError):
    __test__ = False


@dataclass(frozen=True)
class TestConfig:
    __test__ = False
    token: str = field(repr=False)
    bot_id: int
    chat_id: int


def load_config(env, *, send=False, confirmed_chat=None):
    if not send or env.get("TEST_TELEGRAM_SEND_AUTHORIZED") != "YES_TEST_CHAT_ONLY":
        raise TestDeliveryError("Explicit test-send authorization required")
    token = env.get("TEST_TELEGRAM_BOT_TOKEN", "")
    bot = env.get("TEST_TELEGRAM_BOT_ID", "")
    chat = env.get("TEST_TELEGRAM_CHAT_ID", "")
    if (not re.fullmatch(r"[1-9][0-9]{0,15}:[A-Za-z0-9_-]{30,100}", token)
            or not re.fullmatch(r"[1-9][0-9]{0,15}", bot)
            or not re.fullmatch(r"-?[1-9][0-9]{0,15}", chat)
            or token.split(":", 1)[0] != bot
            or confirmed_chat != chat):
        raise TestDeliveryError("Dedicated test bot and confirmed numeric test chat required")
    # Never fall back to the production names, even if they happen to exist.
    return TestConfig(token, int(bot), int(chat))


async def deliver(config, *, transport=None):
    marker = "VALYQON-INGUSHETIA-TEST-" + uuid.uuid4().hex[:12]
    text = ("VALYQON AI / Ингушетия — ТЕСТ доставки.\n"
            "Диагностическое сообщение, не новая закупка.\n" + marker)
    phase = "preflight"
    try:
        async with httpx.AsyncClient(
            verify=True, trust_env=False, follow_redirects=False,
            timeout=15, transport=transport,
        ) as client:
            async def call(method, payload):
                response = await client.post(
                    "https://api.telegram.org/bot" + config.token + "/" + method,
                    json=payload,
                )
                response.raise_for_status()
                body = response.json()
                if not isinstance(body, dict) or body.get("ok") is not True or not isinstance(body.get("result"), dict):
                    raise TestDeliveryError("Bot API did not acknowledge request")
                return body["result"]

            bot = await call("getMe", {})
            if type(bot.get("id")) is not int or bot["id"] != config.bot_id or bot.get("is_bot") is not True:
                raise TestDeliveryError("Unexpected test bot identity")
            chat = await call("getChat", {"chat_id": config.chat_id})
            if (type(chat.get("id")) is not int or chat["id"] != config.chat_id
                    or chat.get("type") not in {"private", "group", "supergroup"}):
                raise TestDeliveryError("Unexpected test chat identity or type")
            phase = "send_attempted"
            message = await call("sendMessage", {
                "chat_id": config.chat_id, "text": text,
                "disable_notification": True,
                "link_preview_options": {"is_disabled": True},
            })
            if (type(message.get("message_id")) is not int or message["message_id"] <= 0
                    or message.get("chat", {}).get("id") != config.chat_id
                    or message.get("text") != text):
                raise TestDeliveryError("Unexpected test message acknowledgement")
            return {"state": "BOT_API_ACKNOWLEDGED", "message_id": message["message_id"],
                    "test_chat_matches": True, "test_bot_matches": True, "marker": marker,
                    "recipient_confirmation": "PENDING", "live_procurement_proven": False}
    except Exception:
        # httpx errors include the token-bearing request URL. Never print them.
        # A timeout after send may already have delivered; do not retry blindly.
        raise TestDeliveryError("Test delivery blocked; phase=" + phase + "; no automatic retry") from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--confirm-test-chat")
    args = parser.parse_args(argv)
    if not args.send:
        print("TEST_TELEGRAM_DELIVERY=NOT_REQUESTED; NETWORK_REQUESTS=0")
        return 0
    try:
        config = load_config(os.environ, send=args.send, confirmed_chat=args.confirm_test_chat)
        result = asyncio.run(deliver(config))
    except TestDeliveryError as error:
        print("TEST_TELEGRAM_DELIVERY=BLOCKED; " + str(error))
        return 2
    print("TEST_TELEGRAM_RECEIPT=" + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
