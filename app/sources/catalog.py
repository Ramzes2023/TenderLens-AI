"""Configured procurement source catalog for VALYQON AI."""
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Iterable

from .austender_rss import AusTenderRssSource
from .canada_buys_dataset import CanadaBuysDatasetSource
from .eis_rss import EisRssSource, SourceError
from .india_cppp import IndiaCpppSource
from .kz_goszakup import KazakhstanGoszakupApiSource
from .multi import MultiSourceFetcher, MultiSourceFetchReport
from .nz_gets_rss import NzGetsRssSource
from .registry import (
    SourceCapabilities,
    SourceRegistration,
    SourceRegistry,
    SourceTransport,
)
from .sam_gov_api import SamGovApiSource
from .ted_api import TedApiSource
from .uk_fts_api import UkFindTenderApiSource
from .za_etenders import ZaETendersSource


if TYPE_CHECKING:
    from app.monitoring.config import MonitoringSettings


@dataclass(frozen=True)
class _UnavailableSource:
    """Disabled authenticated adapter placeholder."""

    name: str
    message: str

    async def fetch(self, limit: int = 20):
        raise SourceError(self.message)


@dataclass(frozen=True, slots=True)
class SourceCatalog:
    """Runtime catalog containing configured adapters and orchestration."""

    registry: SourceRegistry
    fetcher: MultiSourceFetcher

    @property
    def enabled_keys(self) -> tuple[str, ...]:
        return self.registry.keys(
            enabled_only=True
        )

    async def fetch(
        self,
        *,
        limit_per_source: int = 20,
        source_keys: Iterable[str] | None = None,
        search_terms: Iterable[str] = (),
        max_eis_feeds: int = 5,
    ) -> MultiSourceFetchReport:
        """Fetch enabled procurement sources through one orchestration path.

        EIS can still generate profile-specific RSS searches while all other
        Phase23 adapters use their canonical public discovery behavior.
        """

        terms = tuple(
            value
            for value in (
                str(item).strip()
                for item in search_terms
            )
            if value
        )

        if not terms:
            return await self.fetcher.fetch(
                limit_per_source=limit_per_source,
                source_keys=source_keys,
            )

        registrations: list[
            SourceRegistration
        ] = []

        for registration in self.registry.registrations():
            source = registration.source

            if (
                registration.key == "eis"
                and registration.enabled
                and hasattr(
                    source,
                    "for_search_terms",
                )
            ):
                source = source.for_search_terms(
                    terms,
                    max_feeds=max(
                        1,
                        min(
                            int(max_eis_feeds),
                            20,
                        ),
                    ),
                )

                registration = replace(
                    registration,
                    source=source,
                )

            registrations.append(
                registration
            )

        registry = SourceRegistry(
            registrations
        )

        fetcher = MultiSourceFetcher(
            registry,
            concurrency=self.fetcher.concurrency,
        )

        return await fetcher.fetch(
            limit_per_source=limit_per_source,
            source_keys=source_keys,
        )


def build_source_catalog(
    settings: "MonitoringSettings",
) -> SourceCatalog:
    """Build the canonical VALYQON procurement source catalog."""

    timeout = settings.request_timeout

    sam_key = os.environ.get(
        "SAM_GOV_API_KEY",
        "",
    ).strip()

    kz_token = os.environ.get(
        "KZ_GOSZAKUP_API_TOKEN",
        "",
    ).strip()

    eis = EisRssSource(
        urls=settings.eis_rss_urls,
        timeout=timeout,
        ca_bundle_file=settings.ca_bundle_file,
        name="eis",
    )

    sam_source = (
        SamGovApiSource(
            api_key=sam_key,
            timeout=timeout,
        )
        if sam_key
        else _UnavailableSource(
            name="sam_gov",
            message=(
                "SAM.gov API key is not configured."
            ),
        )
    )

    kz_source = (
        KazakhstanGoszakupApiSource(
            api_token=kz_token,
            timeout=timeout,
        )
        if kz_token
        else _UnavailableSource(
            name="kz_goszakup",
            message=(
                "Kazakhstan procurement API "
                "token is not configured."
            ),
        )
    )

    registry = SourceRegistry(
        [
            SourceRegistration(
                key="eis",
                display_name=(
                    "Russian Unified Procurement "
                    "Information System (EIS)"
                ),
                source=eis,
                transport=SourceTransport.RSS,
                jurisdictions=("RU",),
                languages=("ru",),
                homepage_url=(
                    "https://zakupki.gov.ru/"
                ),
                official=True,
                enabled=settings.source_configured,
                capabilities=SourceCapabilities(
                    keyword_search=(
                        settings.profile_feeds_enabled
                    ),
                    pagination=False,
                    documents=False,
                    incremental_sync=False,
                    authentication_required=False,
                ),
            ),
            SourceRegistration(
                key="ted",
                display_name=(
                    "Tenders Electronic Daily (TED)"
                ),
                source=TedApiSource(
                    timeout=timeout,
                ),
                transport=SourceTransport.API,
                jurisdictions=("EU",),
                languages=(),
                homepage_url=(
                    "https://ted.europa.eu/"
                ),
                official=True,
                enabled=True,
                capabilities=SourceCapabilities(),
            ),
            SourceRegistration(
                key="sam_gov",
                display_name="SAM.gov",
                source=sam_source,
                transport=SourceTransport.API,
                jurisdictions=("US",),
                languages=("en",),
                homepage_url="https://sam.gov/",
                official=True,
                enabled=bool(sam_key),
                capabilities=SourceCapabilities(
                    authentication_required=True,
                ),
            ),
            SourceRegistration(
                key="uk_fts",
                display_name="UK Find a Tender",
                source=UkFindTenderApiSource(
                    timeout=timeout,
                ),
                transport=SourceTransport.API,
                jurisdictions=("GB",),
                languages=("en",),
                homepage_url=(
                    "https://www.find-tender."
                    "service.gov.uk/"
                ),
                official=True,
                enabled=True,
                capabilities=SourceCapabilities(),
            ),
            SourceRegistration(
                key="canada_buys",
                display_name="CanadaBuys",
                source=CanadaBuysDatasetSource(
                    timeout=timeout,
                ),
                transport=SourceTransport.DATASET,
                jurisdictions=("CA",),
                languages=("en", "fr"),
                homepage_url=(
                    "https://canadabuys.canada.ca/"
                ),
                official=True,
                enabled=True,
                capabilities=SourceCapabilities(),
            ),
            SourceRegistration(
                key="austender",
                display_name="AusTender",
                source=AusTenderRssSource(
                    timeout=timeout,
                ),
                transport=SourceTransport.RSS,
                jurisdictions=("AU",),
                languages=("en",),
                homepage_url=(
                    "https://www.tenders.gov.au/"
                ),
                official=True,
                enabled=True,
                capabilities=SourceCapabilities(),
            ),
            SourceRegistration(
                key="nz_gets",
                display_name=(
                    "New Zealand Government "
                    "Electronic Tenders Service"
                ),
                source=NzGetsRssSource(
                    timeout=timeout,
                ),
                transport=SourceTransport.RSS,
                jurisdictions=("NZ",),
                languages=("en",),
                homepage_url=(
                    "https://www.gets.govt.nz/"
                ),
                official=True,
                enabled=True,
                capabilities=SourceCapabilities(),
            ),
            SourceRegistration(
                key="za_etenders",
                display_name=(
                    "South Africa eTenders"
                ),
                source=ZaETendersSource(
                    timeout=timeout,
                ),
                transport=SourceTransport.API,
                jurisdictions=("ZA",),
                languages=("en",),
                homepage_url=(
                    "https://www.etenders.gov.za/"
                ),
                official=True,
                enabled=True,
                capabilities=SourceCapabilities(),
            ),
            SourceRegistration(
                key="india_cppp",
                display_name=(
                    "India Central Public "
                    "Procurement Portal"
                ),
                source=IndiaCpppSource(
                    timeout=timeout,
                ),
                transport=SourceTransport.HTML,
                jurisdictions=("IN",),
                languages=("en",),
                homepage_url=(
                    "https://eprocure.gov.in/"
                    "eprocure/app"
                ),
                official=True,
                enabled=True,
                capabilities=SourceCapabilities(
                    pagination=True,
                ),
            ),
            SourceRegistration(
                key="kz_goszakup",
                display_name=(
                    "Kazakhstan Public Procurement"
                ),
                source=kz_source,
                transport=SourceTransport.API,
                jurisdictions=("KZ",),
                languages=("ru", "kk"),
                homepage_url=(
                    "https://goszakup.gov.kz/"
                ),
                official=True,
                enabled=bool(kz_token),
                capabilities=SourceCapabilities(
                    pagination=True,
                    authentication_required=True,
                ),
            ),
        ]
    )

    return SourceCatalog(
        registry=registry,
        fetcher=MultiSourceFetcher(
            registry
        ),
    )


__all__ = [
    "SourceCatalog",
    "build_source_catalog",
]
