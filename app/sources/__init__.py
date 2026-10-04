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
from .catalog import (
    SourceCatalog,
    build_source_catalog,
)
from .ted_api import (
    TED_FIELDS,
    TED_SEARCH_URL,
    TedApiSource,
    parse_ted_search_response,
)
from .sam_gov_api import (
    SAM_GOV_SEARCH_URL,
    SamGovApiSource,
    parse_sam_gov_response,
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
    "SourceCatalog",
    "build_source_catalog",
    "TED_FIELDS",
    "TED_SEARCH_URL",
    "TedApiSource",
    "parse_ted_search_response",
    "SAM_GOV_SEARCH_URL",
    "SamGovApiSource",
    "parse_sam_gov_response",
]
