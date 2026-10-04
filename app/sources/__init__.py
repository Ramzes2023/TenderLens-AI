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
from .uk_fts_api import (
    UK_FTS_SEARCH_URL,
    UkFindTenderApiSource,
    parse_uk_fts_response,
)
from .canada_buys_dataset import (
    CANADABUYS_OPEN_TENDERS_URL,
    CANADABUYS_SEARCH_URL,
    CanadaBuysDatasetSource,
    parse_canadabuys_csv,
)
from .austender_rss import (
    AUSTENDER_ATM_BASE_URL,
    AUSTENDER_RSS_URL,
    AusTenderRssItem,
    AusTenderRssSource,
    parse_austender_detail_page,
    parse_austender_rss,
)
from .nz_gets_rss import (
    NZ_GETS_RSS_URL,
    NzGetsRssSource,
    parse_nz_gets_rss,
)
from .za_etenders import (
    ZA_ETENDERS_ACTIVE_TENDERS_URL,
    ZA_ETENDERS_OPPORTUNITIES_URL,
    ZaETendersSource,
    parse_za_etenders_response,
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
    "UK_FTS_SEARCH_URL",
    "UkFindTenderApiSource",
    "parse_uk_fts_response",
    "CANADABUYS_OPEN_TENDERS_URL",
    "CANADABUYS_SEARCH_URL",
    "CanadaBuysDatasetSource",
    "parse_canadabuys_csv",
    "AUSTENDER_ATM_BASE_URL",
    "AUSTENDER_RSS_URL",
    "AusTenderRssItem",
    "AusTenderRssSource",
    "parse_austender_detail_page",
    "parse_austender_rss",
    "NZ_GETS_RSS_URL",
    "NzGetsRssSource",
    "parse_nz_gets_rss",

    "ZA_ETENDERS_ACTIVE_TENDERS_URL",
    "ZA_ETENDERS_OPPORTUNITIES_URL",
    "ZaETendersSource",
    "parse_za_etenders_response",
]
