"""Business logic for source monitoring, pre-filtering and deduplication."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

from app.scoring.models import CompanyProfile
from app.sources.models import TenderNotice

from .config import MonitoringSettings
from .repository import MonitoringRepository, Subscription


class TenderSource(Protocol):
    async def fetch(self, limit: int = 20) -> list[TenderNotice]: ...


@dataclass(frozen=True)
class MonitorMatch:
    notice: TenderNotice
    reasons: tuple[str, ...]


def _contains(text: str, phrase: str) -> bool:
    return phrase.casefold().strip() in text.casefold()


def prefilter_notice(notice: TenderNotice, profile: CompanyProfile | None) -> MonitorMatch | None:
    if profile is None:
        return MonitorMatch(notice, ("Профиль компании не загружен — показано без pre-filter.",))

    reasons: list[str] = []
    text = " ".join(filter(None, [notice.title, notice.summary]))
    if profile.product_keywords:
        matched = [keyword for keyword in profile.product_keywords if _contains(text, keyword)]
        if not matched:
            return None
        reasons.append("Направление: " + ", ".join(matched[:5]))

    if notice.initial_price is not None and profile.max_contract_value is not None:
        if notice.initial_price > profile.max_contract_value and profile.hard_stop_on_budget:
            return None
        reasons.append("Бюджет известен и не превышает лимит профиля.")

    if notice.region and profile.allowed_regions:
        matches_region = any(_contains(notice.region, region) or _contains(region, notice.region)
                             for region in profile.allowed_regions)
        if not matches_region and profile.hard_stop_on_region:
            return None
        if matches_region:
            reasons.append("Регион совпадает с профилем.")

    if not reasons:
        reasons.append("Нет известного hard-stop несоответствия по данным RSS.")
    return MonitorMatch(notice, tuple(reasons))


class TenderMonitorService:
    def __init__(self, settings: MonitoringSettings, source: TenderSource,
                 repository: MonitoringRepository, profile: CompanyProfile | None):
        self.settings = settings
        self.source = source
        self.repository = repository
        self.profile = profile

    async def fetch_matches(self) -> list[MonitorMatch]:
        notices = await self.source.fetch(self.settings.max_items)
        result: list[MonitorMatch] = []
        for notice in notices:
            match = prefilter_notice(notice, self.profile)
            if match is not None:
                result.append(match)
        return result

    async def claim_new(self, owner_user_id: int, matches: list[MonitorMatch]) -> list[MonitorMatch]:
        new: list[MonitorMatch] = []
        for match in matches:
            notice = match.notice
            first = await asyncio.to_thread(
                self.repository.mark_seen, owner_user_id, notice.source, notice.external_id
            )
            if first:
                new.append(match)
        return new

    async def scan_new(self, owner_user_id: int) -> list[MonitorMatch]:
        return await self.claim_new(owner_user_id, await self.fetch_matches())

    async def baseline(self, owner_user_id: int) -> int:
        matches = await self.fetch_matches()
        count = 0
        for match in matches:
            notice = match.notice
            first = await asyncio.to_thread(
                self.repository.mark_seen, owner_user_id, notice.source, notice.external_id
            )
            count += int(first)
        return count

    async def subscribe(self, owner_user_id: int, chat_id: int) -> Subscription:
        return await asyncio.to_thread(self.repository.set_subscription, owner_user_id, chat_id, True)

    async def unsubscribe(self, owner_user_id: int, chat_id: int) -> Subscription:
        return await asyncio.to_thread(self.repository.set_subscription, owner_user_id, chat_id, False)

    async def subscription(self, owner_user_id: int) -> Subscription | None:
        return await asyncio.to_thread(self.repository.get_subscription, owner_user_id)

    async def active_subscriptions(self) -> list[Subscription]:
        return await asyncio.to_thread(self.repository.list_active)
