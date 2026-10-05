import asyncio
from pathlib import Path

from app.monitoring.config import MonitoringSettings
from app.sources import (
    MultiSourceFetcher,
    SourceCapabilities,
    SourceCatalog,
    SourceRegistration,
    SourceRegistry,
    SourceTransport,
    TenderNotice,
    build_source_catalog,
)


def settings(
    *,
    urls: tuple[str, ...] = (),
    profile_feeds_enabled: bool = True,
) -> MonitoringSettings:
    return MonitoringSettings(
        enabled=False,
        interval_seconds=600,
        max_items=20,
        max_notifications_per_cycle=5,
        request_timeout=30.0,
        eis_rss_urls=urls,
        ca_bundle_file=None,
        profile_feeds_enabled=profile_feeds_enabled,
        profile_feed_limit=5,
    )


def _clear_authenticated_source_env(
    monkeypatch,
) -> None:
    monkeypatch.delenv(
        "SAM_GOV_API_KEY",
        raising=False,
    )
    monkeypatch.delenv(
        "KZ_GOSZAKUP_API_TOKEN",
        raising=False,
    )


def test_catalog_registers_eis_metadata(
    monkeypatch,
) -> None:
    _clear_authenticated_source_env(
        monkeypatch
    )

    catalog = build_source_catalog(
        settings()
    )

    registration = catalog.registry.get(
        "eis"
    )
    metadata = registration.metadata

    assert metadata.key == "eis"
    assert (
        metadata.transport
        == SourceTransport.RSS
    )
    assert metadata.jurisdictions == (
        "RU",
    )
    assert metadata.languages == (
        "ru",
    )
    assert metadata.homepage_url == (
        "https://zakupki.gov.ru/"
    )
    assert metadata.official is True
    assert metadata.enabled is True
    assert (
        metadata.capabilities.keyword_search
        is True
    )

    assert "eis" in catalog.enabled_keys
    assert (
        catalog.fetcher.registry
        is catalog.registry
    )


def test_catalog_registers_all_phase23_sources(
    monkeypatch,
) -> None:
    _clear_authenticated_source_env(
        monkeypatch
    )

    catalog = build_source_catalog(
        settings()
    )

    assert catalog.registry.keys() == (
        "eis",
        "ted",
        "sam_gov",
        "uk_fts",
        "canada_buys",
        "austender",
        "nz_gets",
        "za_etenders",
        "india_cppp",
        "kz_goszakup",
    )

    assert catalog.enabled_keys == (
        "eis",
        "ted",
        "uk_fts",
        "canada_buys",
        "austender",
        "nz_gets",
        "za_etenders",
        "india_cppp",
    )

    assert (
        catalog.registry.get(
            "sam_gov"
        ).enabled
        is False
    )

    assert (
        catalog.registry.get(
            "kz_goszakup"
        ).enabled
        is False
    )


def test_authenticated_sources_enable_from_env(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "SAM_GOV_API_KEY",
        "test-sam-key",
    )

    monkeypatch.setenv(
        "KZ_GOSZAKUP_API_TOKEN",
        "test-kz-token",
    )

    catalog = build_source_catalog(
        settings()
    )

    sam = catalog.registry.get(
        "sam_gov"
    )

    kz = catalog.registry.get(
        "kz_goszakup"
    )

    assert sam.enabled is True
    assert kz.enabled is True

    assert sam.source.api_key == (
        "test-sam-key"
    )

    assert kz.source.api_token == (
        "test-kz-token"
    )

    assert (
        sam.metadata.capabilities.
        authentication_required
        is True
    )

    assert (
        kz.metadata.capabilities.
        authentication_required
        is True
    )


def test_catalog_disables_only_eis_when_no_feed_mode(
    monkeypatch,
) -> None:
    _clear_authenticated_source_env(
        monkeypatch
    )

    catalog = build_source_catalog(
        settings(
            profile_feeds_enabled=False
        )
    )

    assert (
        catalog.registry.get(
            "eis"
        ).metadata.enabled
        is False
    )

    assert "eis" not in (
        catalog.enabled_keys
    )

    assert "ted" in (
        catalog.enabled_keys
    )

    assert "india_cppp" in (
        catalog.enabled_keys
    )


def test_static_eis_urls_enable_source_without_profile_feeds(
    monkeypatch,
) -> None:
    _clear_authenticated_source_env(
        monkeypatch
    )

    catalog = build_source_catalog(
        settings(
            urls=(
                "https://zakupki.gov.ru/"
                "example.xml",
            ),
            profile_feeds_enabled=False,
        )
    )

    assert "eis" in (
        catalog.enabled_keys
    )

    assert (
        catalog.registry.get(
            "eis"
        ).metadata.enabled
        is True
    )


def test_catalog_adapter_keeps_runtime_settings(
    monkeypatch,
) -> None:
    _clear_authenticated_source_env(
        monkeypatch
    )

    ca = Path(
        "example-ca.pem"
    )

    configured = MonitoringSettings(
        enabled=False,
        interval_seconds=600,
        max_items=20,
        max_notifications_per_cycle=5,
        request_timeout=17.5,
        eis_rss_urls=(
            "https://zakupki.gov.ru/"
            "example.xml",
        ),
        ca_bundle_file=ca,
        profile_feeds_enabled=True,
        profile_feed_limit=3,
    )

    catalog = build_source_catalog(
        configured
    )

    eis = catalog.registry.get(
        "eis"
    ).source

    assert eis.timeout == 17.5
    assert eis.ca_bundle_file == ca
    assert eis.urls == (
        "https://zakupki.gov.ru/"
        "example.xml",
    )

    assert (
        catalog.registry.get(
            "ted"
        ).source.timeout
        == 17.5
    )

    assert (
        catalog.registry.get(
            "india_cppp"
        ).source.timeout
        == 17.5
    )


class _FakeSource:
    def __init__(
        self,
        name,
        *,
        terms=(),
    ):
        self.name = name
        self.terms = tuple(
            terms
        )

    def for_search_terms(
        self,
        search_terms,
        *,
        max_feeds=5,
    ):
        return _FakeSource(
            self.name,
            terms=tuple(
                search_terms
            )[:max_feeds],
        )

    async def fetch(
        self,
        limit=20,
    ):
        suffix = (
            ",".join(
                self.terms
            )
            if self.terms
            else "default"
        )

        return [
            TenderNotice(
                source=self.name,
                external_id=(
                    f"{self.name}-1"
                ),
                title=(
                    f"{self.name}:{suffix}"
                ),
                url=(
                    "https://example.test/"
                    f"{self.name}"
                ),
            )
        ][:limit]


def test_catalog_unified_fetch_uses_multisource_and_profile_eis():
    registry = SourceRegistry(
        [
            SourceRegistration(
                key="eis",
                display_name="EIS",
                source=_FakeSource(
                    "eis"
                ),
                enabled=True,
                capabilities=(
                    SourceCapabilities(
                        keyword_search=True
                    )
                ),
            ),
            SourceRegistration(
                key="ted",
                display_name="TED",
                source=_FakeSource(
                    "ted"
                ),
                enabled=True,
            ),
        ]
    )

    catalog = SourceCatalog(
        registry=registry,
        fetcher=MultiSourceFetcher(
            registry
        ),
    )

    report = asyncio.run(
        catalog.fetch(
            limit_per_source=2,
            search_terms=(
                "pump",
                "valve",
            ),
        )
    )

    assert report.attempted_sources == (
        "eis",
        "ted",
    )

    assert report.successful_sources == (
        "eis",
        "ted",
    )

    assert report.failures == ()

    titles = {
        notice.source: notice.title
        for notice in report.notices
    }

    assert titles["eis"] == (
        "eis:pump,valve"
    )

    assert titles["ted"] == (
        "ted:default"
    )
