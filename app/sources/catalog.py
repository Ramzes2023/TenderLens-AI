"""Configured procurement source catalog for VALYQON AI."""
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Iterable

from .am_armeps import ArmeniaArmepsSource
from .tj_eprocurement import TajikistanEprocurementSource
from .kg_gov_legacy import KyrgyzstanGovLegacySource
from .kz_gov_html import KazakhstanGovHtmlSource
from .uz_uzex import UzbekistanUzexSource
from .md_achizitii import MoldovaAchizitiiSource
from .az_adif_small import AzerbaijanAdifSmallSource
from .asia_public import ASIA_RSS_FEEDS, AsiaPublicSource
from .jp_jetro_bid_rss import JetroBidRssSource, RSS_URL as JETRO_BID_RSS_URL
from .hk_hyd_tenders import HighwaysTendersSource, RSS_URL as HYD_TENDERS_RSS_URL
from .sg_gebiz_rss import FEEDS as SG_GEBIZ_RSS_FEEDS, SingaporeGeBizRssSource
from .hk_hkma_tender import HKMATenderSource, API_URL as HKMA_TENDER_API_URL
from .austender_rss import AusTenderRssSource
from .b2b_center import B2BCenterSource
from .tektorg_public_html import TekTorgPublicSource
from .gpb_etp_public import GpbEtpPublicSource
from .lenobl_small_public import LenoblSmallPublicSource
from .nmck_native_public import NmckNativePublicSource
from .stan_commercial_public import StanCommercialPublicSource
from .canada_buys_dataset import CanadaBuysDatasetSource
from .eis_rss import EisRssSource, SourceError
from .eis_44_public_html import Eis44PublicHtmlSource
from .eis_223_rss import Eis223RssSource
from .india_cppp import IndiaCpppSource
from .india_epublish import IndiaEpublishSource, LIST_URL as INDIA_EPUBLISH_LIST_URL
from .uae_mof_rfqs import UAEMinistryFinanceSource, URL as UAE_MOF_URL
from .kz_goszakup import KazakhstanGoszakupApiSource
from .multi import MultiSourceFetcher, MultiSourceFetchReport
from .mikroton_tender import MikrotonTenderSource
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
from .world_bank import WorldBankSource
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

            # A snapshot fetch is always local. Apply profile terms to every
            # locally-searchable stored source, not just EIS/TED. Never send
            # these terms to live remote adapters without explicit support.
            if registration.enabled and getattr(source, 'local_keyword_search', False) and hasattr(source, 'for_search_terms'):
                registration = replace(registration, source=source.for_search_terms(terms))
            elif registration.key == 'ted' and registration.enabled and hasattr(source, 'for_search_terms'):
                registration = replace(registration, source=source.for_search_terms(terms))

            elif (
                registration.key in {"eis", "eis_223"}
                and registration.enabled
                and (registration.key == "eis" or registration.capabilities.keyword_search
                     or getattr(source, "local_keyword_search", False))
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

            # Persisted SnapshotSource wrappers expose local_keyword_search.
            # EIS/223 and TED already specialize above; all other snapshot
            # sources must receive the user's terms as well.  Never send
            # profile terms to live public-source adapters implicitly.
            if (
                registration.enabled
                and registration.key not in {"eis", "eis_223", "ted"}
                and getattr(registration.source, "local_keyword_search", False)
                and hasattr(registration.source, "for_search_terms")
            ):
                registration = replace(
                    registration,
                    source=registration.source.for_search_terms(terms),
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
        direct=settings.eis_direct_enabled,
        system_trust=settings.eis_system_trust_enabled,
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
                capabilities=SourceCapabilities(keyword_search=True, pagination=True),
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
                capabilities=SourceCapabilities(pagination=True, incremental_sync=True),
            ),
            SourceRegistration(
                key='world_bank', display_name='World Bank Group — Finances One',
                source=WorldBankSource(timeout=timeout), transport=SourceTransport.DATASET,
                jurisdictions=('GLOBAL',), languages=('en',),
                homepage_url='https://financesone.worldbank.org/api-explorer?id=DS00979',
                official=True, enabled=True,
                capabilities=SourceCapabilities(pagination=True, incremental_sync=True),
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

    # Reviewed public CIS adapters remain disabled; activation is a separate decision.
    for key, display, adapter, country, languages, homepage, pagination in (
        ("am_armeps", "Armenia ARMEPS", ArmeniaArmepsSource, "AM", ("en", "hy"),
         "https://eauction.armeps.am/en/public/tender/", True),
        ("tj_eprocurement", "Tajikistan public procurement", TajikistanEprocurementSource,
         "TJ", ("ru", "tg"), "https://eprocurement.gov.tj/ru/searchanno", False),
    ):
        registry.register(SourceRegistration(
            key=key, display_name=display, source=adapter(timeout=min(timeout, 30)),
            transport=SourceTransport.HTML, jurisdictions=(country,), languages=languages,
            homepage_url=homepage, official=True, enabled=False,
            capabilities=SourceCapabilities(pagination=pagination),
        ))

    # Verified Uzbekistan UZEX source; disabled until explicit operator activation.
    registry.register(SourceRegistration(
        key="uz_uzex",
        display_name="Uzbekistan UZEX public tenders and selections",
        source=UzbekistanUzexSource(timeout=min(timeout, 30)),
        transport=SourceTransport.API,
        jurisdictions=("UZ",),
        languages=("uz", "ru"),
        homepage_url="https://etender.uzex.uz/",
        official=True,
        enabled=False,
        capabilities=SourceCapabilities(pagination=False, incremental_sync=False),
    ))

    # Official Kyrgyz server-rendered government listing; operator activation separate.
    registry.register(SourceRegistration(
        key="kg_gov_legacy",
        display_name="Kyrgyzstan government public tender notices",
        source=KyrgyzstanGovLegacySource(timeout=min(timeout, 30)),
        transport=SourceTransport.HTML,
        jurisdictions=("KG",),
        languages=("ru", "ky"),
        homepage_url="https://zakupki.gov.kg/popp/view/order/list.xhtml",
        official=True,
        enabled=False,
        capabilities=SourceCapabilities(pagination=False, incremental_sync=False),
    ))

    # Accredited Moldova marketplace, NOT the government OCDS API.
    # Register disabled until explicitly authorized by operator.
    registry.register(SourceRegistration(
        key="md_achizitii",
        display_name="Moldova Achizitii.md public procurement marketplace",
        source=MoldovaAchizitiiSource(timeout=min(timeout, 30)),
        transport=SourceTransport.HTML,
        jurisdictions=("MD",),
        languages=("ro", "ru"),
        homepage_url="https://achizitii.md/ro/",
        official=False,
        enabled=False,
        capabilities=SourceCapabilities(pagination=False, incremental_sync=False),
    ))

    # Independent official small public quotation notices: ADIF Azerbaijan.
    # This is NOT the national procurement API. Activation remains disabled
    # until strictly green official HTTPS -> worker -> persisted query acceptance.
    registry.register(SourceRegistration(
        key="az_adif_small",
        display_name="Azerbaijan Deposit Insurance Fund — small public quotations",
        source=AzerbaijanAdifSmallSource(timeout=min(timeout, 30)),
        transport=SourceTransport.HTML,
        jurisdictions=("AZ",),
        languages=("az",),
        homepage_url="https://adif.gov.az/az/sale/",
        official=True,
        enabled=False,
        capabilities=SourceCapabilities(pagination=False, incremental_sync=False),
    ))

    # Additional official KZ public HTML adapter complements the separately
    # token-authenticated KZ API source; operator activation remains explicit.
    registry.register(SourceRegistration(
        key="kz_gov_html",
        display_name="Kazakhstan government public procurement announcements",
        source=KazakhstanGovHtmlSource(timeout=min(timeout, 30)),
        transport=SourceTransport.HTML,
        jurisdictions=("KZ",),
        languages=("ru", "kk"),
        homepage_url="https://old.goszakup.gov.kz/ru/search/announce",
        official=True,
        enabled=False,
        capabilities=SourceCapabilities(pagination=False, incremental_sync=False),
    ))

    # Staged Asian sources are intentionally excluded from default operations.
    # Enable only after live network → normalized notice → isolated DB acceptance.
    if os.environ.get("VALYQON_ASIA_SOURCES_ENABLED", "").strip() == "1":
        for key, url in ASIA_RSS_FEEDS.items():
            registry.register(SourceRegistration(
                key=key,
                display_name={
                    "hk_ha_works": "Hong Kong Housing Authority — works and services",
                    "hk_ha_leasing": "Hong Kong Housing Authority — property tenders",
                    "hk_emsd_tenders": "Hong Kong EMSD — tender notices",
                    "hk_emsd_consultancy": "Hong Kong EMSD — consultancy invitations",
                    "hk_dsd_current": "Hong Kong Drainage Services Department — current tenders",
                    "hk_cedd_tenders": "Hong Kong Civil Engineering and Development Department — tenders",
                }[key],
                source=AsiaPublicSource(name=key, timeout=timeout),
                transport=SourceTransport.RSS,
                jurisdictions=("HK",),
                languages=("en",),
                homepage_url=url,
                official=True,
                enabled=True,
                capabilities=SourceCapabilities(),
            ))

    # Separate Japanese JETRO *agency-only* RSS: requires its own explicit
    # opt-in and independent real queue -> worker -> search CI acceptance.
    # Do not include in the previously approved six Hong Kong sources.
    if os.environ.get("VALYQON_ASIA_JETRO_BID_ENABLED", "").strip() == "1":
        registry.register(SourceRegistration(
            key="jp_jetro_bid",
            display_name="Japan External Trade Organization — public competitive bids",
            source=JetroBidRssSource(timeout=min(timeout, 30.0)),
            transport=SourceTransport.RSS,
            jurisdictions=("JP",),
            languages=("ja",),
            homepage_url=JETRO_BID_RSS_URL,
            official=True,
            enabled=True,
            capabilities=SourceCapabilities(),
        ))

    # Hong Kong Highways Department has an independent official RSS gate.
    # It is not included in the six existing HK sources or JETRO source.
    if os.environ.get("VALYQON_ASIA_HYD_ENABLED", "").strip() == "1":
        registry.register(SourceRegistration(
            key="hk_hyd_tenders",
            display_name="Hong Kong Highways Department — tender notices",
            source=HighwaysTendersSource(timeout=min(timeout, 30.0)),
            transport=SourceTransport.RSS,
            jurisdictions=("HK",), languages=("en",),
            homepage_url=HYD_TENDERS_RSS_URL,
            official=True, enabled=True,
            capabilities=SourceCapabilities(),
        ))

    # Singapore GeBIZ government-owned BO feeds; never confuse with award RSS.
    # Two fixed official categories only, independent opt-in, default disabled.
    if os.environ.get("VALYQON_ASIA_GEBIZ_ENABLED", "").strip() == "1":
        for key, url in SG_GEBIZ_RSS_FEEDS.items():
            registry.register(SourceRegistration(
                key=key,
                display_name=("Singapore GeBIZ — professional service opportunities"
                              if key == "sg_gebiz_professional"
                              else "Singapore GeBIZ — miscellaneous open opportunities"),
                source=SingaporeGeBizRssSource(name=key, timeout=min(timeout, 30.0)),
                transport=SourceTransport.RSS,
                jurisdictions=("SG",), languages=("en",),
                homepage_url=url, official=True, enabled=True,
                capabilities=SourceCapabilities(),
            ))

    # Independent Hong Kong Monetary Authority government Gazette tenders API.
    # Tender invitations only (segment=tender), NOT the award/notice segment.
    if os.environ.get("VALYQON_ASIA_HKMA_ENABLED", "").strip() == "1":
        registry.register(SourceRegistration(
            key="hk_hkma_tender",
            display_name="Hong Kong Monetary Authority — official tender invitations",
            source=HKMATenderSource(timeout=min(timeout, 30.0)),
            transport=SourceTransport.API, jurisdictions=("HK",),
            languages=("en",), homepage_url=HKMA_TENDER_API_URL,
            official=True, enabled=True, capabilities=SourceCapabilities(),
        ))

    # India's government-owned ePublishing is independent of CPPP eProcure.
    if os.environ.get("VALYQON_ASIA_INDIA_EPUBLISH_ENABLED", "").strip() == "1":
        registry.register(SourceRegistration(
            key="in_epublish",
            display_name="India Central ePublishing — latest tender enquiries",
            source=IndiaEpublishSource(timeout=min(timeout, 30.0)),
            transport=SourceTransport.HTML,
            jurisdictions=("IN",), languages=("en",),
            homepage_url=INDIA_EPUBLISH_LIST_URL,
            official=True, enabled=True,
            capabilities=SourceCapabilities(),
        ))

    # Official UAE Ministry of Finance federal current business opportunities.
    # Separate from Dubai eSupply and Abu Dhabi's procurement portals.
    if os.environ.get("VALYQON_ASIA_UAE_FEDERAL_ENABLED", "").strip() == "1":
        registry.register(SourceRegistration(
            key="ae_federal_mof",
            display_name="UAE Ministry of Finance — current federal RFQs",
            source=UAEMinistryFinanceSource(timeout=min(timeout, 30.0)),
            transport=SourceTransport.HTML,
            jurisdictions=("AE",), languages=("en", "ar"),
            homepage_url=UAE_MOF_URL,
            official=True, enabled=True, capabilities=SourceCapabilities(),
        ))

    # Russian connectors are opt-in. Do not enable unverified live adapters.
    if settings.eis_223_configured:
        registry.register(SourceRegistration(
            key="eis_223",
            display_name="EIS 223-FZ",
            source=Eis223RssSource(
                urls=settings.eis_223_rss_urls,
                timeout=timeout,
                ca_bundle_file=settings.ca_bundle_file,
                direct=settings.eis_direct_enabled,
                system_trust=settings.eis_system_trust_enabled,
            ),
            transport=SourceTransport.RSS,
            jurisdictions=("RU",),
            languages=("ru",),
            homepage_url="https://zakupki.gov.ru/",
            official=True,
            enabled=True,
            capabilities=SourceCapabilities(
                keyword_search=settings.eis_223_profile_feeds_enabled
            ),
        ))
    if settings.b2b_center_enabled:
        registry.register(SourceRegistration(
            key="b2b_center",
            display_name="B2B-Center",
            source=B2BCenterSource(timeout=timeout),
            transport=SourceTransport.HTML,
            jurisdictions=("RU",),
            languages=("ru",),
            homepage_url="https://www.b2b-center.ru/",
            official=False,
            enabled=True,
            capabilities=SourceCapabilities(),
        ))

    if settings.mikroton_tender_enabled:
        registry.register(SourceRegistration(
            key="mikroton_tender",
            display_name="MikroTon Tender — public procurement API",
            source=MikrotonTenderSource(timeout=min(timeout, 30)),
            transport=SourceTransport.API,
            jurisdictions=("RU",),
            languages=("ru",),
            homepage_url="https://tender.mt52.ru/",
            official=False,
            enabled=True,
            capabilities=SourceCapabilities(
                pagination=False, documents=False, keyword_search=False,
                authentication_required=False,
            ),
        ))

    if settings.tektorg_public_enabled:
        registry.register(SourceRegistration(
            key="tektorg",
            display_name="TEK-Torg — public tenders (law not independently verified)",
            source=TekTorgPublicSource(timeout=min(timeout, 30)),
            transport=SourceTransport.HTML,
            jurisdictions=("RU",),
            languages=("ru",),
            homepage_url="https://www.tektorg.ru/223-fz/procedures",
            official=False,
            enabled=True,
            capabilities=SourceCapabilities(),
        ))

    if settings.eis_44_html_enabled:
        registry.register(SourceRegistration(
            key="eis_44_html",
            display_name="EIS 44-FZ — experimental public listing (detail unverified)",
            source=Eis44PublicHtmlSource(ca_bundle_file=settings.ca_bundle_file, timeout=min(timeout, 30)),
            transport=SourceTransport.HTML,
            jurisdictions=("RU",), languages=("ru",),
            homepage_url="https://zakupki.gov.ru/",
            official=True, enabled=True,
            capabilities=SourceCapabilities(),
        ))

    if settings.lenobl_small_public_enabled:
        registry.register(SourceRegistration(
            key="lenobl_small_public",
            display_name="Leningrad Oblast official public small-purchase requests",
            source=LenoblSmallPublicSource(timeout=min(timeout, 30)),
            transport=SourceTransport.HTML,
            jurisdictions=("RU",),
            languages=("ru",),
            homepage_url="https://zakupki.lenreg.ru/Search/NewRequests",
            official=True,
            enabled=True,
            capabilities=SourceCapabilities(),
        ))

    if settings.stan_commercial_public_enabled:
        registry.register(SourceRegistration(
            key="stan_commercial_public",
            display_name="STAN-Torgi — genuine commercial procurement procedures",
            source=StanCommercialPublicSource(timeout=min(timeout, 30)),
            transport=SourceTransport.HTML,
            jurisdictions=("RU",),
            languages=("ru",),
            homepage_url="https://stantorgi.ru/etp",
            official=False,
            enabled=True,
            capabilities=SourceCapabilities(),
        ))

    if settings.nmck_native_public_enabled:
        registry.register(SourceRegistration(
            key="nmck_native_public",
            display_name="NMCK — first-party public small-purchase notices",
            source=NmckNativePublicSource(timeout=min(timeout, 30)),
            transport=SourceTransport.HTML,
            jurisdictions=("RU",),
            languages=("ru",),
            homepage_url="https://xn--j1adc1b.xn--p1ai/procedures",
            official=False,
            enabled=True,
            capabilities=SourceCapabilities(),
        ))

    if settings.gpb_etp_public_enabled:
        registry.register(SourceRegistration(
            key="gpb_etp_public",
            display_name="Gazprombank ETP public procurement (law unverified)",
            source=GpbEtpPublicSource(timeout=min(timeout, 30)),
            transport=SourceTransport.HTML,
            jurisdictions=("RU",),
            languages=("ru",),
            homepage_url="https://etpgpb.ru/procedures/",
            official=False,
            enabled=True,
            capabilities=SourceCapabilities(),
        ))

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
