"""Tender source adapters and orchestration primitives."""
from .base import TenderSource
from .models import TenderNotice
from .eis_rss import (
    EisRssSource,
    SourceError,
    build_eis_rss_url,
    build_eis_rss_urls,
)
from .registry import (
    SourceCapabilities,
    SourceMetadata,
    SourceRegistration,
    SourceRegistry,
    SourceRegistryError,
    SourceTransport,
)
from .multi import (
    MultiSourceFetcher,
    MultiSourceFetchReport,
    SourceFailure,
    SourceRunState,
    SourceRunStatus,
)

__all__ = [
    "TenderSource",
    "TenderNotice",
    "EisRssSource",
    "SourceError",
    "build_eis_rss_url",
    "build_eis_rss_urls",
    "SourceCapabilities",
    "SourceMetadata",
    "SourceRegistration",
    "SourceRegistry",
    "SourceRegistryError",
    "SourceTransport",
    "MultiSourceFetcher",
    "MultiSourceFetchReport",
    "SourceFailure",
    "SourceRunState",
    "SourceRunStatus",
]
