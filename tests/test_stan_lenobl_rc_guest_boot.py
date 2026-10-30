"""Exact RC guest API acceptance: no MikroTon opt-in in non-public stage."""
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient

import app.api.isolated_public_sources as public
from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.api.isolated_public_sources import approved_public_source_keys, create_public_source_app


def stage_env():
    return {
        "DATABASE_URL": public.ISOLATED_SQLITE_URL,
        "VALYQON_ISOLATED_PUBLIC_SOURCES_ENABLED": "true",
        "VALYQON_STAN_LENOBL_RC_MODE": "true",
        "MIKROTON_TENDER_ENABLED": "false",
        "STAN_COMMERCIAL_PUBLIC_ENABLED": "true",
        "LENOBL_SMALL_PUBLIC_ENABLED": "true",
        "MONITORING_ENABLED": "false",
        "VALYQON_EMAIL_MODE": "disabled",
        "VALYQON_PUBLIC_AI_ENABLED": "false",
        "VALYQON_RU_BACKGROUND_CATALOG_ENABLED": "false",
        "TELEGRAM_BOT_TOKEN": "",
        "OUTBOUND_PROXY_URL": "",
    }


def test_stage_mode_only_allows_exact_two_sources():
    assert approved_public_source_keys(stage_env()) == frozenset({
        "stan_commercial_public", "lenobl_small_public"
    })


@pytest.mark.parametrize("key,value", [
    ("MIKROTON_TENDER_ENABLED", "true"),
    ("STAN_COMMERCIAL_PUBLIC_ENABLED", "false"),
    ("LENOBL_SMALL_PUBLIC_ENABLED", "false"),
    ("MONITORING_ENABLED", "true"),
    ("VALYQON_EMAIL_MODE", "smtp"),
    ("VALYQON_PUBLIC_AI_ENABLED", "true"),
    ("VALYQON_RU_BACKGROUND_CATALOG_ENABLED", "true"),
    ("TELEGRAM_BOT_TOKEN", "unsafe"),
    ("OUTBOUND_PROXY_URL", "https://proxy.invalid"),
    ("DATABASE_URL", "sqlite:////tmp/not-the-isolated-database.sqlite"),
    ("VALYQON_ISOLATED_PUBLIC_SOURCES_ENABLED", "false"),
    ("VALYQON_STAN_LENOBL_RC_MODE", "unexpected"),
    ("SOUTH_URAL_PUBLIC_ENABLED", "true"),
])
def test_stage_rejects_any_other_source_or_send_option(key, value):
    env=stage_env()
    env[key]=value
    with pytest.raises(RuntimeError):
        approved_public_source_keys(env)


def test_regular_production_rejects_rc_flags_without_mode_and_preserves_base():
    env=stage_env()
    env["VALYQON_STAN_LENOBL_RC_MODE"]="false"
    with pytest.raises(RuntimeError, match="Mandatory base"):
        approved_public_source_keys(env)
    env["MIKROTON_TENDER_ENABLED"]="true"
    assert approved_public_source_keys(env) == frozenset({
        "mikroton_tender", "stan_commercial_public", "lenobl_small_public"
    })


def test_real_stage_lifespan_initializes_separate_sql_and_health_without_base_mikroton(monkeypatch):
    env=stage_env()
    with TemporaryDirectory(prefix="valyqon-stage-api-test-") as folder:
        destination=Path(folder)/"stage-only.sqlite3"
        monkeypatch.setattr(public, "parse_database_settings",
                            lambda _: DatabaseSettings("test-rc",destination))
        monkeypatch.setattr(public.os, "environ", env)
        app=create_public_source_app()
        with TestClient(app) as client:
            assert app.state.public_source_allowed_keys == frozenset({
                "stan_commercial_public","lenobl_small_public"
            })
            health=client.get("/_internal/health")
            assert health.status_code==200
            assert health.json()=={
                "service":"valyqon-public-source-preview",
                "database":"isolated","status":"ready"
            }
        assert destination.is_file()
