"""Telegram UI for Phase 9 tender monitoring."""
from __future__ import annotations

import asyncio
import contextlib
import logging

from aiogram import Bot
from aiogram.types import Message

from app.monitoring import MonitoringRepositoryError, TenderMonitorService
from app.companies import CompanyRepositoryError, CompanyService
from app.sources import SourceCatalog, SourceError

logger = logging.getLogger(__name__)


def _money(value: float | None, currency: str | None) -> str:
    if value is None:
        return "не указана в RSS"
    amount = f"{value:,.2f}".replace(",", " ")
    return f"{amount} {currency or ''}".strip()


def format_match(match, *, index: int | None = None) -> str:
    notice = match.notice
    prefix = f"{index}. " if index is not None else ""
    lines = [f"{prefix}📌 {notice.title}"]
    lines.append(f"Источник: {notice.source}")
    if notice.tender_number:
        lines.append(f"Номер: {notice.tender_number}")
    if notice.customer:
        lines.append(f"Заказчик: {notice.customer}")
    lines.append(f"Цена: {_money(notice.initial_price, notice.currency)}")
    if notice.deadline:
        lines.append(f"Подача заявок: {notice.deadline}")
    if notice.region:
        lines.append(f"Регион: {notice.region}")
    if match.reasons:
        lines.append("Pre-filter: " + "; ".join(match.reasons))
    if notice.url:
        lines.append(notice.url)
    return "\n".join(lines)


async def _service_or_message(message: Message, monitoring_service: TenderMonitorService | None):
    if monitoring_service is None:
        await message.answer(
            "Мониторинг источников не настроен. Проверьте EIS_RSS_URLS / EIS_PROFILE_FEEDS_ENABLED и перезапустите бота."
        )
        return None
    return monitoring_service


async def tenders_handler(
    message: Message,
    monitoring_service: TenderMonitorService | None = None,
    source_catalog: SourceCatalog | None = None,
) -> None:
    service = await _service_or_message(
        message,
        monitoring_service,
    )

    if (
        service is None
        or message.from_user is None
    ):
        return

    status = await message.answer(
        "Проверяю новые закупки "
        "в официальных источниках VALYQON…"
    )

    report = None

    try:
        if source_catalog is None:
            matches = await service.scan_new(
                message.from_user.id
            )
        else:
            matches, report = (
                await service.scan_new_from_catalog(
                    source_catalog,
                    message.from_user.id,
                )
            )

    except (
        SourceError,
        MonitoringRepositoryError,
    ):
        await status.edit_text(
            "Не удалось проверить источники закупок. "
            "Проверьте сеть и конфигурацию VALYQON."
        )
        return

    if report is not None:
        if not report.attempted_sources:
            await status.edit_text(
                "Нет включённых источников закупок."
            )
            return

        if report.total_failure:
            await status.edit_text(
                "Не удалось получить данные "
                "ни из одного включённого источника."
            )
            return

    lines: list[str] = []

    if matches:
        lines.append(
            "Найдено новых подходящих закупок: "
            f"{len(matches)}"
        )
    else:
        lines.append(
            "Новых подходящих закупок "
            "с момента последней проверки нет."
        )

    if report is not None:
        lines.append(
            "Источники: "
            f"{len(report.successful_sources)}/"
            f"{len(report.attempted_sources)} успешно."
        )

        if report.failures:
            failed = ", ".join(
                failure.source
                for failure in report.failures[:5]
            )

            lines.append(
                "Частично недоступны: "
                + failed
            )

    await status.edit_text(
        "\n".join(lines)
    )

    if not matches:
        return

    limit = (
        service.settings
        .max_notifications_per_cycle
    )

    for index, match in enumerate(
        matches[:limit],
        1,
    ):
        await message.answer(
            format_match(
                match,
                index=index,
            ),
            disable_web_page_preview=True,
        )

    remaining = len(matches) - limit

    if remaining > 0:
        await message.answer(
            f"Ещё {remaining} новых записей "
            "сохранены как просмотренные."
        )


async def monitor_on_handler(message: Message, monitoring_service: TenderMonitorService | None = None) -> None:
    service = await _service_or_message(message, monitoring_service)
    if service is None or message.from_user is None:
        return
    if not service.settings.enabled:
        await message.answer(
            "Автоцикл отключён глобально. Установите MONITORING_ENABLED=true в .env и перезапустите бота. "
            "Для ручной проверки используйте /tenders."
        )
        return
    status = await message.answer("Подготавливаю исходную точку мониторинга…")
    try:
        baseline_count = await service.baseline(message.from_user.id)
        await service.subscribe(message.from_user.id, message.chat.id)
    except (SourceError, MonitoringRepositoryError):
        await status.edit_text("Не удалось включить мониторинг. Проверьте источник и локальную БД.")
        return
    await status.edit_text(
        "✅ Автомониторинг включён.\n"
        f"Текущие подходящие записи помечены как baseline: {baseline_count}.\n"
        f"Дальше бот проверяет источник примерно каждые {service.settings.interval_seconds // 60} мин."
    )


async def monitor_off_handler(message: Message, monitoring_service: TenderMonitorService | None = None) -> None:
    service = await _service_or_message(message, monitoring_service)
    if service is None or message.from_user is None:
        return
    try:
        await service.unsubscribe(message.from_user.id, message.chat.id)
    except MonitoringRepositoryError:
        await message.answer("Не удалось изменить monitoring-подписку в локальной БД.")
        return
    await message.answer("⏸ Автомониторинг выключен. /tenders остаётся доступной для ручной проверки.")


async def monitor_status_handler(message: Message, monitoring_service: TenderMonitorService | None = None,
                                 company_service: CompanyService | None = None) -> None:
    service = await _service_or_message(message, monitoring_service)
    if service is None or message.from_user is None:
        return
    owner_id = message.from_user.id
    try:
        subscription = await service.subscription(owner_id)
        workspace = (await asyncio.to_thread(company_service.active, owner_id)) if company_service else None
    except (MonitoringRepositoryError, CompanyRepositoryError):
        await message.answer("Не удалось прочитать monitoring/company состояние.")
        return
    state = "включён" if subscription and subscription.enabled else "выключен"
    global_state = "запущен" if service.settings.enabled else "отключён"
    profile = workspace.profile if workspace is not None else await service.profile_for_owner(owner_id)
    if profile is not None and getattr(service.settings, "profile_feeds_enabled", False) and profile.monitoring_keywords:
        feed_count = min(len(profile.monitoring_keywords), getattr(service.settings, "profile_feed_limit", 5))
        feed_mode = "персональные поиски по активной компании"
    else:
        feed_count = len(service.settings.eis_rss_urls)
        feed_mode = "статические RSS"
    company_line = workspace.name if workspace is not None else (profile.company_name if profile else "не выбрана")
    await message.answer(
        "📡 Мониторинг ЕИС\n"
        f"Фоновый цикл: {global_state}\n"
        f"Ваша подписка: {state}\n"
        f"Активная компания: {company_line}\n"
        f"Интервал: {service.settings.interval_seconds} сек.\n"
        f"RSS-поисков: {feed_count} ({feed_mode})\n"
        "Pre-filter использует данные RSS и активный профиль; полный score выполняется после анализа документа."
    )


async def monitor_loop(bot: Bot, service: TenderMonitorService, stop_event: asyncio.Event) -> None:
    """Periodic source check. Errors are logged without URLs or credentials."""
    while not stop_event.is_set():
        try:
            subscriptions = await service.active_subscriptions()
            if subscriptions:
                for subscription in subscriptions:
                    try:
                        matches = await service.fetch_matches(subscription.owner_user_id)
                        new_matches = await service.claim_new(subscription.owner_user_id, matches)
                        for match in new_matches[:service.settings.max_notifications_per_cycle]:
                            await bot.send_message(
                                subscription.chat_id,
                                "🆕 НОВАЯ ЗАКУПКА\n\n" + format_match(match),
                                disable_web_page_preview=True,
                            )
                    except (MonitoringRepositoryError, SourceError):
                        logger.warning("Monitoring scan failed for one subscription.")
                    except Exception:
                        logger.warning("Telegram notification failed for one subscription.")
        except (MonitoringRepositoryError, SourceError):
            logger.warning("Monitoring cycle could not read subscriptions/source.")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=service.settings.interval_seconds)
        except asyncio.TimeoutError:
            pass


async def stop_monitor_task(task: asyncio.Task | None, stop_event: asyncio.Event | None) -> None:
    if stop_event is not None:
        stop_event.set()
    if task is not None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
