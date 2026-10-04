"""Telegram commands and guided company management for multi-company workspaces."""
from __future__ import annotations

import asyncio
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

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


class CompanyEdit(StatesGroup):
    """Step-by-step editor for an existing company workspace."""

    name = State()
    mode = State()
    keywords = State()
    regions = State()
    budget = State()
    confirm = State()


class CompanyDelete(StatesGroup):
    """Explicit confirmation before deleting a company workspace."""

    confirm = State()


_KEEP_VALUES = {"=", "оставить", "без изменений", "keep", "same"}
_CANCEL_VALUES = {"нет", "no", "n", "отмена", "cancel"}
_YES_VALUES = {"да", "yes", "y", "сохранить", "save", "создать", "create"}
_DELETE_VALUES = {"удалить", "delete"}


def _owner(message: Message) -> int | None:
    value = getattr(getattr(message, "from_user", None), "id", None)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _callback_owner(callback: CallbackQuery) -> int | None:
    value = getattr(getattr(callback, "from_user", None), "id", None)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _command_tail(message: Message) -> str:
    text = (message.text or "").strip()
    return text.split(maxsplit=1)[1].strip() if " " in text else ""


def _money(value: float | None) -> str:
    if value is None:
        return "без лимита"
    return f"{value:,.0f}".replace(",", " ")


def _normalize_answer(value: str) -> str:
    return " ".join(value.casefold().strip().split())


def _is_keep(value: str) -> bool:
    return _normalize_answer(value) in _KEEP_VALUES


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


def company_switch_markup(items: Iterable[Any]) -> InlineKeyboardMarkup | None:
    """Build compact one-tap company switch buttons for /companies."""

    rows: list[list[InlineKeyboardButton]] = []
    for item in list(items)[:20]:
        marker = "✅" if item.is_active else "➡️"
        label = f"{marker} #{item.id} {item.name}"[:64]
        rows.append([InlineKeyboardButton(text=label, callback_data=f"company_use:{item.id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def _resolve_company(items: Iterable[Any], selector: str):
    """Resolve a company by numeric id or exact case-insensitive name."""

    clean = " ".join(selector.strip().split())
    if not clean:
        return None
    try:
        company_id = int(clean)
    except ValueError:
        company_id = None
    candidates = list(items)
    if company_id is not None:
        return next((item for item in candidates if int(item.id) == company_id), None)
    matches = [item for item in candidates if str(item.name).casefold() == clean.casefold()]
    return matches[0] if len(matches) == 1 else None


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
            "Пока персонального профиля нет, VALYQON AI использует demo-профиль администратора."
        )
        return
    await message.answer(
        "🏢 ВАШИ КОМПАНИИ\n\n"
        + "\n\n".join(format_workspace(item) for item in items)
        + "\n\nНажмите кнопку компании, чтобы сделать её активной.\n"
        "Редактировать: /company_edit\nУдалить: /company_delete",
        reply_markup=company_switch_markup(items),
    )


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
    await message.answer(
        "🏢 АКТИВНАЯ КОМПАНИЯ\n\n"
        + format_workspace(item)
        + "\n\nРедактировать: /company_edit\nУдалить: /company_delete"
    )


async def company_use_handler(message: Message, company_service: CompanyService | None = None) -> None:
    owner = _owner(message)
    if company_service is None or owner is None:
        await message.answer("Company workspaces пока недоступны.")
        return
    raw = _command_tail(message)
    if not raw:
        try:
            items = await asyncio.to_thread(company_service.list, owner)
        except CompanyRepositoryError:
            await message.answer("Не удалось прочитать список компаний.")
            return
        if not items:
            await message.answer("У вас пока нет компаний. Создать: /company_setup")
            return
        await message.answer(
            "Выберите активную компанию кнопкой или используйте /company_use <id>.",
            reply_markup=company_switch_markup(items),
        )
        return
    try:
        items = await asyncio.to_thread(company_service.list, owner)
        selected = _resolve_company(items, raw)
        if selected is None:
            await message.answer("Компания не найдена. Используйте /companies и выберите её кнопкой.")
            return
        item = await asyncio.to_thread(company_service.set_active, owner, int(selected.id))
    except CompanyRepositoryError as error:
        await message.answer(str(error))
        return
    await message.answer(
        f"✅ Активная компания переключена на #{item.id}: {item.name}.\n"
        "Следующие /tenders, автоуведомления и scoring будут использовать этот профиль."
    )


async def company_use_callback_handler(
    callback: CallbackQuery,
    company_service: CompanyService | None = None,
) -> None:
    owner = _callback_owner(callback)
    data = callback.data or ""
    if company_service is None or owner is None or not data.startswith("company_use:"):
        await callback.answer("Переключение недоступно.", show_alert=True)
        return
    try:
        company_id = int(data.split(":", 1)[1])
        item = await asyncio.to_thread(company_service.set_active, owner, company_id)
    except (ValueError, CompanyRepositoryError) as error:
        await callback.answer(str(error) or "Не удалось переключить компанию.", show_alert=True)
        return
    await callback.answer(f"Активна: {item.name}")
    if callback.message is not None:
        await callback.message.answer(
            f"✅ Активная компания: #{item.id} {item.name}.\n"
            "Следующие /tenders и scoring будут использовать этот профиль."
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
    raw = _normalize_answer(value)
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


def build_profile_from_edit(data: dict[str, Any]) -> CompanyProfile:
    """Update wizard-managed fields while preserving advanced profile fields."""

    original = CompanyProfile.model_validate(data["original_profile"])
    updates: dict[str, Any] = {
        "company_name": str(data.get("name", original.company_name)).strip(),
        "business_mode": str(data.get("mode", original.business_mode)).strip(),
        "allowed_regions": list(data.get("regions", original.allowed_regions) or []),
        "max_contract_value": data.get("budget", original.max_contract_value),
    }
    if data.get("keywords_changed"):
        keywords = list(data.get("keywords") or [])
        updates["product_keywords"] = keywords
        updates["search_keywords"] = keywords
    regions = updates["allowed_regions"]
    budget = updates["max_contract_value"]
    updates["hard_stop_on_region"] = bool(regions)
    updates["hard_stop_on_budget"] = budget is not None
    merged = original.model_dump(mode="python")
    merged.update(updates)
    return CompanyProfile.model_validate(merged)


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


def format_edit_summary(data: dict[str, Any]) -> str:
    keywords = ", ".join(data.get("keywords") or []) or "не заданы"
    regions = ", ".join(data.get("regions") or []) or "без ограничения"
    return (
        "Проверьте изменения перед сохранением:\n\n"
        f"Компания: {data.get('name', '')}\n"
        f"Режим: {data.get('mode', 'sell')}\n"
        f"Что отслеживать: {keywords}\n"
        f"Регионы: {regions}\n"
        f"Максимальный контракт: {_money(data.get('budget'))} RUB\n\n"
        "Напишите ДА, чтобы сохранить, или НЕТ, чтобы отменить."
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
    answer = _normalize_answer(message.text or "")
    if answer in _CANCEL_VALUES:
        await state.clear()
        await message.answer("Создание компании отменено.")
        return
    if answer not in _YES_VALUES:
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
        f"VALYQON AI будет строить {len(profile.monitoring_keywords)} персональных EIS-поиска(ов).\n\n"
        "Проверить профиль: /company_show\n"
        "Проверить закупки: /tenders\n"
        "Статус мониторинга: /monitor_status"
        + note
    )


async def company_edit_handler(
    message: Message,
    state: FSMContext,
    company_service: CompanyService | None = None,
) -> None:
    owner = _owner(message)
    if company_service is None or owner is None:
        await message.answer("Редактирование компаний пока недоступно.")
        return
    selector = _command_tail(message)
    try:
        if selector:
            items = await asyncio.to_thread(company_service.list, owner)
            item = _resolve_company(items, selector)
        else:
            item = await asyncio.to_thread(company_service.active, owner)
    except CompanyRepositoryError:
        await message.answer("Не удалось прочитать профиль компании.")
        return
    if item is None:
        await message.answer(
            "Компания для редактирования не найдена.\n"
            "Откройте /companies, сделайте нужную компанию активной и повторите /company_edit."
        )
        return
    profile = item.profile
    await state.clear()
    await state.update_data(
        edit_company_id=int(item.id),
        original_profile=profile.model_dump(mode="json"),
        name=item.name,
        mode=profile.business_mode,
        keywords=list(profile.monitoring_keywords),
        keywords_changed=False,
        regions=list(profile.allowed_regions),
        budget=profile.max_contract_value,
    )
    await state.set_state(CompanyEdit.name)
    await message.answer(
        f"✏️ РЕДАКТИРОВАНИЕ #{item.id} {item.name} — шаг 1 из 5\n\n"
        f"Текущее название: {item.name}\n"
        "Введите новое название. Чтобы оставить текущее, отправьте =\n\n"
        "Отмена в любой момент: /company_cancel"
    )


async def company_edit_name_handler(message: Message, state: FSMContext) -> None:
    raw = message.text or ""
    if not _is_keep(raw):
        name = " ".join(raw.strip().split())
        if not name or name.startswith("/"):
            await message.answer("Введите название компании или =, чтобы оставить текущее.")
            return
        if len(name) > 200:
            await message.answer("Название слишком длинное. Используйте до 200 символов.")
            return
        await state.update_data(name=name)
    data = await state.get_data()
    await state.set_state(CompanyEdit.mode)
    await message.answer(
        "✏️ Шаг 2 из 5 — режим\n\n"
        f"Сейчас: {data.get('mode', 'sell')}\n"
        "Введите sell, buy или both. Чтобы оставить текущий режим, отправьте ="
    )


async def company_edit_mode_handler(message: Message, state: FSMContext) -> None:
    raw = message.text or ""
    if not _is_keep(raw):
        mode = _parse_mode(raw)
        if mode is None:
            await message.answer("Введите sell, buy, both или =, чтобы оставить текущее.")
            return
        await state.update_data(mode=mode)
    data = await state.get_data()
    current = ", ".join(data.get("keywords") or []) or "не заданы"
    await state.set_state(CompanyEdit.keywords)
    await message.answer(
        "✏️ Шаг 3 из 5 — ключевые слова\n\n"
        f"Сейчас: {current}\n\n"
        "Введите новый список через запятую. Чтобы оставить текущий список, отправьте ="
    )


async def company_edit_keywords_handler(message: Message, state: FSMContext) -> None:
    raw = message.text or ""
    if not _is_keep(raw):
        keywords = _parse_csv(raw)
        if not keywords:
            await message.answer("Нужно хотя бы одно ключевое слово либо =, чтобы оставить текущие.")
            return
        if len(keywords) > 100:
            await message.answer("Слишком много ключевых слов. Укажите не более 100.")
            return
        await state.update_data(keywords=keywords, keywords_changed=True)
    data = await state.get_data()
    current = ", ".join(data.get("regions") or []) or "без ограничения"
    await state.set_state(CompanyEdit.regions)
    await message.answer(
        "✏️ Шаг 4 из 5 — регионы\n\n"
        f"Сейчас: {current}\n\n"
        "Новые регионы — через запятую.\n"
        "= — оставить как есть\n"
        "- — убрать ограничение по регионам"
    )


async def company_edit_regions_handler(message: Message, state: FSMContext) -> None:
    raw = message.text or ""
    if not _is_keep(raw):
        await state.update_data(regions=_parse_csv(raw))
    data = await state.get_data()
    await state.set_state(CompanyEdit.budget)
    await message.answer(
        "✏️ Шаг 5 из 5 — максимальный контракт\n\n"
        f"Сейчас: {_money(data.get('budget'))} RUB\n\n"
        "Введите новое положительное число.\n"
        "= — оставить как есть\n"
        "- — убрать лимит"
    )


async def company_edit_budget_handler(message: Message, state: FSMContext) -> None:
    raw = message.text or ""
    if not _is_keep(raw):
        try:
            budget = _parse_budget(raw)
        except ValueError:
            await message.answer("Введите положительное число, -, либо =, чтобы оставить текущее.")
            return
        await state.update_data(budget=budget)
    data = await state.get_data()
    await state.set_state(CompanyEdit.confirm)
    await message.answer(format_edit_summary(data))


async def company_edit_confirm_handler(
    message: Message,
    state: FSMContext,
    company_service: CompanyService | None = None,
) -> None:
    owner = _owner(message)
    if company_service is None or owner is None:
        await state.clear()
        await message.answer("Не удалось завершить редактирование компании.")
        return
    answer = _normalize_answer(message.text or "")
    if answer in _CANCEL_VALUES:
        await state.clear()
        await message.answer("Изменения отменены.")
        return
    if answer not in _YES_VALUES:
        await message.answer("Напишите ДА, чтобы сохранить изменения, или НЕТ, чтобы отменить.")
        return
    data = await state.get_data()
    try:
        profile = build_profile_from_edit(data)
        company_id = int(data["edit_company_id"])
        item = await asyncio.to_thread(
            company_service.update,
            owner,
            company_id,
            profile,
            name=str(data["name"]),
        )
    except (CompanyRepositoryError, KeyError, TypeError, ValueError) as error:
        await state.clear()
        await message.answer(f"Не удалось сохранить изменения: {error}")
        return
    await state.clear()
    await message.answer(
        f"✅ Компания обновлена: #{item.id} {item.name}.\n"
        "Новые настройки будут использоваться в следующих /tenders, автоуведомлениях и scoring.\n"
        "Проверить: /company_show"
    )


async def company_delete_handler(
    message: Message,
    state: FSMContext,
    company_service: CompanyService | None = None,
) -> None:
    owner = _owner(message)
    if company_service is None or owner is None:
        await message.answer("Удаление компаний пока недоступно.")
        return
    selector = _command_tail(message)
    try:
        if selector:
            items = await asyncio.to_thread(company_service.list, owner)
            item = _resolve_company(items, selector)
        else:
            item = await asyncio.to_thread(company_service.active, owner)
    except CompanyRepositoryError:
        await message.answer("Не удалось прочитать профиль компании.")
        return
    if item is None:
        await message.answer("Компания для удаления не найдена. Проверьте /companies.")
        return
    await state.clear()
    await state.update_data(delete_company_id=int(item.id), delete_company_name=item.name)
    await state.set_state(CompanyDelete.confirm)
    await message.answer(
        "⚠️ УДАЛЕНИЕ КОМПАНИИ\n\n"
        f"Вы собираетесь удалить #{item.id} {item.name}.\n"
        "Это удалит профиль компании из VALYQON AI.\n\n"
        "Для подтверждения напишите точно: УДАЛИТЬ\n"
        "Для отмены: НЕТ или /company_cancel"
    )


async def company_delete_confirm_handler(
    message: Message,
    state: FSMContext,
    company_service: CompanyService | None = None,
) -> None:
    owner = _owner(message)
    if company_service is None or owner is None:
        await state.clear()
        await message.answer("Не удалось завершить удаление компании.")
        return
    answer = _normalize_answer(message.text or "")
    if answer in _CANCEL_VALUES:
        await state.clear()
        await message.answer("Удаление отменено.")
        return
    if answer not in _DELETE_VALUES:
        await message.answer("Чтобы удалить компанию, напишите УДАЛИТЬ. Для отмены напишите НЕТ.")
        return
    data = await state.get_data()
    company_id = int(data.get("delete_company_id", 0))
    company_name = str(data.get("delete_company_name", ""))
    try:
        deleted = await asyncio.to_thread(company_service.delete, owner, company_id)
        replacement = await asyncio.to_thread(company_service.active, owner) if deleted else None
    except CompanyRepositoryError as error:
        await state.clear()
        await message.answer(f"Не удалось удалить компанию: {error}")
        return
    await state.clear()
    if not deleted:
        await message.answer("Компания уже не существует или была удалена ранее.")
        return
    if replacement is not None:
        await message.answer(
            f"✅ Компания #{company_id} {company_name} удалена.\n"
            f"Новая активная компания: #{replacement.id} {replacement.name}."
        )
    else:
        await message.answer(
            f"✅ Компания #{company_id} {company_name} удалена.\n"
            "Персональных компаний больше нет. VALYQON AI вернётся к fallback-профилю, если он настроен.\n"
            "Создать новую: /company_setup"
        )


async def company_setup_cancel_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Текущая операция с компанией отменена.\n"
        "Компании: /companies · Создать: /company_setup · Активная: /company_show"
    )
