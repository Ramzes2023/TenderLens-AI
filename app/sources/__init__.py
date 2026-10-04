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
    SourceRegistration,
    SourceRegistry,
    SourceRegistryError,
)
from .multi import (
    MultiSourceFetcher,
    MultiSourceFetchReport,
    SourceFailure,
)

__all__ = [
    "TenderSource",
    "TenderNotice",
    "EisRssSource",
    "SourceError",
    "build_eis_rss_url",
    "build_eis_rss_urls",
    "SourceRegistration",
    "SourceRegistry",
    "SourceRegistryError",
    "MultiSourceFetcher",
    "MultiSourceFetchReport",
    "SourceFailure",
]
