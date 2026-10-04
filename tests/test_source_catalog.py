from pathlib import Path

from app.monitoring.config import MonitoringSettings
from app.sources import (
    SourceTransport,
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


def test_catalog_registers_eis_metadata() -> None:
    catalog = build_source_catalog(settings())

    registration = catalog.registry.get("eis")
    metadata = registration.metadata

    assert metadata.key == "eis"
    assert metadata.transport == SourceTransport.RSS
    assert metadata.jurisdictions == ("RU",)
    assert metadata.languages == ("ru",)
    assert metadata.homepage_url == "https://zakupki.gov.ru/"
    assert metadata.official is True
    assert metadata.enabled is True
    assert metadata.capabilities.keyword_search is True

    assert catalog.enabled_keys == ("eis",)
    assert catalog.fetcher.registry is catalog.registry


def test_catalog_disables_eis_when_no_feed_mode_is_configured() -> None:
    catalog = build_source_catalog(
        settings(profile_feeds_enabled=False)
    )

    assert catalog.registry.get("eis").metadata.enabled is False
    assert catalog.enabled_keys == ()


def test_static_eis_urls_enable_source_without_profile_feeds() -> None:
    catalog = build_source_catalog(
        settings(
            urls=("https://zakupki.gov.ru/example.xml",),
            profile_feeds_enabled=False,
        )
    )

    assert catalog.enabled_keys == ("eis",)
    assert catalog.registry.get("eis").metadata.enabled is True


def test_catalog_adapter_keeps_runtime_settings() -> None:
    ca = Path("example-ca.pem")

    configured = MonitoringSettings(
        enabled=False,
        interval_seconds=600,
        max_items=20,
        max_notifications_per_cycle=5,
        request_timeout=17.5,
        eis_rss_urls=("https://zakupki.gov.ru/example.xml",),
        ca_bundle_file=ca,
        profile_feeds_enabled=True,
        profile_feed_limit=3,
    )

    catalog = build_source_catalog(configured)
    source = catalog.registry.get("eis").source

    assert source.timeout == 17.5
    assert source.ca_bundle_file == ca
    assert source.urls == ("https://zakupki.gov.ru/example.xml",)
