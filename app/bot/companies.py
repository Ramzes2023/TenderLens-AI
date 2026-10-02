"""Telegram commands for multi-company workspaces."""
from __future__ import annotations

import asyncio
from decimal import Decimal, InvalidOperation

from aiogram.types import Message

from app.companies import CompanyRepositoryError, CompanyService
from app.scoring.models import CompanyProfile


def _owner(message: Message) -> int | None:
    value = getattr(getattr(message, "from_user", None), "id", None)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _command_tail(message: Message) -> str:
    text = (message.text or "").strip()
    return text.split(maxsplit=1)[1].strip() if " " in text else ""


def _money(value: float | None) -> str:
    if value is None:
        return "без лимита"
    return f"{value:,.0f}".replace(",", " ")


def format_workspace(workspace) -> str:
    profile = workspace.profile
    marker = "✅ ACTIVE" if workspace.is_active else "▫️"
    keywords = ", ".join(profile.monitoring_keywords[:8]) or "не заданы"
    regions = ", ".join(profile.allowed_regions[:6]) or "без ограничения"
    return (
        f"{marker} #{workspace.id} · {workspace.name}\n"
        f"Режим: {profile.business_mode}\n"
        f"Ключевые слова: {keywords}\n"
        f"Регионы: {regions}\n"
        f"Диапазон: {_money(profile.min_contract_value)} — {_money(profile.max_contract_value)} RUB"
    )


async def companies_handler(message: Message, company_service: CompanyService | None = None) -> None:
    owner = _owner(message)
    if company_service is None or owner is None:
        await message.answer("Company workspaces пока недоступны.")
        return
    try:
        items = await asyncio.to_thread(company_service.list, owner)
    except CompanyRepositoryError:
        await message.answer("Не удалось прочитать список компаний.")
        return
    if not items:
        await message.answer(
            "У вас пока нет персональных профилей компаний.\n\n"
            "Создать:\n"
            "/company_add Название | sell | ключ1, ключ2 | регион1, регион2 | 50000000\n\n"
            "Вместо регионов или бюджета можно указать '-'. Пока персонального профиля нет, "
            "TenderLens использует demo-профиль администратора."
        )
        return
    await message.answer("🏢 ВАШИ КОМПАНИИ\n\n" + "\n\n".join(format_workspace(item) for item in items))


async def company_show_handler(message: Message, company_service: CompanyService | None = None) -> None:
    owner = _owner(message)
    if company_service is None or owner is None:
        await message.answer("Company workspaces пока недоступны.")
        return
    try:
        item = await asyncio.to_thread(company_service.active, owner)
    except CompanyRepositoryError:
        await message.answer("Не удалось прочитать активную компанию.")
        return
    if item is None:
        profile = company_service.fallback_profile
        if profile is None:
            await message.answer("Активная компания не выбрана.")
            return
        await message.answer(
            "🏢 Активен fallback-профиль администратора\n"
            f"Компания: {profile.company_name}\n"
            f"Ключевые слова: {', '.join(profile.monitoring_keywords[:10]) or 'не заданы'}"
        )
        return
    await message.answer("🏢 АКТИВНАЯ КОМПАНИЯ\n\n" + format_workspace(item))


async def company_use_handler(message: Message, company_service: CompanyService | None = None) -> None:
    owner = _owner(message)
    if company_service is None or owner is None:
        await message.answer("Company workspaces пока недоступны.")
        return
    raw = _command_tail(message)
    try:
        company_id = int(raw)
    except ValueError:
        await message.answer("Использование: /company_use <id>\nПример: /company_use 2")
        return
    try:
        item = await asyncio.to_thread(company_service.set_active, owner, company_id)
    except CompanyRepositoryError as error:
        await message.answer(str(error))
        return
    await message.answer(
        f"✅ Активная компания переключена на #{item.id}: {item.name}.\n"
        "Следующие /tenders, автоуведомления и scoring будут использовать этот профиль."
    )


def _parse_csv(value: str) -> list[str]:
    if not value or value.strip() == "-":
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_budget(value: str) -> float | None:
    raw = value.strip().replace(" ", "").replace(",", ".")
    if not raw or raw == "-":
        return None
    try:
        amount = float(Decimal(raw))
    except (InvalidOperation, ValueError):
        raise ValueError from None
    if amount <= 0:
        raise ValueError
    return amount


async def company_add_handler(message: Message, company_service: CompanyService | None = None) -> None:
    owner = _owner(message)
    if company_service is None or owner is None:
        await message.answer("Company workspaces пока недоступны.")
        return
    raw = _command_tail(message)
    parts = [part.strip() for part in raw.split("|")]
    if len(parts) != 5:
        await message.answer(
            "Формат:\n"
            "/company_add Название | sell | ключ1, ключ2 | регион1, регион2 | максимальный_бюджет\n\n"
            "Пример для алюминия:\n"
            "/company_add AluTrade | sell | алюминий, алюминиевый профиль, алюминиевый лист | - | 50000000\n\n"
            "Режимы: sell, buy, both. Вместо регионов/бюджета можно указать '-'."
        )
        return
    name, mode, keyword_raw, region_raw, budget_raw = parts
    mode = mode.casefold()
    if mode not in {"sell", "buy", "both"}:
        await message.answer("Режим должен быть sell, buy или both.")
        return
    keywords = _parse_csv(keyword_raw)
    if not keywords:
        await message.answer("Нужно указать хотя бы одно товарное/сервисное ключевое слово.")
        return
    try:
        budget = _parse_budget(budget_raw)
    except ValueError:
        await message.answer("Максимальный бюджет должен быть положительным числом или '-'.")
        return
    regions = _parse_csv(region_raw)
    profile = CompanyProfile(
        profile_version="workspace-1",
        company_name=name,
        business_mode=mode,
        product_keywords=keywords,
        search_keywords=keywords,
        allowed_regions=regions,
        accepted_currencies=["RUB"],
        max_contract_value=budget,
        hard_stop_on_region=bool(regions),
        hard_stop_on_budget=budget is not None,
    )
    try:
        item = await asyncio.to_thread(company_service.create, owner, name, profile, make_active=True)
    except CompanyRepositoryError as error:
        await message.answer(str(error))
        return
    note = ""
    if mode == "buy":
        note = (
            "\nℹ️ Профиль отмечен как buy. Текущий источник ЕИС показывает спрос покупателей; "
            "supplier-intelligence источники для поиска поставщиков будут подключены следующим этапом."
        )
    await message.answer(
        f"✅ Компания создана и активирована: #{item.id} {item.name}.\n"
        f"Персональные EIS-поиски будут строиться по {len(profile.monitoring_keywords)} ключевым словам."
        + note
    )
