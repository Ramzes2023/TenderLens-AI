"""Kavkaz.RF real adapter can be activated only by explicit operator setting.

Mocked/offline registry tests are NOT proof of externally reachable notices.
"""
from dataclasses import replace
import pytest

from app.monitoring.config import MonitoringSettings, MonitoringConfigurationError, load_monitoring_settings
from app.sources.catalog import build_source_catalog
from app.sources.ingestion import HOSTS
from app.sources.kavkaz_rf_firstparty import SOURCE_ID, HOST, KavkazRfFirstpartySource


def _settings():
    return MonitoringSettings(
        enabled=False,
        interval_seconds=600,
        max_items=20,
        max_notifications_per_cycle=5,
        request_timeout=20,
        eis_rss_urls=(),
        ca_bundle_file=None,
        profile_feeds_enabled=False,
    )


def test_default_setting_does_not_register_or_enable_firstparty_source():
    cfg = _settings()
    assert cfg.kavkaz_rf_firstparty_enabled is False
    assert SOURCE_ID not in build_source_catalog(cfg).enabled_keys
    assert SOURCE_ID not in {m.key for m in build_source_catalog(cfg).registry.metadata()}


def test_explicit_enable_registers_correct_firstparty_adapter_and_host():
    catalog = build_source_catalog(replace(_settings(), kavkaz_rf_firstparty_enabled=True))
    assert SOURCE_ID in catalog.enabled_keys
    metadata = {m.key: m for m in catalog.registry.metadata()}[SOURCE_ID]
    assert metadata.enabled and metadata.jurisdictions == ("RU",)
    assert metadata.homepage_url.startswith("https://" + HOST + "/")
    assert isinstance(catalog.registry.get(SOURCE_ID).source, KavkazRfFirstpartySource)
    assert HOSTS[SOURCE_ID] == frozenset({HOST})


def test_env_opt_in_is_strict_boolean_and_defaults_off(monkeypatch, tmp_path):
    envfile = tmp_path / "not-created.env"
    monkeypatch.delenv("KAVKAZ_RF_FIRSTPARTY_ENABLED", raising=False)
    assert load_monitoring_settings(envfile).kavkaz_rf_firstparty_enabled is False
    monkeypatch.setenv("KAVKAZ_RF_FIRSTPARTY_ENABLED", "true")
    assert load_monitoring_settings(envfile).kavkaz_rf_firstparty_enabled is True
    monkeypatch.setenv("KAVKAZ_RF_FIRSTPARTY_ENABLED", "maybe")
    with pytest.raises(MonitoringConfigurationError):
        load_monitoring_settings(envfile)
