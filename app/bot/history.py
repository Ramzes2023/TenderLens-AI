"""User-scoped tender history rendering."""
from __future__ import annotations

import asyncio
from datetime import datetime

from aiogram.types import Message

from app.database.repository import DatabaseError, TenderRepository
from app.companies import CompanyRepositoryError
from .tender import split_messages


def _owner_id(message: Message) -> int | None:
    value = getattr(getattr(message, "from_user", None), "id", None)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def format_history(records, profile=None) -> list[str]:
    if not records:
        return ["История пока пуста. Отправьте PDF тендера для анализа."]
    lines = ["🗂 ПОСЛЕДНИЕ ТЕНДЕРЫ"]
    for item in records:
        title = item.analysis.title or item.analysis.procurement_object or item.source_filename
        scoring = item.scoring
        if profile is not None:
            try:
                from app.scoring.engine import score_tender
                scoring = score_tender(item.analysis, profile)
            except Exception:
                pass
        score = (f" — {scoring.fit_score:g}/100" if scoring and scoring.fit_score is not None else "")
        try:
            stamp = datetime.fromisoformat(item.updated_at).strftime("%d.%m.%Y %H:%M")
        except ValueError:
            stamp = item.updated_at[:16]
        lines.append(f"#{item.id} · {stamp}{score}\n{title}")
    lines.append("Повторная отправка того же PDF не расходует новый AI-запрос: сохранённый результат используется повторно.")
    return split_messages("\n\n".join(lines))


async def history_handler(message: Message, tender_repository: TenderRepository | None = None,
                          company_service=None) -> None:
    owner = _owner_id(message)
    if tender_repository is None:
        await message.answer("История временно недоступна: локальная база данных не настроена.")
        return
    if owner is None:
        await message.answer("Не удалось определить пользователя для истории.")
        return
    try:
        records = await asyncio.to_thread(tender_repository.list_recent, owner, 10)
        profile = (await asyncio.to_thread(company_service.profile_for_owner, owner)) if company_service else None
    except (DatabaseError, CompanyRepositoryError):
        await message.answer("Не удалось прочитать историю тендеров. Попробуйте позже.")
        return
    for chunk in format_history(records, profile):
        await message.answer(chunk, parse_mode=None)
