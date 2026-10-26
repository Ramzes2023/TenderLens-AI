"""Last-resort, read-only SSH inventory using tiny independent commands.

Used only if the already-pinned SSH host accepts a minimal stdin-shell probe
but cannot execute either the complete or segmented inventory. Each command
has a fixed literal body (no user interpolation) and returns one verified
result. No remote files, secrets, or docker state are changed.
"""
from __future__ import annotations

import re
import subprocess

# All stages are finite strings. Never print remote stdout or stderr.
_STAGE = {
    "PREFLIGHT_SCHEMA": "START",
    "REPO_PRESENT": "REPOSITORY",
    "REMOTE_SHA": "REPOSITORY",
    "WORKTREE_CLEAN": "REPOSITORY",
    "DOCKER_USABLE": "DOCKER",
    "PUBLIC_COMPOSE_PRESENT": "PUBLIC_COMPOSE",
    "APP_ENV_FILE_PRESENT": "PUBLIC_COMPOSE",
    "PUBLIC_SERVICES": "PUBLIC_COMPOSE",
    "PRIVATE_PREVIEW_TREE_PRESENT": "PRIVATE_PREVIEW",
    "PRIVATE_PREVIEW_CONTAINERS_RUNNING": "PRIVATE_PREVIEW",
}


def _call(prefix, source: str, *, runner=None, timeout=18):
    """One fixed script on stdin; never execute a local shell or print output."""
    try:
        return (runner or subprocess.run)(
            prefix + ["sh", "-s"], input=source, capture_output=True,
            text=True, check=False, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def short_inventory(ssh_prefix, *, runner=None):
    """Return (full parsed report, failure stage), or (None, failure stage).

    parse_status remains the existing strict, complete, versioned parser.
    This module imports it only after the SSH commands to avoid a circular
    import. No partial inventory is ever a successful result.
    """
    from scripts.valyqon_vps_readonly_preflight import parse_status

    def request(label, script, *, allow_nonzero=False, timeout=18):
        outcome = _call(ssh_prefix, script, runner=runner, timeout=timeout)
        if outcome is None or not isinstance(outcome.returncode, int):
            raise _Blocked(_STAGE[label])
        if outcome.returncode == 255:
            raise _Blocked(_STAGE[label])
        if outcome.returncode not in (0, 1) or (outcome.returncode and not allow_nonzero):
            raise _Blocked(_STAGE[label])
        if not isinstance(outcome.stdout, str) or len(outcome.stdout) > 8192:
            raise _Blocked(_STAGE[label])
        return outcome

    try:
        schema = request("PREFLIGHT_SCHEMA", "echo PREFLIGHT_SCHEMA=2\n")
        if schema.stdout.strip() != "PREFLIGHT_SCHEMA=2":
            raise _Blocked("START")
        report = {"PREFLIGHT_SCHEMA": "2"}

        repo = request("REPO_PRESENT", "test -d /opt/tenderlens/.git\n",
                       allow_nonzero=True)
        report["REPO_PRESENT"] = "YES" if repo.returncode == 0 else "NO"

        if report["REPO_PRESENT"] == "YES":
            rev = request(
                "REMOTE_SHA",
                "git -C /opt/tenderlens rev-parse --verify HEAD 2>/dev/null\n",
                allow_nonzero=True,
            )
            value = rev.stdout.strip()
            report["REMOTE_SHA"] = (
                value if rev.returncode == 0 and re.fullmatch("[0-9a-f]{40}", value)
                else "UNKNOWN"
            )
            worktree = request(
                "WORKTREE_CLEAN",
                "GIT_OPTIONAL_LOCKS=0 git -C /opt/tenderlens status --porcelain 2>/dev/null\n",
                allow_nonzero=True,
            )
            report["WORKTREE_CLEAN"] = (
                "UNKNOWN" if worktree.returncode else
                "YES" if not worktree.stdout.strip() else "NO"
            )
        else:
            report.update(REMOTE_SHA="UNKNOWN", WORKTREE_CLEAN="UNKNOWN")

        docker = request("DOCKER_USABLE", "docker info >/dev/null 2>&1\n",
                         allow_nonzero=True)
        report["DOCKER_USABLE"] = "YES" if docker.returncode == 0 else "NO"

        compose = request(
            "PUBLIC_COMPOSE_PRESENT",
            "test -f /opt/tenderlens/compose.public.yaml\n",
            allow_nonzero=True,
        )
        report["PUBLIC_COMPOSE_PRESENT"] = "YES" if compose.returncode == 0 else "NO"

        env = request("APP_ENV_FILE_PRESENT", "test -f /opt/tenderlens/.env\n",
                      allow_nonzero=True)
        report["APP_ENV_FILE_PRESENT"] = "YES" if env.returncode == 0 else "NO"

        if report["DOCKER_USABLE"] == "YES" and report["PUBLIC_COMPOSE_PRESENT"] == "YES":
            services = request(
                "PUBLIC_SERVICES",
                "cd /opt/tenderlens && docker compose -f compose.public.yaml ps --services --status running 2>/dev/null\n",
                allow_nonzero=True, timeout=22,
            )
            if services.returncode:
                for name in ("api", "caddy", "bot"):
                    report[f"PUBLIC_{name}_RUNNING"] = "UNKNOWN"
            else:
                names = services.stdout.splitlines()
                if len(names) > 3 or len(set(names)) != len(names) or any(
                    name not in {"api", "caddy", "bot"} for name in names
                ):
                    raise _Blocked("PUBLIC_COMPOSE")
                for name in ("api", "caddy", "bot"):
                    report[f"PUBLIC_{name}_RUNNING"] = "YES" if name in names else "NO"
        else:
            for name in ("api", "caddy", "bot"):
                report[f"PUBLIC_{name}_RUNNING"] = "UNKNOWN"

        preview = request(
            "PRIVATE_PREVIEW_TREE_PRESENT",
            "test -d /home/ubuntu/valyqon-personal-preview\n",
            allow_nonzero=True,
        )
        report["PRIVATE_PREVIEW_TREE_PRESENT"] = "YES" if preview.returncode == 0 else "NO"

        if report["DOCKER_USABLE"] == "YES":
            containers = request(
                "PRIVATE_PREVIEW_CONTAINERS_RUNNING",
                "docker ps --filter label=com.docker.compose.project=valyqon-private-preview --format '{{.ID}}' 2>/dev/null\n",
                allow_nonzero=True,
            )
            report["PRIVATE_PREVIEW_CONTAINERS_RUNNING"] = (
                "UNKNOWN" if containers.returncode else
                "YES" if containers.stdout.strip() else "NO"
            )
        else:
            report["PRIVATE_PREVIEW_CONTAINERS_RUNNING"] = "UNKNOWN"

        report.update(
            TELEGRAM_BOT_API_ACK="NOT_CHECKED",
            LIVE_TENDER_DB="NOT_CHECKED",
            EXTERNAL_HTTPS="NOT_CHECKED",
            PRODUCTION_CHANGED="NO",
        )
        # Full provenance/required-key validation is shared with long mode.
        return parse_status("\n".join(f"{key}={value}" for key, value in report.items())), "COMPLETE"
    except (_Blocked, ValueError) as error:
        return None, error.stage if isinstance(error, _Blocked) else "COMPLETE"


class _Blocked(Exception):
    def __init__(self, stage):
        self.stage = stage
