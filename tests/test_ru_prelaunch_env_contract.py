"""Regression: other PR merges must not silently drop RU opt-in controls.

Offline-only: never parses a live production .env or connects to an ETP.
"""
from pathlib import Path

from app.monitoring.config import MonitoringSettings, load_monitoring_settings
from app.sources.fabrikant_44_public import HOST as FABRIKANT_HOST


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / ".env.example"
FLAGS = (
    "RU_DAGESTAN_PUBLIC_LIST_ENABLED",
    "FABRIKANT_44_PUBLIC_ENABLED",
    "ROSELTORG_PUBLIC_ENABLED",
    "GPB_ETP_PUBLIC_ENABLED",
    "TEKTORG_PUBLIC_ENABLED",
    "VALYQON_RU_BACKGROUND_CATALOG_ENABLED",
)


def test_all_marketplace_and_regional_operator_flags_explicitly_off_in_template():
    lines = TEMPLATE.read_text(encoding="utf-8").splitlines()
    for flag in FLAGS:
        assert lines.count(flag + "=false") == 1
        assert not any(line.startswith(flag + "=true") for line in lines)


def test_prelaunch_defaults_for_all_new_operator_adapters(monkeypatch, tmp_path):
    for flag in FLAGS:
        monkeypatch.delenv(flag, raising=False)
    settings = load_monitoring_settings(tmp_path / "never-created.env")
    assert settings.ru_dagestan_public_list_enabled is False
    assert settings.fabrikant_44_public_enabled is False
    assert settings.roseltorg_public_enabled is False
    assert settings.gpb_etp_public_enabled is False
    assert settings.tektorg_public_enabled is False
    assert settings.ru_background_catalog_enabled is False


def test_fabrikant_original_registry_host_not_deprecated_soap4():
    assert FABRIKANT_HOST == "44.fabrikant.ru"
    template = TEMPLATE.read_text(encoding="utf-8")
    assert "The proposed soap4 route was NOT available" in template
