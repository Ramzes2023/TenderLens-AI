"""Offline bot startup guard for operator-only regional Worker-SQL alerts.

Pure preflight only: no Telegram Bot API, DB, migrations, queues, live sources,
user subscriptions or production changes.
"""
from dataclasses import replace

import pytest

from app.bot.main import require_ingushetia_worker_sql_settings
from app.monitoring.config import MonitoringSettings, MonitoringConfigurationError
from app.sources.catalog import build_source_catalog


def config(**overrides):
    values = dict(
        enabled=False, interval_seconds=600, max_items=20,
        max_notifications_per_cycle=5, request_timeout=20,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
        ru_background_catalog_enabled=False,
        ru_ingushetia_worker_sql_alerts_enabled=False,
        ru_ingushetia_eis44_enabled=False,
        ru_ingushetia_fabrikant44_enabled=False,
    )
    values.update(overrides)
    return MonitoringSettings(**values)


def check(settings):
    return require_ingushetia_worker_sql_settings(settings, build_source_catalog(settings))


def test_unrelated_existing_legacy_config_keeps_original_opt_out():
    assert check(config()) is None
    assert check(config(enabled=True, ru_background_catalog_enabled=True)) is None


@pytest.mark.parametrize("other_source", [
    {},
    {"b2b_center_enabled": True},
    {"kavkaz_rf_firstparty_enabled": True},
])
def test_worker_sql_enabled_without_either_ingushetia_source_fails_closed(other_source):
    settings = config(
        enabled=True, ru_background_catalog_enabled=True,
        ru_ingushetia_worker_sql_alerts_enabled=True, **other_source,
    )
    with pytest.raises(MonitoringConfigurationError, match="explicitly enabled Ingushetia source"):
        check(settings)


@pytest.mark.parametrize("missing_switch", ["enabled", "ru_background_catalog_enabled"])
def test_worker_sql_does_not_start_with_background_monitoring_disabled(missing_switch):
    switches = dict(
        enabled=True, ru_background_catalog_enabled=True,
        ru_ingushetia_worker_sql_alerts_enabled=True,
        ru_ingushetia_eis44_enabled=True,
    )
    switches[missing_switch] = False
    with pytest.raises(MonitoringConfigurationError, match="explicit background monitoring"):
        check(config(**switches))


@pytest.mark.parametrize("flags", [
    {"ru_ingushetia_eis44_enabled": True},
    {"ru_ingushetia_fabrikant44_enabled": True},
    {"ru_ingushetia_eis44_enabled": True, "ru_ingushetia_fabrikant44_enabled": True},
])
def test_explicitly_enabled_verified_sources_accept_pure_preflight_without_side_effects(flags):
    settings = config(enabled=True, ru_background_catalog_enabled=True,
                      ru_ingushetia_worker_sql_alerts_enabled=True, **flags)
    assert check(settings) is None
