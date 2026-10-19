"""Opt-in only: Fabrikant soap4 first-party source never activates by default."""
from dataclasses import replace

import pytest

from app.monitoring.config import MonitoringSettings, load_monitoring_settings, MonitoringConfigurationError
from app.sources.catalog import build_source_catalog
from app.sources.ingestion import HOSTS
from app.sources.fabrikant_44_public import Fabrikant44PublicSource, HOST, SOURCE_ID


def cfg():
    return MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=5,
        max_notifications_per_cycle=5, request_timeout=20,
        eis_rss_urls=(), ca_bundle_file=None,
    )


def test_fabrikant_has_no_implicit_enable_or_extra_eis_upstream_count():
    assert SOURCE_ID not in build_source_catalog(cfg()).registry.keys()
    enabled = build_source_catalog(replace(cfg(), fabrikant_44_public_enabled=True))
    assert SOURCE_ID in enabled.enabled_keys
    entry = enabled.registry.get(SOURCE_ID)
    assert isinstance(entry.source, Fabrikant44PublicSource)
    assert entry.jurisdictions == ("RU",)
    assert "44.fabrikant.ru" in entry.homepage_url
    assert HOSTS[SOURCE_ID] == frozenset({HOST})


def test_user_must_explicitly_turn_on_fabrikant_and_invalid_config_rejected(monkeypatch, tmp_path):
    file = tmp_path / "not-present.env"
    monkeypatch.delenv("FABRIKANT_44_PUBLIC_ENABLED", raising=False)
    assert not load_monitoring_settings(file).fabrikant_44_public_enabled
    monkeypatch.setenv("FABRIKANT_44_PUBLIC_ENABLED", "true")
    assert load_monitoring_settings(file).fabrikant_44_public_enabled
    monkeypatch.setenv("FABRIKANT_44_PUBLIC_ENABLED", "unknown")
    with pytest.raises(MonitoringConfigurationError):
        load_monitoring_settings(file)
