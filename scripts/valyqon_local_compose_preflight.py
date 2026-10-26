"""Read-only local Compose architecture test without exporting source to VPS.

Only three tracked Compose descriptors are copied into a disposable local
directory with a SYNTHETIC .env. Never loads the real operator .env.
Never starts Docker containers, creates AWS resources or accesses a database.
Passing does not imply public launch readiness.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
from unittest.mock import patch

from scripts import check_public_operator_compose as checker

ROOT = Path(__file__).resolve().parents[1]
COPIED = (
    "compose.public.yaml",
    "compose.postgresql.example.yaml",
    "compose.public-operator.yaml",
)
FAKE_ENV = {
    "DATABASE_URL": "postgresql://synthetic:synthetic@db.example.invalid:5432/disposable",
    "TENDERLENS_DOMAIN": "staging.example.invalid",
    "ACME_EMAIL": "synthetic@example.invalid",
    "DOCKER_OUTBOUND_PROXY_URL": "",
    "DOCKER_TELEGRAM_PROXY_URL": "",
    "TENDERLENS_HTTP_PORT": "18080",
    "TENDERLENS_HTTPS_PORT": "18443",
    "MONITORING_ENABLED": "false",
    "TELEGRAM_BOT_TOKEN": "",
    "VALYQON_LEGAL_REQUIRED": "true",
    "VALYQON_LEGAL_APPROVED": "false",
}
# Keep only OS fields needed to find Docker Compose on Windows/Linux.
OS_ALLOW = frozenset({
    "PATH", "PATHEXT", "SystemRoot", "WINDIR", "COMSPEC",
    "HOME", "USERPROFILE", "LOCALAPPDATA", "PROGRAMDATA", "TMP", "TEMP",
})


def local_probe(*, root=ROOT, command=checker.validate):
    root = Path(root).resolve()
    for name in COPIED:
        if not (root / name).is_file():
            raise ValueError("Missing required version-controlled Compose file")
    if shutil.which("docker") is None:
        raise RuntimeError("Docker CLI not found")
    with tempfile.TemporaryDirectory(prefix="valyqon-synthetic-compose-") as directory:
        target = Path(directory)
        for name in COPIED:
            shutil.copyfile(root / name, target / name)
        # Docker Compose uses this *fake* .env instead of the real one.
        (target / ".env").write_text(
            "".join(f"{k}={v}\n" for k, v in FAKE_ENV.items()),
            encoding="utf-8",
        )
        # No real .env, SSH file, DB or source packages are staged here.
        safe_environment = {k: v for k, v in os.environ.items() if k in OS_ALLOW}
        safe_environment.update(FAKE_ENV)
        saved_cwd = Path.cwd()
        try:
            with patch.dict(os.environ, safe_environment, clear=True):
                os.chdir(target)
                checked = command()
        finally:
            os.chdir(saved_cwd)
    if not isinstance(checked, dict) or checked.get("status") != "OFFLINE_OPERATOR_COMPOSE_CONTRACTS_PASS":
        raise ValueError("Resolved Compose contract was not approved")
    return {
        "LOCAL_RELEASE_COMPOSE": "PASS",
        "DEFAULT_SERVICES": checked["default_services"],
        "PRODUCTION_CHANGED": "NO",
        "PRIVATE_SOURCE_SENT_TO_EC2": "NO",
        "REAL_HTTPS_VERIFIED": "NO",
        "REAL_TELEGRAM_VERIFIED": "NO",
        "PUBLIC_LAUNCH_APPROVED": "NO",
    }


def main():
    try:
        report = local_probe()
    except (ValueError, OSError, RuntimeError):
        print("LOCAL_RELEASE_COMPOSE=BLOCKED")
        print("FAILURE_CODE=LOCAL_DOCKER_OR_COMPOSE_CONTRACT")
        print("PRODUCTION_CHANGED=NO")
        print("PRIVATE_SOURCE_SENT_TO_EC2=NO")
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
