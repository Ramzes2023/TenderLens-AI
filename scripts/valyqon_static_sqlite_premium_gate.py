"""Static proof that PREMIUM UI can be staged without a PostgreSQL cutover.

READ-ONLY: checks committed source and the default public Compose descriptor.
Never reads .env, contacts a server, runs Docker, or touches any database.
PASS here is strictly an architectural possibility, NOT deployment permission.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check(root: Path = ROOT) -> dict:
    required = [
        "compose.public.yaml",
        "app/api/routes.py",
        "app/api/saas_shell.py",
        "app/api/static/premium.css",
        "app/api/landing.py",
        "app/api/runtime.py",
        "app/quotas/synchronous.py",
    ]
    missing = [path for path in required if not (root / path).is_file()]
    status = {
        "kind": "VALYQON_STATIC_SQLITE_PREMIUM_SEPARATION",
        "read_only": True,
        "current_public_database": "NOT_VERIFIED",
        "public_root_source": "NOT_VERIFIED",
        "premium_asset_source": "NOT_VERIFIED",
        "external_live_site": "NOT_CHECKED",
        "sqlite_backup_restore": "NOT_VERIFIED",
        "rollback_artefact": "NOT_VERIFIED",
        "live_worker_to_user": "NOT_VERIFIED",
        "payment_and_legal_approval": "NOT_VERIFIED",
        "postgres_cutover_required_for_premium_ui": "NOT_VERIFIED",
        "existing_sqlite_api_startup_can_change_schema": "NOT_VERIFIED",
        "same_sqlite_api_image_upgrade_approved": False,
        "public_deployment_authorized": False,
        "production_changed": False,
        "errors": [],
    }
    if missing:
        status["errors"].append("REQUIRED_SOURCE_FILE_MISSING")
        return status
    compose = (root / required[0]).read_text(encoding="utf-8")
    routes = (root / required[1]).read_text(encoding="utf-8")
    shell = (root / required[2]).read_text(encoding="utf-8")
    def service(name: str) -> str:
        # Only top-level two-space service names, without YAML processing of
        # secret interpolations. This tool must never load the operator .env.
        match = re.search(
            r"(?ms)^  " + re.escape(name) +
            r":\n(.*?)(?=^  [A-Za-z][A-Za-z0-9_-]*:\n|^networks:\n|^volumes:\n|\Z)",
            compose,
        )
        return match.group(1) if match else ""
    api, bot = service("api"), service("bot")
    if not api or not bot:
        status["errors"].append("REQUIRED_API_OR_BOT_SERVICE_MISSING")
        return status
    if not re.search(
        r"(?m)^      DATABASE_URL: sqlite:////app/data/tenderlens\.db\s*$", api
    ) or not re.search(r"(?m)^      DATA_DIR: /app/data\s*$", api):
        status["errors"].append("DEFAULT_API_NOT_PINNED_TO_EXISTING_SQLITE")
    else:
        status["current_public_database"] = "SQLITE_CONFIG_ONLY"
    if not re.search(r"(?m)^      - tenderlens_data:/app/data\s*$", api):
        status["errors"].append("EXISTING_SQLITE_VOLUME_NOT_PRESERVED")
    if not re.search(r"(?m)^      VALYQON_LEGAL_REQUIRED: [\"']?true[\"']?\s*$", api):
        status["errors"].append("LEGAL_GATE_NOT_FORCED")
    for key, value in (
        ("MONITORING_ENABLED", "false"),
        ("VALYQON_DEADLINE_ALERTS_ENABLED", "false"),
        ("VALYQON_PUBLIC_AI_ENABLED", "false"),
        ("VALYQON_RESTRICT_PAID_SOURCE_DETAILS", "true"),
        ("VALYQON_PUBLIC_ANALYTICS_MODE", "real"),
    ):
        if not re.search(
            rf"(?m)^      {re.escape(key)}: [\"']?{value}[\"']?\s*$", api
        ):
            status["errors"].append("UNSAFE_API_OVERRIDE_" + key)
    if not re.search(
        r"(?m)^    profiles:\n      - verified-bot\s*$", bot
    ):
        status["errors"].append("BOT_MUST_REMAIN_OPT_IN")
    # The public home must be returned without forcing unauthenticated
    # browsers to /login. A separate auth route can still protect /dashboard.
    home = re.search(
        r'@router\.get\("/", include_in_schema=False\)\s*async def root_page\(request: Request\):'
        r'(.*?)(?=\n@router\.|\Z)',
        routes, flags=re.S,
    )
    if home and "return HTMLResponse(landing_html(account is not None)" in home.group(1) and (
        'RedirectResponse("/login"' not in home.group(1)
    ):
        status["public_root_source"] = "LANDING_HTML_IN_MAIN"
    else:
        status["errors"].append("PUBLIC_ROOT_NOT_ACTUAL_LANDING")
    if ('/assets/premium.css' in shell
            and (root / "app/api/static/premium.css").stat().st_size > 100):
        status["premium_asset_source"] = "ASSET_PRESENT_IN_MAIN"
    else:
        status["errors"].append("PREMIUM_STYLESHEET_NOT_IN_RENDERED_SHELL")
    runtime=(root/"app/api/runtime.py").read_text(encoding="utf-8")
    quota=(root/"app/quotas/synchronous.py").read_text(encoding="utf-8")
    if ("runtime.synchronous_usage.initialize()" in runtime
            and "self.repository.database.migrate('synchronous_usage')" in quota):
        status["existing_sqlite_api_startup_can_change_schema"] = "YES"
    else:
        status["errors"].append("UNREVIEWED_SQLITE_STARTUP_MUTATION_BEHAVIOR")
    if not status["errors"]:
        status["postgres_cutover_required_for_premium_ui"] = "NO_STATIC_ARCHITECTURE"
    return status


def main() -> int:
    status = check()
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    return 0 if not status["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
