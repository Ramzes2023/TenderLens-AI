"""Release policy: premium static UI and PostgreSQL migration are separate.

Offline source review only. No production, no .env, no Docker, no real DB.
"""
from pathlib import Path
import shutil

import pytest

from scripts.valyqon_static_sqlite_premium_gate import check, ROOT

FILES=(
    "compose.public.yaml",
    "app/api/routes.py",
    "app/api/saas_shell.py",
    "app/api/static/premium.css",
    "app/api/landing.py",
)


def fixture_tree(tmp_path):
    for name in FILES:
        dest=tmp_path/name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/name,dest)
    return tmp_path


def test_source_architecture_preserves_sqlite_without_postgres_cutover():
    evidence=check(ROOT)
    assert evidence["errors"] == []
    assert evidence["read_only"] is True
    assert evidence["public_root_source"]=="LANDING_HTML_IN_MAIN"
    assert evidence["premium_asset_source"]=="ASSET_PRESENT_IN_MAIN"
    assert evidence["current_public_database"]=="SQLITE_CONFIG_ONLY"
    assert evidence["postgres_cutover_required_for_premium_ui"]=="NO_STATIC_ARCHITECTURE"
    assert evidence["sqlite_backup_restore"]=="NOT_VERIFIED"
    assert evidence["external_live_site"]=="NOT_CHECKED"
    assert evidence["rollback_artefact"]=="NOT_VERIFIED"
    assert evidence["public_deployment_authorized"] is False
    assert evidence["production_changed"] is False


@pytest.mark.parametrize("old,new,expected",[
    ("DATABASE_URL: sqlite:////app/data/tenderlens.db",
     "DATABASE_URL: ${DATABASE_URL}", "DEFAULT_API_NOT_PINNED_TO_EXISTING_SQLITE"),
    ("- tenderlens_data:/app/data",
     "- unknown_volume:/app/data", "EXISTING_SQLITE_VOLUME_NOT_PRESERVED"),
    ("VALYQON_LEGAL_REQUIRED: \"true\"",
     "VALYQON_LEGAL_REQUIRED: \"false\"", "LEGAL_GATE_NOT_FORCED"),
    ("MONITORING_ENABLED: \"false\"",
     "MONITORING_ENABLED: \"true\"", "UNSAFE_API_OVERRIDE_MONITORING_ENABLED"),
    ("VALYQON_RESTRICT_PAID_SOURCE_DETAILS: \"true\"",
     "VALYQON_RESTRICT_PAID_SOURCE_DETAILS: \"false\"",
     "UNSAFE_API_OVERRIDE_VALYQON_RESTRICT_PAID_SOURCE_DETAILS"),
])
def test_unsafe_public_compose_change_blocks_architecture_proof(
        tmp_path,old,new,expected):
    root=fixture_tree(tmp_path)
    p=root/"compose.public.yaml"
    current=p.read_text(encoding="utf-8")
    assert old in current
    p.write_text(current.replace(old,new,1),encoding="utf-8")
    assert expected in check(root)["errors"]


def test_legacy_login_redirect_not_mislabeled_public_landing(tmp_path):
    root=fixture_tree(tmp_path)
    p=root/"app/api/routes.py"
    s=p.read_text(encoding="utf-8")
    marker="return HTMLResponse(landing_html(account is not None), headers={\"Cache-Control\": \"no-store\"})"
    assert marker in s
    p.write_text(s.replace(marker,'return RedirectResponse("/login", status_code=303)',1),
                 encoding="utf-8")
    status=check(root)
    assert "PUBLIC_ROOT_NOT_ACTUAL_LANDING" in status["errors"]
    assert status["public_deployment_authorized"] is False


def test_css_path_is_assets_premium_not_old_static_public_luxe(tmp_path):
    root=fixture_tree(tmp_path)
    shell=root/"app/api/saas_shell.py"
    s=shell.read_text(encoding="utf-8")
    assert "/assets/premium.css" in s
    shell.write_text(s.replace("/assets/premium.css","/static/public_luxe.css"),
                     encoding="utf-8")
    assert "PREMIUM_STYLESHEET_NOT_IN_RENDERED_SHELL" in check(root)["errors"]


def test_missing_source_is_rejected_without_secret_or_network_access(tmp_path):
    root=fixture_tree(tmp_path)
    (root/"app/api/static/premium.css").unlink()
    result=check(root)
    assert result["errors"]==["REQUIRED_SOURCE_FILE_MISSING"]
    assert result["production_changed"] is False
    assert result["sqlite_backup_restore"]=="NOT_VERIFIED"
