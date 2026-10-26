"""Safely inspect public Compose overlays; never start containers or use secrets.

The integration CI invokes this only with disposable *synthetic* environment
variables; a positive result checks architecture, not external readiness.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

OVERLAYS = (
    "compose.public.yaml",
    "compose.postgresql.example.yaml",
    "compose.public-operator.yaml",
)
DEFAULT_SERVICES = {"api", "caddy"}
TELEGRAM_PROFILE = "authorized-telegram"
SOURCE_PROFILE = "reviewed-source-worker"


def _cmd(*args):
    out = [
        "docker", "compose",
        *[entry for name in OVERLAYS for entry in ("-f", name)],
        *args,
    ]
    done = subprocess.run(
        out, capture_output=True, text=True, timeout=25, check=False,
    )
    if done.returncode:
        # The command can leak operator-supplied environment values. Never
        # echo arbitrary Compose output or raw subprocess exception messages.
        raise RuntimeError("Compose structural validation failed")
    return done.stdout


def validate():
    for name in OVERLAYS:
        if not Path(name).is_file():
            raise RuntimeError("Missing required reviewed Compose overlay")
    default = set(_cmd("config", "--services").split())
    telegram = set(_cmd("--profile", TELEGRAM_PROFILE, "config", "--services").split())
    sources = set(_cmd("--profile", SOURCE_PROFILE, "config", "--services").split())

    if default != DEFAULT_SERVICES:
        raise RuntimeError("An unreviewed production service would start by default")
    if telegram != DEFAULT_SERVICES | {"bot"}:
        raise RuntimeError("Telegram profile activation scope mismatch")
    if sources != DEFAULT_SERVICES | {"connector-worker"}:
        raise RuntimeError("Connector profile activation scope mismatch")

    configured = json.loads(_cmd(
        "--profile", TELEGRAM_PROFILE, "--profile", SOURCE_PROFILE,
        "config", "--format", "json",
    ))
    services = configured["services"]
    for name in ("api", "bot", "connector-worker"):
        service = services[name]
        environment = service["environment"]
        if environment.get("VALYQON_DATABASE_REQUIRE_POSTGRES") != "true":
            raise RuntimeError("Public application service does not require PostgreSQL")
        if not environment.get("DATABASE_URL", "").startswith(
            ("postgresql://", "postgresql+psycopg://")
        ):
            raise RuntimeError("Public service is not configured for PostgreSQL")
        if service.get("ports") or service.get("network_mode") == "host":
            raise RuntimeError("Private application service publishes a host port")
    if services["bot"]["environment"].get("MONITORING_ENABLED") != "false":
        raise RuntimeError("Unapproved Telegram background delivery enabled")
    worker = services["connector-worker"]
    if worker.get("command") != ["python", "-m", "app.jobs.worker", "--connectors"]:
        raise RuntimeError("Unreviewed public worker entrypoint")
    if worker.get("profiles") != [SOURCE_PROFILE]:
        raise RuntimeError("Source Worker must be opt-in")
    if services["bot"].get("profiles") != [TELEGRAM_PROFILE]:
        raise RuntimeError("Telegram polling must be opt-in")
    if services["caddy"].get("profiles"):
        raise RuntimeError("HTTPS gateway must be part of default staging stack")
    return {
        "status": "OFFLINE_OPERATOR_COMPOSE_CONTRACTS_PASS",
        "default_services": sorted(default),
        "telegram_opt_in": sorted(telegram - default),
        "connector_opt_in": sorted(sources - default),
        "production_changed": False,
        "public_https_verified": False,
        "real_source_to_user_verified": False,
        "paid_subscriptions_verified": False,
        "commercial_launch_approved": False,
    }


def main():
    print(json.dumps(validate(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
