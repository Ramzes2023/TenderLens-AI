"""Telegram UI for Phase 9 tender monitoring."""
from __future__ import annotations

import asyncio
import contextlib
import logging
from types import SimpleNamespace

from aiogram import Bot
from aiogram.types import Message

from app.monitoring import MonitoringRepositoryError, TenderMonitorService
from app.monitoring.service import prefilter_notice
from app.companies import CompanyRepositoryError, CompanyService
from app.sources import SourceCatalog, SourceError

logger = logging.getLogger(__name__)

# Only these fixed regional routes ignore caller-specific upstream search terms.
# Never pool tenant-specific EIS profile RSS requests or any other source.
_SHARED_INGUSHETIA_KEYS = frozenset({
    "ru_ingushetia_eis44", "ru_ingushetia_fabrikant44",
})

def enabled_ru_catalog_keys(catalog: SourceCatalog | None) -> tuple[str, ...]:
    """Only explicitly enabled RU registrations; no guessed or draft sources."""
    if catalog is None:
        return ()
    return tuple(sorted(
        item.key for item in catalog.registry.metadata()
        if item.enabled and "RU" in item.jurisdictions
    ))



def _money(value: float | None, currency: str | None) -> str:
    if value is None:
        return "не указана источником"
    amount = f"{value:,.2f}".replace(",", " ")
    return f"{amount} {currency or ''}".strip()


def _telegram_bounded_field(value, max_utf16: int) -> str:
    """Trim untrusted upstream prose within Telegram's UTF-16 text budget.

    Never split a surrogate pair. Preserve ordinary, already short messages.
    Procurement number and a reasonably sized first-party URL are kept in
    full; descriptions cannot deny delivery to the next valid notice.
    """
    value = str(value)
    if len(value.encode("utf-16-le", errors="replace")) // 2 <= max_utf16:
        return value
    output = []
    remaining = max_utf16 - 1  # the final ellipsis
    for char in value:
        units = 2 if ord(char) > 0xFFFF else 1
        if units > remaining:
            break
        output.append(char)
        remaining -= units
    return "".join(output) + "…"


def format_match(match, *, index: int | None = None) -> str:
    notice = match.notice
    prefix = f"{index}. " if index is not None else ""
    lines = [f"{prefix}📌 {_telegram_bounded_field(notice.title, 900)}"]
    lines.append("Источник: " + _telegram_bounded_field(notice.source, 70))
    if notice.tender_number:
        lines.append("Номер: " + _telegram_bounded_field(notice.tender_number, 80))
    if notice.customer:
        lines.append("Заказчик: " + _telegram_bounded_field(notice.customer, 400))
    lines.append("Цена: " + _telegram_bounded_field(_money(notice.initial_price, notice.currency), 80))
    if notice.deadline:
        lines.append("Подача заявок: " + _telegram_bounded_field(notice.deadline, 100))
    if notice.region:
        lines.append("Регион: " + _telegram_bounded_field(notice.region, 180))
    if match.reasons:
        lines.append("Pre-filter: " + _telegram_bounded_field("; ".join(match.reasons), 380))
    if notice.url:
        # A full, short original link is always retained. An exceptionally
        # long untrusted URL cannot break the entire Bot API send; the notice
        # number remains available to identify the original on the publisher.
        if len(str(notice.url).encode("utf-16-le", errors="replace")) // 2 <= 1200:
            lines.append(str(notice.url))
        else:
            lines.append("Ссылка превышает допустимую длину; используйте номер закупки.")
    return "\n".join(lines)


async def _service_or_message(message: Message, monitoring_service: TenderMonitorService | None):
    if monitoring_service is None:
        await message.answer(
            "Сервис поиска или мониторинга закупок сейчас недоступен. Проверьте конфигурацию VALYQON и локальную БД."
        )
        return None
    return monitoring_service


async def _manual_regional_worker_sql_search(service, source_catalog, owner_id):
    """Deep scan only operator-enabled fixed regional SQL; no extra upstream HTTP.

    A manual /tenders keyword request must not lose a stored matching item
    behind the global 20-result candidate cap. Keep all unrelated, possibly
    tenant-specific sources on the original default search depth, and merge
    their results fairly. Telegram acknowledgement still gates mark_seen.
    """
    enabled = tuple(
        item.key for item in source_catalog.registry.metadata()
        if item.enabled
    )
    regional = tuple(k for k in enabled if k in _SHARED_INGUSHETIA_KEYS)
    if not regional:
        return await service.fetch_matches_from_catalog(source_catalog, owner_id)

    # Explicit Worker-SQL mode may NEVER silently downgrade to on-demand
    # network fetching, even if a caller supplied a live source catalog.
    from app.sources.snapshots import FreshIngushetiaWorkerSource
    if any(not isinstance(source_catalog.registry.get(key).source, FreshIngushetiaWorkerSource)
           for key in regional):
        raise SourceError("Ingushetia Worker-SQL catalog was not installed")
    others = tuple(k for k in enabled if k not in _SHARED_INGUSHETIA_KEYS)
    profile = await service.profile_for_owner(owner_id)
    regional_matches, regional_report = await service.fetch_matches_from_catalog_for_profile(
        source_catalog, profile, source_keys=regional, max_items=1000,
    )
    if not others:
        return regional_matches, regional_report
    other_matches, other_report = await service.fetch_matches_from_catalog_for_profile(
        source_catalog, profile, source_keys=others,
    )
    # Interleave the two independent pools to avoid allowing up to 100
    # regional rows to starve normal tender discovery at a low send cap.
    matches = []
    for idx in range(max(len(regional_matches), len(other_matches))):
        for pool in (regional_matches, other_matches):
            if idx < len(pool):
                matches.append(pool[idx])
    return matches, SimpleNamespace(
        attempted_sources=regional_report.attempted_sources + other_report.attempted_sources,
        successful_sources=regional_report.successful_sources + other_report.successful_sources,
        failures=regional_report.failures + other_report.failures,
        total_failure=not (regional_report.successful_sources or other_report.successful_sources),
    )


async def tenders_handler(
    message: Message,
    monitoring_service: TenderMonitorService | None = None,
    source_catalog: SourceCatalog | None = None,
    tender_discovery_service: TenderMonitorService | None = None,
) -> None:
    if source_catalog is not None:
        service_candidate = (
            tender_discovery_service
            or monitoring_service
        )
    else:
        service_candidate = monitoring_service

    service = await _service_or_message(
        message,
        service_candidate,
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
        owner_id = message.from_user.id
        # Fetch and preview without changing the dedup database.  In the
        # previous implementation scan_new*() marked *all* records seen before
        # Telegram acknowledged any of the resulting messages, losing failed
        # and rate-limited deliveries permanently.
        if source_catalog is None:
            fetched = await service.fetch_matches(owner_id)
        elif (getattr(service.settings, "ru_ingushetia_worker_sql_alerts_enabled", False)
              and callable(getattr(service, "fetch_matches_from_catalog_for_profile", None))
              and callable(getattr(service, "profile_for_owner", None))):
            fetched, report = await _manual_regional_worker_sql_search(
                service, source_catalog, owner_id,
            )
        else:
            fetched, report = await service.fetch_matches_from_catalog(
                source_catalog, owner_id,
            )
        matches = await service.unseen_matches(owner_id, fetched)

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

    for index, match in enumerate(matches[:limit], 1):
        receipt = await message.answer(
            format_match(match, index=index),
            disable_web_page_preview=True,
        )
        # Manual /tenders and background monitoring use the same strict
        # Telegram Bot API acknowledgement policy. No claimed delivery on
        # a missing message ID, wrong chat or unconfirmed transport.
        _require_telegram_delivery_ack(receipt, message.chat.id)
        await service.claim_new(message.from_user.id, [match])

    remaining = len(matches) - limit
    if remaining > 0:
        await message.answer(
            f"Ещё {remaining} новых записей не отправлены. "
            "Для получения остальных повторите /tenders."
        )



async def _baseline_ingushetia_worker_sql(service, source_catalog, owner_id):
    """Mark the complete bounded *fresh* regional SQL baseline, never send it.

    Ordinary catalogue scans are capped at settings.max_items (often 20), so
    marking only their first page as a subscription baseline incorrectly
    re-alerts users about previously indexed regional procurement. This path
    uses the approved in-memory profile filter over bounded source-owned SQL.
    """
    from app.sources.snapshots import FreshIngushetiaWorkerSource

    if source_catalog is None:
        raise ValueError("No configured Worker SQL catalogue")
    enabled = enabled_ru_catalog_keys(source_catalog)
    regional = tuple(k for k in enabled if k in _SHARED_INGUSHETIA_KEYS)
    if not regional:
        raise ValueError("No enabled regional Worker SQL source")

    profile = await service.profile_for_owner(owner_id)
    matches = []
    for key in regional:
        source = source_catalog.registry.get(key).source
        if not isinstance(source, FreshIngushetiaWorkerSource):
            raise ValueError("Regional subscription baseline requires Worker SQL")
        # This limit is specific to *fresh regional SQL*, never an upstream
        # network fetch or a widened limit on another tenant/source.
        candidates = await source.fetch(limit=1000)
        if len(candidates) >= 1000:
            # Cannot prove a full baseline beyond the supported bound:
            # fail rather than quietly classifying old entries as new.
            raise ValueError("Regional baseline exceeds approved bounded SQL scan")
        for notice in candidates:
            match = prefilter_notice(notice, profile)
            if match is not None:
                matches.append(match)

    others = tuple(k for k in enabled if k not in _SHARED_INGUSHETIA_KEYS)
    if others:
        other_matches, report = await service.fetch_matches_from_catalog(
            source_catalog, owner_id, source_keys=others,
        )
        # Refuse an incomplete first baseline instead of quietly promising
        # that unrelated previously-existing records will not be sent.
        if report.failures or not report.successful_sources:
            raise ValueError("Nonregional baseline sources unavailable")
        matches.extend(other_matches)
    # Production service keys EIS/Fabrikant by the canonical publisher
    # identity, so a shared original gets exactly one per-owner claim.
    return len(await service.claim_new(owner_id, matches))



async def monitor_on_handler(message: Message, monitoring_service: TenderMonitorService | None = None,
                             source_catalog: SourceCatalog | None = None) -> None:
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
        if service.settings.ru_background_catalog_enabled:
            keys = enabled_ru_catalog_keys(source_catalog)
            if not keys:
                raise ValueError("No explicitly enabled Russian source.")
            if getattr(service.settings, "ru_ingushetia_worker_sql_alerts_enabled", False):
                baseline_count = await _baseline_ingushetia_worker_sql(
                    service, source_catalog, message.from_user.id,
                )
            else:
                baseline_count, _ = await service.baseline_from_catalog(
                    source_catalog, message.from_user.id, source_keys=keys,
                )
        else:
            baseline_count = await service.baseline(message.from_user.id)
        await service.subscribe(message.from_user.id, message.chat.id)
    except (SourceError, MonitoringRepositoryError, ValueError):
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
                                 company_service: CompanyService | None = None,
                                 source_catalog: SourceCatalog | None = None) -> None:
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
    ru_mode = service.settings.ru_background_catalog_enabled
    ru_count = len(enabled_ru_catalog_keys(source_catalog)) if ru_mode else 0
    title = "📡 Мониторинг российских источников" if ru_mode else "📡 Мониторинг ЕИС"
    sources_line = (f"Включённых RU-источников: {ru_count}\n" if ru_mode
                    else f"RSS-поисков: {feed_count} ({feed_mode})\n")
    await message.answer(
        title + "\n"
        + f"Фоновый цикл: {global_state}\n"
        + f"Ваша подписка: {state}\n"
        + f"Активная компания: {company_line}\n"
        + f"Интервал: {service.settings.interval_seconds} сек.\n"
        + sources_line
        + "Pre-filter использует профиль и опубликованные данные источников."
    )


def _require_telegram_delivery_ack(response, chat_id: int) -> None:
    """Fail closed before marking a notice as seen.

    An awaited API call that returns no message, an invalid message ID, or
    confirmation for a different chat is not a verified send. Exception
    details are never exposed to logs, and the next monitoring cycle can
    retry the unchanged original notice.
    """
    message_id = getattr(response, "message_id", None)
    chat = getattr(response, "chat", None)
    returned_chat_id = getattr(chat, "id", None)
    if (type(message_id) is not int or message_id <= 0
            or type(returned_chat_id) is not int
            or returned_chat_id != chat_id):
        raise ValueError("Telegram message acknowledgement invalid")


async def monitor_loop(bot: Bot, service: TenderMonitorService,
                       stop_event: asyncio.Event, source_catalog: SourceCatalog | None = None) -> None:
    """Periodic source check. Russian catalog scanning is operator opt-in."""
    russian_keys = (enabled_ru_catalog_keys(source_catalog)
                    if service.settings.ru_background_catalog_enabled else ())
    if service.settings.ru_background_catalog_enabled and not russian_keys:
        raise ValueError("No approved Russian sources for the background monitor.")
    # Fixed, non-personalized regional listings can be obtained once each
    # cycle; never make O(number_of_subscriptions) upstream HTTP requests.
    # Per-tenant profile matching and confirmed Telegram receipts remain
    # individual. Other source combinations use the unchanged legacy path.
    regional_keys = tuple(k for k in russian_keys if k in _SHARED_INGUSHETIA_KEYS)
    tenant_specific_keys = tuple(k for k in russian_keys if k not in _SHARED_INGUSHETIA_KEYS)
    share_ingushetia = (
        bool(regional_keys)
        and callable(getattr(service, "fetch_matches_from_catalog_for_profile", None))
        and callable(getattr(service, "profile_for_owner", None))
    )
    local_regional_sql = (
        share_ingushetia
        and bool(getattr(service.settings, "ru_ingushetia_worker_sql_alerts_enabled", False))
    )
    if local_regional_sql:
        from app.sources.snapshots import FreshIngushetiaWorkerSource
        # Never silently fall back to one HTTP request per tenant when the
        # operator approved only Worker-SQL notifications.
        if any(
            not isinstance(source_catalog.registry.get(key).source, FreshIngushetiaWorkerSource)
            for key in regional_keys
        ):
            raise ValueError("Ingushetia Worker SQL alert catalog not installed")
    while not stop_event.is_set():
        try:
            subscriptions = await service.active_subscriptions()
            if subscriptions:
                shared_notices, shared_report = None, None
                if share_ingushetia and not local_regional_sql:
                    try:
                        # Fetch a fixed, bounded source-owned candidate pool
                        # ONCE per cycle. Limiting to settings.max_items here
                        # drops matches for tenants whose keyword appears only
                        # below the first handful of regional notices.
                        shared_matches, shared_report = await service.fetch_matches_from_catalog_for_profile(
                            source_catalog, None, source_keys=regional_keys, max_items=100,
                        )
                        shared_notices = tuple(match.notice for match in shared_matches)
                    except Exception:
                        # The shared request is outside the individual
                        # subscription handler. One transient upstream error
                        # must not terminate the entire background monitor.
                        # Nothing is delivered or marked seen in this cycle.
                        # Never log raw upstream errors or tenant secrets.
                        logger.warning("Ingushetia shared source poll failed; no alerts claimed.")
                        shared_notices = ()
                        # Report the failed fixed regional sources as unavailable
                        # without disclosing upstream exceptions or treating them
                        # as a successful empty result. Other individually searched
                        # sources remain available to each tenant.
                        shared_report = SimpleNamespace(
                            attempted_sources=regional_keys,
                            successful_sources=(),
                            failures=tuple(SimpleNamespace(source=k) for k in regional_keys),
                            total_failure=True,
                        )
                for subscription in subscriptions:
                    try:
                        if service.settings.ru_background_catalog_enabled:
                            if share_ingushetia:
                                profile = await service.profile_for_owner(subscription.owner_user_id)
                                # Filter the full bounded shared candidate pool
                                # per tenant. DO NOT apply max_items yet: the
                                # first max_items matches may all be marked seen,
                                # while a later genuine regional original is new.
                                # The per-source limit is enforced *after* the
                                # nonmutating unseen check below. Nothing here
                                # marks a notice sent before Telegram receipt.
                                if local_regional_sql:
                                    # Source is strictly read-only Worker SQL:
                                    # per-tenant local keyword prefilter can scan
                                    # 1000 RECENT candidates, including IDs
                                    # beyond the first hundred already-seen
                                    # matches. No per-user upstream HTTP.
                                    # In normal network mode preserve the single
                                    # shared real HTTP poll across all tenants.
                                    try:
                                        regional_matches, regional_report = await service.fetch_matches_from_catalog_for_profile(
                                            source_catalog, profile,
                                            source_keys=regional_keys, max_items=1000,
                                        )
                                        matches = list(regional_matches)
                                    except Exception:
                                        logger.warning("Ingushetia tenant Worker SQL search failed; no regional alerts claimed.")
                                        matches = []
                                        regional_report = SimpleNamespace(
                                            attempted_sources=regional_keys,
                                            successful_sources=(),
                                            failures=tuple(SimpleNamespace(source=k) for k in regional_keys),
                                            total_failure=True,
                                        )
                                    reports = [regional_report]
                                else:
                                    matches = []
                                    for notice in shared_notices:
                                        match = prefilter_notice(notice, profile)
                                        if match is not None:
                                            matches.append(match)
                                    reports = [shared_report]
                                if tenant_specific_keys:
                                    try:
                                        extra_matches, extra_report = await service.fetch_matches_from_catalog(
                                            source_catalog, subscription.owner_user_id,
                                            source_keys=tenant_specific_keys,
                                        )
                                        matches.extend(extra_matches)
                                    except Exception:
                                        # A failed personalized source cannot hide
                                        # already obtained matching regional notices.
                                        # The report and logs expose only registered
                                        # source keys, not tenant terms or URLs.
                                        logger.warning("Personalized RU source poll failed; regional results retained.")
                                        extra_report = SimpleNamespace(
                                            attempted_sources=tenant_specific_keys,
                                            successful_sources=(),
                                            failures=tuple(SimpleNamespace(source=k) for k in tenant_specific_keys),
                                            total_failure=True,
                                        )
                                    reports.append(extra_report)
                                if len(reports) == 1:
                                    report = reports[0]
                                else:
                                    report = SimpleNamespace(
                                        attempted_sources=tuple(
                                            k for part in reports for k in part.attempted_sources
                                        ),
                                        successful_sources=tuple(
                                            k for part in reports for k in part.successful_sources
                                        ),
                                        failures=tuple(
                                            failure for part in reports
                                            for failure in getattr(part, "failures", ())
                                        ),
                                        total_failure=all(part.total_failure for part in reports),
                                    )
                            else:
                                matches, report = await service.fetch_matches_from_catalog(
                                    source_catalog, subscription.owner_user_id,
                                    source_keys=russian_keys,
                                )
                            if not report.attempted_sources or report.total_failure:
                                logger.warning("Russian source scan unavailable; no alerts claimed.")
                                continue
                            # Preserve positive matches from a healthy source
                            # when another operator-enabled source is down.
                            # Only static catalog identities may enter logs:
                            # never log raw vendor errors, URLs, requests, user
                            # profiles, chat IDs or bot credentials.
                            failed_keys = tuple(sorted({
                                failure.source for failure in getattr(report, "failures", ())
                                if getattr(failure, "source", None) in russian_keys
                            }))
                            if failed_keys:
                                logger.warning(
                                    "Russian source partial outage: %s",
                                    ",".join(failed_keys),
                                )
                        else:
                            matches = await service.fetch_matches(subscription.owner_user_id)
                        new_matches = await service.unseen_matches(
                            subscription.owner_user_id, matches,
                        )
                        if share_ingushetia and service.settings.ru_background_catalog_enabled:
                            # Bound only regionally shared sources *after*
                            # dedup/seen filtering. Other tenant-personalized
                            # sources already carry their original fetch cap.
                            unseen_per_source = {}
                            bounded = []
                            for match in new_matches:
                                source = match.notice.source
                                if source in regional_keys:
                                    count = unseen_per_source.get(source, 0)
                                    if count >= service.settings.max_items:
                                        continue
                                    unseen_per_source[source] = count + 1
                                bounded.append(match)
                            new_matches = bounded
                        for match in new_matches[:service.settings.max_notifications_per_cycle]:
                            receipt = await bot.send_message(
                                subscription.chat_id,
                                "🆕 НОВАЯ ЗАКУПКА\n\n" + format_match(match),
                                disable_web_page_preview=True,
                            )
                            _require_telegram_delivery_ack(receipt, subscription.chat_id)
                            # Mark only after Telegram confirms delivery; a
                            # failed send must be retryable on the next cycle.
                            await service.claim_new(subscription.owner_user_id, [match])
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
