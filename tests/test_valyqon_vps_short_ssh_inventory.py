"""Offline regression tests for strictly read-only, tiny SSH fallback.

No host, SSH identity, Docker, VPS or production connection is used.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import valyqon_vps_short_ssh_inventory as tiny
from scripts import valyqon_vps_readonly_preflight as full

SHA = "a" * 40


def run_fixed(args, **kwargs):
    assert args[-2:] == ["sh", "-s"]
    assert "StrictHostKeyChecking=yes" in args
    assert "IdentitiesOnly=yes" in args
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    assert kwargs["check"] is False
    assert kwargs["timeout"] in (18, 22)
    script = kwargs["input"]
    assert not any(x in script for x in (
        "git pull", "docker compose up", "docker compose down",
        "docker start", "cat /opt/tenderlens/.env", "curl ",
        "scp ", "ssh-keyscan", "chmod ", "rm -rf",
    ))
    rc, output = 0, ""
    if script == "echo PREFLIGHT_SCHEMA=2\n":
        output = "PREFLIGHT_SCHEMA=2\n"
    elif script == "test -d /opt/tenderlens/.git\n":
        pass
    elif "rev-parse --verify HEAD" in script:
        output = SHA + "\n"
    elif "GIT_OPTIONAL_LOCKS=0 git" in script:
        pass
    elif script == "command -v timeout >/dev/null 2>&1 && timeout 6s docker info >/dev/null 2>&1\n":
        pass
    elif script == "test -f /opt/tenderlens/compose.public.yaml\n":
        pass
    elif script == "test -f /opt/tenderlens/.env\n":
        pass
    elif "docker compose -f compose.public.yaml ps --services" in script:
        output = "api\ncaddy\n"
    elif script == "test -d /home/ubuntu/valyqon-personal-preview\n":
        pass
    elif "docker ps --filter label=com.docker.compose.project" in script:
        pass
    else:
        pytest.fail("Unexpected or non-reviewed remote shell statement")
    return SimpleNamespace(returncode=rc, stdout=output, stderr="PRIVATE")


def test_tiny_independent_inventory_proves_exact_schema_and_does_not_write():
    prefix = ["ssh", "-o", "StrictHostKeyChecking=yes",
              "-o", "IdentitiesOnly=yes", "-i", "/fake-ssh-key",
              "ubuntu@63.189.75.15"]
    report, stage = tiny.short_inventory(prefix, runner=run_fixed)
    assert stage == "COMPLETE"
    assert report["REPO_PRESENT"] == "YES"
    assert report["REMOTE_SHA"] == SHA
    assert report["WORKTREE_CLEAN"] == "YES"
    assert report["DOCKER_USABLE"] == "YES"
    assert report["PUBLIC_COMPOSE_PRESENT"] == "YES"
    assert report["APP_ENV_FILE_PRESENT"] == "YES"
    assert report["PUBLIC_api_RUNNING"] == "YES"
    assert report["PUBLIC_caddy_RUNNING"] == "YES"
    assert report["PUBLIC_bot_RUNNING"] == "NO"
    assert report["PRIVATE_PREVIEW_CONTAINERS_RUNNING"] == "NO"
    assert report["PRODUCTION_CHANGED"] == "NO"


def test_tiny_inventory_refuses_unexpected_service_output():
    def malicious(args, **kwargs):
        r = run_fixed(args, **kwargs)
        if "docker compose -f compose.public.yaml ps --services" in kwargs["input"]:
            r.stdout = "api\nprivate-secret-project\n"
        return r

    report, stage = tiny.short_inventory(["ssh", "-o", "StrictHostKeyChecking=yes", "-o", "IdentitiesOnly=yes", "host"], runner=malicious)
    assert report is None and stage == "PUBLIC_COMPOSE"


def test_tiny_inventory_refuses_failed_or_incomplete_first_probe():
    calls = []
    def fail(args, **kwargs):
        calls.append(kwargs["input"])
        return SimpleNamespace(returncode=2, stdout="secret", stderr="PRIVATE")
    report, stage = tiny.short_inventory(["ssh", "-o", "StrictHostKeyChecking=yes", "-o", "IdentitiesOnly=yes", "host"], runner=fail)
    assert report is None and stage == "START"
    assert calls == ["echo PREFLIGHT_SCHEMA=2\n"]


def test_do_not_mark_failed_docker_as_working():
    def cannot_docker(args, **kwargs):
        r = run_fixed(args, **kwargs)
        if kwargs["input"] == "command -v timeout >/dev/null 2>&1 && timeout 6s docker info >/dev/null 2>&1\n":
            r.returncode = 1
        return r

    report, stage = tiny.short_inventory(["ssh", "-o", "StrictHostKeyChecking=yes", "-o", "IdentitiesOnly=yes", "host"], runner=cannot_docker)
    assert stage == "COMPLETE"
    assert report["DOCKER_USABLE"] == "NO"
    assert report["PUBLIC_api_RUNNING"] == "UNKNOWN"
    assert report["PUBLIC_caddy_RUNNING"] == "UNKNOWN"


def test_original_inspect_falls_back_to_tiny_inventory_only_after_verified_ssh(
    tmp_path, monkeypatch,
):
    key = tmp_path / "test-identity"
    key.write_text("synthetic")
    stages = []
    def simulated(args, **kwargs):
        script = kwargs["input"]
        if script == full.REMOTE:
            stages.append("full")
            return SimpleNamespace(returncode=2, stdout="SECRET", stderr="PRIVATE")
        if script == "echo VALYQON_REMOTE_SHELL_OK\n":
            stages.append("identity")
            return SimpleNamespace(returncode=0, stdout="VALYQON_REMOTE_SHELL_OK\n",
                                   stderr="")
        if script.startswith("set -u\n"):
            stages.append("segmented")
            return SimpleNamespace(returncode=2, stdout="", stderr="PRIVATE")
        stages.append("tiny")
        return run_fixed(args, **kwargs)

    monkeypatch.setattr(full.subprocess, "run", simulated)
    report, same = full.inspect("63.189.75.15", key, expected_sha=SHA)
    assert same is True
    assert report["PUBLIC_caddy_RUNNING"] == "YES"
    assert report["PRODUCTION_CHANGED"] == "NO"
    assert stages[:3] == ["full", "identity", "segmented"]
    assert stages.count("tiny") >= 7


def test_original_inspect_does_not_claim_success_on_tiny_failure(tmp_path, monkeypatch):
    key = tmp_path / "test"
    key.write_text("synthetic")
    def simulated(args, **kwargs):
        script = kwargs["input"]
        if script == "echo VALYQON_REMOTE_SHELL_OK\n":
            return SimpleNamespace(returncode=0, stdout="VALYQON_REMOTE_SHELL_OK\n", stderr="")
        return SimpleNamespace(returncode=2, stdout="PRIVATE", stderr="PRIVATE")
    monkeypatch.setattr(full.subprocess, "run", simulated)
    with pytest.raises(full.SSHPreflightError) as exc:
        full.inspect("63.189.75.15", key, expected_sha=SHA)
    assert exc.value.failure_code == "SSH_REMOTE_SCRIPT_FAILED"
    assert exc.value.stage == "START"
    assert "PRIVATE" not in str(exc.value)


def test_timeout_of_docker_daemon_preserves_complete_read_only_inventory():
    """A stuck Docker daemon blocks readiness, not the whole SSH inventory."""
    import subprocess

    def docker_hangs(args, **kwargs):
        if kwargs["input"].startswith("command -v timeout") and "docker info" in kwargs["input"]:
            raise subprocess.TimeoutExpired(args, kwargs["timeout"])
        return run_fixed(args, **kwargs)

    report, stage = tiny.short_inventory(
        ["ssh", "-o", "StrictHostKeyChecking=yes",
         "-o", "IdentitiesOnly=yes", "host"],
        runner=docker_hangs,
    )
    assert stage == "COMPLETE"
    assert report["REPO_PRESENT"] == "YES"
    assert report["REMOTE_SHA"] == SHA
    assert report["DOCKER_USABLE"] == "UNKNOWN"
    assert report["PUBLIC_api_RUNNING"] == "UNKNOWN"
    assert report["PUBLIC_caddy_RUNNING"] == "UNKNOWN"
    assert report["PRODUCTION_CHANGED"] == "NO"


def test_ssh_transport_255_on_docker_command_never_returns_inventory():
    def auth_revoked(args, **kwargs):
        if "docker info" in kwargs["input"]:
            return SimpleNamespace(returncode=255, stdout="", stderr="private key")
        return run_fixed(args, **kwargs)

    report, stage = tiny.short_inventory(
        ["ssh", "-o", "StrictHostKeyChecking=yes",
         "-o", "IdentitiesOnly=yes", "host"],
        runner=auth_revoked,
    )
    assert report is None and stage == "DOCKER"
