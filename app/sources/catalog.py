"""Configured procurement source catalog for VALYQON AI."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .eis_rss import EisRssSource
from .multi import MultiSourceFetcher
from .registry import (
    SourceCapabilities,
    SourceRegistration,
    SourceRegistry,
    SourceTransport,
)

if TYPE_CHECKING:
    from app.monitoring.config import MonitoringSettings


@dataclass(frozen=True, slots=True)
class SourceCatalog:
    """Runtime catalog containing configured adapters and orchestration."""

    registry: SourceRegistry
    fetcher: MultiSourceFetcher

    @property
    def enabled_keys(self) -> tuple[str, ...]:
        return self.registry.keys(enabled_only=True)


def build_source_catalog(
    settings: "MonitoringSettings",
) -> SourceCatalog:
    """Build the canonical runtime source catalog.

    EIS remains the first registered source for backwards compatibility.
    Future international adapters are added here without changing consumers.
    """

    eis = EisRssSource(
        urls=settings.eis_rss_urls,
        timeout=settings.request_timeout,
        ca_bundle_file=settings.ca_bundle_file,
        name="eis",
    )

    registry = SourceRegistry(
        [
            SourceRegistration(
                key="eis",
                display_name=(
                    "Russian Unified Procurement Information System (EIS)"
                ),
                source=eis,
                transport=SourceTransport.RSS,
                jurisdictions=("RU",),
                languages=("ru",),
                homepage_url="https://zakupki.gov.ru/",
                official=True,
                enabled=settings.source_configured,
                capabilities=SourceCapabilities(
                    keyword_search=settings.profile_feeds_enabled,
                    pagination=False,
                    documents=False,
                    incremental_sync=False,
                    authentication_required=False,
                ),
            )
        ]
    )

    return SourceCatalog(
        registry=registry,
        fetcher=MultiSourceFetcher(registry),
    )


__all__ = [
    "SourceCatalog",
    "build_source_catalog",
]
