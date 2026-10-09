"""Business logic for source monitoring, profile filtering and deduplication."""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from app.currency import normalize_currency_code
from app.scoring.models import CompanyProfile
from app.sources.base import TenderSource
from app.sources.models import TenderNotice

if TYPE_CHECKING:
    from app.sources.catalog import SourceCatalog
    from app.sources.multi import MultiSourceFetchReport

from .config import MonitoringSettings
from .repository import MonitoringRepository, Subscription


@dataclass(frozen=True)
class MonitorMatch:
    notice: TenderNotice
    reasons: tuple[str, ...]


def _contains(text: str, phrase: str) -> bool:
    return phrase.casefold().strip() in text.casefold()





def _term_match(
    text: str,
    term: str,
) -> bool:
    """
    Unicode word / phrase matcher.

    Latin words stay exact:
        gold != golden
        gold != goldhofer

    Russian words use conservative inflection stems:
        насосы == насосов
        клапаны == клапанов
        оборудование == оборудования
        профиль == профиля
    """
    suffixes = (
        "\u0438\u044f\u043c\u0438",
        "\u044f\u043c\u0438",
        "\u0430\u043c\u0438",
        "\u043e\u0433\u043e",
        "\u0435\u043c\u0443",
        "\u043e\u043c\u0443",
        "\u044b\u043c\u0438",
        "\u0438\u043c\u0438",
        "\u0438\u044f\u0445",
        "\u0430\u0445",
        "\u044f\u0445",
        "\u043e\u0432",
        "\u0435\u0432",
        "\u0435\u0439",
        "\u0430\u043c",
        "\u044f\u043c",
        "\u043e\u043c",
        "\u0435\u043c",
        "\u043e\u0439",
        "\u0438\u0439",
        "\u044b\u0439",
        "\u0430\u044f",
        "\u044f\u044f",
        "\u043e\u0435",
        "\u0435\u0435",
        "\u044b\u0435",
        "\u0438\u0435",
        "\u0438\u044f",
        "\u044b\u0445",
        "\u0438\u0445",
        "\u0443\u044e",
        "\u044e\u044e",
        "\u0430",
        "\u044f",
        "\u044b",
        "\u0438",
        "\u0435",
        "\u043e",
        "\u0443",
        "\u044e",
        "\u044c",
    )

    def normalize_token(
        token: str,
    ) -> str:
        value = (
            token.casefold()
            .replace(
                "\u0451",
                "\u0435",
            )
        )

        is_russian = (
            bool(value)
            and all(
                0x0430
                <= ord(char)
                <= 0x044F
                for char in value
            )
        )

        if not is_russian:
            return value

        for suffix in suffixes:
            if (
                value.endswith(suffix)
                and (
                    len(value)
                    - len(suffix)
                ) >= 4
            ):
                return value[
                    :-len(suffix)
                ]

        return value

    haystack = [
        normalize_token(token)
        for token in re.findall(
            r"[^\W_]+",
            text or "",
            flags=re.UNICODE,
        )
    ]

    needle = [
        normalize_token(token)
        for token in re.findall(
            r"[^\W_]+",
            term or "",
            flags=re.UNICODE,
        )
    ]

    if not needle:
        return False

    width = len(needle)

    if width > len(haystack):
        return False

    for index in range(
        len(haystack)
        - width
        + 1
    ):
        if (
            haystack[
                index:
                index + width
            ]
            == needle
        ):
            return True

    return False





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

    currency = normalize_currency_code(
        notice.currency
    )

    accepted_currencies = {
        normalized
        for item in profile.accepted_currencies
        if (
            normalized
            := normalize_currency_code(
                item
            )
        )
    }

    budget_comparable = (
        notice.initial_price is not None
        and currency is not None
        and len(accepted_currencies) == 1
        and currency in accepted_currencies
    )

    if (
        notice.initial_price is not None
        and currency is not None
        and accepted_currencies
        and currency not in accepted_currencies
    ):
        reasons.append(
            "\u0412\u0430\u043b\u044e\u0442\u0430 "
            "\u043e\u0442\u043b\u0438\u0447\u0430\u0435\u0442\u0441\u044f "
            "\u043e\u0442 \u0432\u0430\u043b\u044e\u0442\u044b "
            "\u0431\u044e\u0434\u0436\u0435\u0442\u0430 "
            "\u043f\u0440\u043e\u0444\u0438\u043b\u044f; "
            "\u0441\u0443\u043c\u043c\u044b "
            "\u043d\u0430\u043f\u0440\u044f\u043c\u0443\u044e "
            "\u043d\u0435 "
            "\u0441\u0440\u0430\u0432\u043d\u0438\u0432\u0430\u043b\u0438\u0441\u044c."
        )

    if (
        notice.initial_price is not None
        and currency is None
    ):
        reasons.append(
            "\u0421\u0442\u043e\u0438\u043c\u043e\u0441\u0442\u044c "
            "\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u0430 "
            "\u0431\u0435\u0437 \u0432\u0430\u043b\u044e\u0442\u044b; "
            "\u0431\u044e\u0434\u0436\u0435\u0442 "
            "\u043d\u0430\u043f\u0440\u044f\u043c\u0443\u044e "
            "\u043d\u0435 "
            "\u0441\u0440\u0430\u0432\u043d\u0438\u0432\u0430\u043b\u0441\u044f."
        )

    if budget_comparable:
        if (
            profile.min_contract_value is not None
            and notice.initial_price
            < profile.min_contract_value
        ):
            if profile.hard_stop_on_budget:
                return None

            reasons.append(
                "Стоимость ниже целевого "
                "минимума профиля."
            )

        if profile.max_contract_value is not None:
            if (
                notice.initial_price
                > profile.max_contract_value
                and profile.hard_stop_on_budget
            ):
                return None

            if (
                notice.initial_price
                <= profile.max_contract_value
            ):
                reasons.append(
                    "Бюджет известен и "
                    "не превышает лимит профиля."
                )

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

    async def fetch_matches_from_catalog_for_profile(
        self,
        catalog: "SourceCatalog",
        profile: CompanyProfile | None,
    ) -> tuple[
        list[MonitorMatch],
        "MultiSourceFetchReport",
    ]:
        """Fetch global sources and pre-filter against an explicit profile."""

        search_terms = (
            tuple(profile.monitoring_keywords)
            if profile is not None
            else ()
        )

        report = await catalog.fetch(
            limit_per_source=self.settings.max_items,
            search_terms=search_terms,
            max_eis_feeds=self.settings.profile_feed_limit,
        )

        matches: list[MonitorMatch] = []

        for notice in report.notices:
            match = prefilter_notice(
                notice,
                profile,
            )

            if match is not None:
                matches.append(match)

        return matches, report

    async def fetch_matches_from_catalog(
        self,
        catalog: "SourceCatalog",
        owner_user_id: int | None = None,
    ) -> tuple[
        list[MonitorMatch],
        "MultiSourceFetchReport",
    ]:
        """Fetch global sources using the resolved owner profile."""

        profile = await self.profile_for_owner(
            owner_user_id
        )

        return await self.fetch_matches_from_catalog_for_profile(
            catalog,
            profile,
        )

    async def scan_new_from_catalog(
        self,
        catalog: "SourceCatalog",
        owner_user_id: int,
    ) -> tuple[
        list[MonitorMatch],
        "MultiSourceFetchReport",
    ]:
        matches, report = (
            await self.fetch_matches_from_catalog(
                catalog,
                owner_user_id,
            )
        )

        new_matches = await self.claim_new(
            owner_user_id,
            matches,
        )

        return new_matches, report

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
