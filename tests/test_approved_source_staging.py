"""Opt-in real MikroTon source staging: never edit production or public preview.

Config-only contract tests; the live HTTP→Worker→SQLite→authenticated ASGI
proof is scripts/ci_ru_mikroton_guest_http_acceptance.py (separate CI job).
"""
from dataclasses import replace
from pathlib import Path

from app.monitoring.config import MonitoringSettings
from app.sources.catalog import build_source_catalog
from app.sources.ru_cycle import RU_APPROVED_SOURCES, approved_ru_keys


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "ops/ready_sources/compose.yaml"


def test_only_genuinely_proven_mikroton_is_enabled_in_staging():
    compose = COMPOSE.read_text(encoding="utf-8")
    settings = MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=20,
        max_notifications_per_cycle=5, request_timeout=20,
        eis_rss_urls=(), ca_bundle_file=None,
        profile_feeds_enabled=False,
    )
    catalog = build_source_catalog(replace(settings, mikroton_tender_enabled=True))
    assert approved_ru_keys(catalog) == ("mikroton_tender",)
    assert "mikroton_tender" in RU_APPROVED_SOURCES
    assert catalog.registry.get("mikroton_tender").enabled is True
    assert catalog.registry.get("eis").enabled is False
    for blocked in ("tektorg", "gpb_etp_public", "ru_samara_public_list",
                    "ru_dagestan_public_list", "b2b_center"):
        assert not catalog.registry.get(blocked).enabled
    assert 'MIKROTON_TENDER_ENABLED: "true"' in compose
    for key in (
        "EIS_PROFILE_FEEDS_ENABLED", "EIS_DIRECT_ENABLED", "EIS_223_ENABLED",
        "B2B_CENTER_ENABLED", "TEKTORG_PUBLIC_ENABLED", "GPB_ETP_PUBLIC_ENABLED",
        "VALYQON_RU_BACKGROUND_CATALOG_ENABLED",
        "MONITORING_ENABLED", "RAG_ENABLED", "VALYQON_PUBLIC_AI_ENABLED",
        "VALYQON_CIS_MD_ELICITATIE_ENABLED",
        "VALYQON_CIS_AZ_AZERISTILIK_ENABLED",
        "VALYQON_CIS_AZ_ADIF_SMALL_ENABLED",
    ):
        assert f'{key}: "false"' in compose, key


def test_staging_is_isolated_and_requires_explicit_worker_queue():
    text = COMPOSE.read_text(encoding="utf-8")
    assert '127.0.0.1:18965:8000' in text
    assert '127.0.0.1:18966:8025' in text
    assert 'ready_source_data:/app/data' in text
    assert 'DATABASE_URL: sqlite:////app/data/ready-sources.sqlite' in text
    assert 'command: ["python", "-m", "app.jobs.worker", "--connectors"]' in text
    assert 'command: ["python", "-m", "app.sources.enqueue", "--ru-approved"]' in text
    assert 'profiles: ["operator"]' in text
    assert 'network_mode: none' in text
    assert 'TEL EGRAM' not in text
    assert 'TELEGRAM_BOT_TOKEN: ""' in text
    assert "VALYQON_RESTRICT_PAID_SOURCE_DETAILS: \"true\"" in text
    assert "VALYQON_PUBLIC_ANALYTICS_MODE: real" in text
    assert "VALYQON_SMTP_HOST: mailpit" in text
    assert "no-new-privileges:true" in text
    assert "cap_drop:" in text
    assert "external: true" not in text
    assert "tenderlens_data" not in text
    assert "website_review_data" not in text
    assert "restart: always" not in text
    assert "--cis-approved" not in text
    assert ".env" not in text or "PYTHON_DOTENV_DISABLED" in text


def test_source_activation_comes_from_operator_choice_not_public_review():
    preview = (ROOT / "ops/website_preview/compose.yaml").read_text(encoding="utf-8")
    assert 'MIKROTON_TENDER_ENABLED: "true"' not in preview
    assert "ready_source_data" not in preview
    assert 'MIKROTON_TENDER_ENABLED: "false"' in (ROOT / ".env.example").read_text(encoding="utf-8")
