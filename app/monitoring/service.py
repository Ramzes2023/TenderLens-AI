"""Business logic for source monitoring, profile filtering and deduplication."""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Callable

from app.scoring.models import CompanyProfile
from app.sources.base import TenderSource
from app.sources.models import TenderNotice

from .config import MonitoringSettings
from .repository import MonitoringRepository, Subscription


@dataclass(frozen=True)
class MonitorMatch:
    notice: TenderNotice
    reasons: tuple[str, ...]


def _contains(text: str, phrase: str) -> bool:
    return phrase.casefold().strip() in text.casefold()


def _term_match(text: str, phrase: str) -> bool:
    """Conservative token-prefix match for RSS pre-filtering.

    EIS morphology can return inflected Russian forms (e.g. ``профиль`` /
    ``профиля``), so an exact substring alone is too brittle for discovery.
    """
    if _contains(text, phrase):
        return True
    hay = re.findall(r"[0-9a-zа-яё]+", text.casefold())
    needles = re.findall(r"[0-9a-zа-яё]+", phrase.casefold())
    needles = [item for item in needles if len(item) >= 4]
    if not needles:
        return False
    for needle in needles:
        prefix_len = min(6, len(needle))
        prefix = needle[:prefix_len]
        if not any(token.startswith(prefix) for token in hay):
            return False
    return True


def prefilter_notice(notice: TenderNotice, profile: CompanyProfile | None) -> MonitorMatch | None:
    if profile is None:
        return MonitorMatch(notice, ("Профиль компании не загружен — показано без pre-filter.",))

    reasons: list[str] = []
    text = " ".join(filter(None, [notice.title, notice.summary]))
    if profile.excluded_keywords:
        excluded = [keyword for keyword in profile.excluded_keywords if _term_match(text, keyword)]
        if excluded:
            return None

    keywords = profile.monitoring_keywords
    if keywords:
        matched = [keyword for keyword in keywords if _term_match(text, keyword)]
        if not matched:
            return None
        reasons.append("Направление: " + ", ".join(matched[:5]))

    if notice.initial_price is not None:
        if profile.min_contract_value is not None and notice.initial_price < profile.min_contract_value:
            if profile.hard_stop_on_budget:
                return None
            reasons.append("Стоимость ниже целевого минимума профиля.")
        if profile.max_contract_value is not None:
            if notice.initial_price > profile.max_contract_value and profile.hard_stop_on_budget:
                return None
            if notice.initial_price <= profile.max_contract_value:
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
                 repository: MonitoringRepository, profile: CompanyProfile | None,
                 profile_resolver: Callable[[int], CompanyProfile | None] | None = None,
                 scope_resolver: Callable[[int], str | None] | None = None):
        self.settings = settings
        self.source = source
        self.repository = repository
        self.profile = profile
        self.profile_resolver = profile_resolver
        self.scope_resolver = scope_resolver

    async def profile_for_owner(self, owner_user_id: int | None) -> CompanyProfile | None:
        if owner_user_id is not None and self.profile_resolver is not None:
            return await asyncio.to_thread(self.profile_resolver, owner_user_id)
        return self.profile

    def _source_for_profile(self, profile: CompanyProfile | None) -> TenderSource:
        if (profile is not None and self.settings.profile_feeds_enabled
                and profile.monitoring_keywords and hasattr(self.source, "for_search_terms")):
            return self.source.for_search_terms(  # type: ignore[attr-defined]
                profile.monitoring_keywords,
                max_feeds=self.settings.profile_feed_limit,
            )
        return self.source

    async def fetch_matches_for_profile(
        self,
        profile: CompanyProfile | None,
    ) -> list[MonitorMatch]:
        source = self._source_for_profile(profile)
        notices = await source.fetch(self.settings.max_items)
        result: list[MonitorMatch] = []

        for notice in notices:
            match = prefilter_notice(
                notice,
                profile,
            )
            if match is not None:
                result.append(match)

        return result

    async def fetch_matches(
        self,
        owner_user_id: int | None = None,
    ) -> list[MonitorMatch]:
        profile = await self.profile_for_owner(owner_user_id)
        return await self.fetch_matches_for_profile(profile)

    async def claim_new_for_organization(
        self,
        *,
        account_id: int,
        organization_id: int,
        owner_user_id: int,
        company_scope: str,
        matches: list[MonitorMatch],
    ) -> list[MonitorMatch]:
        new: list[MonitorMatch] = []

        for match in matches:
            notice = match.notice
            dedup_source = (
                f"{notice.source}:company:{company_scope}"
            )

            first = await asyncio.to_thread(
                self.repository.mark_seen_for_organization,
                account_id=account_id,
                organization_id=organization_id,
                owner_user_id=owner_user_id,
                source=dedup_source,
                external_id=notice.external_id,
            )

            if first:
                new.append(match)

        return new

    async def scan_new_for_organization(
        self,
        *,
        account_id: int,
        organization_id: int,
        owner_user_id: int,
        profile: CompanyProfile,
        company_scope: str,
    ) -> list[MonitorMatch]:
        matches = await self.fetch_matches_for_profile(profile)

        return await self.claim_new_for_organization(
            account_id=account_id,
            organization_id=organization_id,
            owner_user_id=owner_user_id,
            company_scope=company_scope,
            matches=matches,
        )

    async def dedup_source(self, owner_user_id: int, source: str) -> str:
        if self.scope_resolver is None:
            return source
        scope = await asyncio.to_thread(self.scope_resolver, owner_user_id)
        return f"{source}:company:{scope}" if scope else source

    async def claim_new(self, owner_user_id: int, matches: list[MonitorMatch]) -> list[MonitorMatch]:
        new: list[MonitorMatch] = []
        for match in matches:
            notice = match.notice
            dedup_source = await self.dedup_source(owner_user_id, notice.source)
            first = await asyncio.to_thread(
                self.repository.mark_seen, owner_user_id, dedup_source, notice.external_id
            )
            if first:
                new.append(match)
        return new

    async def scan_new(self, owner_user_id: int) -> list[MonitorMatch]:
        return await self.claim_new(owner_user_id, await self.fetch_matches(owner_user_id))

    async def baseline(self, owner_user_id: int) -> int:
        matches = await self.fetch_matches(owner_user_id)
        count = 0
        for match in matches:
            notice = match.notice
            dedup_source = await self.dedup_source(owner_user_id, notice.source)
            first = await asyncio.to_thread(
                self.repository.mark_seen, owner_user_id, dedup_source, notice.external_id
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
