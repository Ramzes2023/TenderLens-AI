"""Secure Telegram confirmation helpers for linking a web account."""

from __future__ import annotations

import asyncio

from aiogram.types import Message

from app.auth import AuthService, TelegramLinkError


def start_link_token(message: Message) -> str | None:
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) != 2 or not parts[1].startswith("link_"):
        return None
    token = parts[1][len("link_"):].strip()
    return token or None


def command_link_token(message: Message) -> str | None:
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) != 2:
        return None
    return parts[1].strip() or None


def telegram_owner(message: Message) -> int | None:
    value = getattr(getattr(message, "from_user", None), "id", None)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


async def redeem_link(
    message: Message,
    token: str | None,
    auth_service: AuthService | None,
) -> bool:
    if token is None:
        return False
    if auth_service is None:
        await message.answer(
            "Связь с веб-аккаунтом временно недоступна. Попробуйте позже."
        )
        return True

    owner = telegram_owner(message)
    if owner is None:
        await message.answer("Не удалось определить Telegram-пользователя.")
        return True

    try:
        await asyncio.to_thread(auth_service.consume_telegram_link, token, owner)
    except TelegramLinkError:
        await message.answer(
            "Ссылка недействительна, истекла или уже использована. "
            "Создайте новую ссылку в VALYQON AI Web."
        )
        return True

    await message.answer(
        "✅ Telegram успешно подключён к VALYQON AI Web. "
        "Теперь сайт и бот используют один профиль владельца."
    )
    return True
