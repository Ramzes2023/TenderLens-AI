"""Telegram commands and guided onboarding for multi-company workspaces."""
from __future__ import annotations

import asyncio
from decimal import Decimal, InvalidOperation
from typing import Any

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from app.companies import CompanyRepositoryError, CompanyService
from app.scoring.models import CompanyProfile


class CompanySetup(StatesGroup):
    """Step-by-step Telegram wizard for creating a company workspace."""

    name = State()
    mode = State()
    keywords = State()
    regions = State()
    budget = State()
    confirm = State()


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
            "Самый простой способ — запустить пошаговую настройку:\n"
            "/company_setup\n\n"
            "Для опытных пользователей остаётся короткий формат:\n"
            "/company_add Название | sell | ключ1, ключ2 | регион1, регион2 | 50000000\n\n"
            "Пока персонального профиля нет, TenderLens использует demo-профиль администратора."
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
            f"Ключевые слова: {', '.join(profile.monitoring_keywords[:10]) or 'не заданы'}\n\n"
            "Создать свой профиль: /company_setup"
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


def _parse_mode(value: str) -> str | None:
    raw = " ".join(value.casefold().strip().split())
    aliases = {
        "sell": "sell",
        "продавать": "sell",
        "продажа": "sell",
        "продаем": "sell",
        "продаём": "sell",
        "buy": "buy",
        "покупать": "buy",
        "закупать": "buy",
        "покупка": "buy",
        "both": "both",
        "оба": "both",
        "оба режима": "both",
        "покупать и продавать": "both",
        "продавать и покупать": "both",
    }
    return aliases.get(raw)


def build_profile_from_setup(data: dict[str, Any]) -> CompanyProfile:
    """Build the same validated profile used by the one-line /company_add command."""

    name = str(data.get("name", "")).strip()
    mode = str(data.get("mode", "sell")).strip()
    keywords = list(data.get("keywords") or [])
    regions = list(data.get("regions") or [])
    budget = data.get("budget")
    return CompanyProfile(
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


def format_setup_summary(data: dict[str, Any]) -> str:
    keywords = ", ".join(data.get("keywords") or []) or "не заданы"
    regions = ", ".join(data.get("regions") or []) or "без ограничения"
    return (
        "Проверьте профиль перед созданием:\n\n"
        f"Компания: {data.get('name', '')}\n"
        f"Режим: {data.get('mode', 'sell')}\n"
        f"Что отслеживать: {keywords}\n"
        f"Регионы: {regions}\n"
        f"Максимальный контракт: {_money(data.get('budget'))} RUB\n\n"
        "Напишите ДА, чтобы создать компанию, или НЕТ, чтобы отменить."
    )


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
            "Или используйте более простой мастер: /company_setup\n\n"
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


async def company_setup_handler(
    message: Message,
    state: FSMContext,
    company_service: CompanyService | None = None,
) -> None:
    owner = _owner(message)
    if company_service is None or owner is None:
        await message.answer("Пошаговая настройка компаний пока недоступна.")
        return
    await state.clear()
    await state.set_state(CompanySetup.name)
    await message.answer(
        "🏢 СОЗДАНИЕ КОМПАНИИ — шаг 1 из 5\n\n"
        "Как называется компания?\n"
        "Например: AluTrade или MedSupply.\n\n"
        "В любой момент можно написать /company_cancel."
    )


async def company_setup_name_handler(message: Message, state: FSMContext) -> None:
    name = " ".join((message.text or "").strip().split())
    if not name or name.startswith("/"):
        await message.answer("Введите обычное название компании, например: AluTrade")
        return
    if len(name) > 200:
        await message.answer("Название слишком длинное. Используйте до 200 символов.")
        return
    await state.update_data(name=name)
    await state.set_state(CompanySetup.mode)
    await message.answer(
        "🏢 Шаг 2 из 5\n\n"
        "Что компания хочет делать?\n\n"
        "Напишите одно из:\n"
        "• sell — продавать через тендеры\n"
        "• buy — искать поставщиков (источники supplier intelligence добавим позже)\n"
        "• both — оба направления\n\n"
        "Можно также написать: продавать, покупать или оба."
    )


async def company_setup_mode_handler(message: Message, state: FSMContext) -> None:
    mode = _parse_mode(message.text or "")
    if mode is None:
        await message.answer("Не понял режим. Напишите sell, buy или both.")
        return
    await state.update_data(mode=mode)
    await state.set_state(CompanySetup.keywords)
    await message.answer(
        "🏢 Шаг 3 из 5\n\n"
        "Что компания продаёт или хочет отслеживать?\n"
        "Перечислите через запятую.\n\n"
        "Пример:\n"
        "алюминий, алюминиевый профиль, алюминиевый лист\n\n"
        "Чем точнее слова, тем точнее мониторинг ЕИС."
    )


async def company_setup_keywords_handler(message: Message, state: FSMContext) -> None:
    keywords = _parse_csv(message.text or "")
    if not keywords:
        await message.answer("Нужно указать хотя бы одно направление или товар.")
        return
    if len(keywords) > 100:
        await message.answer("Слишком много ключевых слов. Укажите не более 100.")
        return
    await state.update_data(keywords=keywords)
    await state.set_state(CompanySetup.regions)
    await message.answer(
        "🏢 Шаг 4 из 5\n\n"
        "В каких регионах работать?\n"
        "Напишите регионы через запятую.\n\n"
        "Если регион не важен — отправьте один символ:\n-"
    )


async def company_setup_regions_handler(message: Message, state: FSMContext) -> None:
    regions = _parse_csv(message.text or "")
    await state.update_data(regions=regions)
    await state.set_state(CompanySetup.budget)
    await message.answer(
        "🏢 Шаг 5 из 5\n\n"
        "Какова максимальная стоимость интересующего контракта в RUB?\n\n"
        "Например: 50000000\n"
        "Если лимита нет — отправьте:\n-"
    )


async def company_setup_budget_handler(message: Message, state: FSMContext) -> None:
    try:
        budget = _parse_budget(message.text or "")
    except ValueError:
        await message.answer("Введите положительное число, например 50000000, либо '-' без лимита.")
        return
    await state.update_data(budget=budget)
    data = await state.get_data()
    await state.set_state(CompanySetup.confirm)
    await message.answer(format_setup_summary(data))


async def company_setup_confirm_handler(
    message: Message,
    state: FSMContext,
    company_service: CompanyService | None = None,
) -> None:
    owner = _owner(message)
    if company_service is None or owner is None:
        await state.clear()
        await message.answer("Не удалось завершить создание компании.")
        return
    answer = " ".join((message.text or "").casefold().strip().split())
    if answer in {"нет", "no", "n", "отмена", "cancel"}:
        await state.clear()
        await message.answer("Создание компании отменено.")
        return
    if answer not in {"да", "yes", "y", "создать", "create"}:
        await message.answer("Напишите ДА для создания или НЕТ для отмены.")
        return
    data = await state.get_data()
    try:
        profile = build_profile_from_setup(data)
        item = await asyncio.to_thread(
            company_service.create,
            owner,
            str(data["name"]),
            profile,
            make_active=True,
        )
    except (CompanyRepositoryError, KeyError, ValueError) as error:
        await state.clear()
        await message.answer(f"Не удалось создать компанию: {error}")
        return
    await state.clear()
    note = ""
    if profile.business_mode == "buy":
        note = (
            "\n\nℹ️ Сейчас ЕИС используется для поиска спроса/тендеров. "
            "Полноценный поиск поставщиков для buy-режима будет отдельным модулем Supplier Intelligence."
        )
    await message.answer(
        f"✅ Компания создана и стала активной: #{item.id} {item.name}.\n"
        f"TenderLens будет строить {len(profile.monitoring_keywords)} персональных EIS-поиска(ов).\n\n"
        "Проверить профиль: /company_show\n"
        "Проверить закупки: /tenders\n"
        "Статус мониторинга: /monitor_status"
        + note
    )


async def company_setup_cancel_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Пошаговая настройка компании отменена. Запустить снова: /company_setup")
