"""Offline no-network tests for pinned-SSH Caddy topology classification."""
import json
import subprocess
from pathlib import Path

import pytest

from scripts import valyqon_public_caddy_topology as topology


def fake_runner(*, compose=True, repo=True, mount="false", hostkey_ok=True):
    observed = []
    def run(args, **kwargs):
        assert args[:2] == ["ssh", "-o"]
        assert "StrictHostKeyChecking=yes" in args
        assert "-i" in args
        assert "sh" == args[-2] and " -s" != args[-1] and args[-1] == "-s"
        assert kwargs["check"] is False
        source = kwargs["input"]
        observed.append(source)
        assert "cat /" not in source and "docker cp" not in source
        assert "docker stop" not in source and "docker restart" not in source
        assert "sudo" not in source and "env" not in source
        if not hostkey_ok:
            return subprocess.CompletedProcess(args, 255, stdout="", stderr="HOST KEY ERROR")
        if source.startswith("echo VALYQON"):
            stdout = "VALYQON_SSH_READ_ONLY_OK\n"
        elif source.startswith("docker ps"):
            stdout = "0123456789ab|caddy:2.11.6-alpine|public-caddy\n"
        elif "com.docker.compose.project" in source:
            stdout = "public-stack|caddy\n" if compose else "<no value>|unknown\n"
        elif "range .Mounts" in source:
            stdout = f"/etc/caddy/Caddyfile:{mount};/data:true;\n"
        elif "test -d" in source:
            stdout = "YES\n" if repo else "NO\n"
        elif "test -f" in source:
            stdout = "YES\n" if repo else "NO\n"
        else:
            raise AssertionError("Unreviewed remote command")
        return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr="")
    return run, observed


def test_safe_compatible_caddy_is_read_only(tmp_path):
    key = tmp_path / "existing-test-key"
    key.write_text("not a real key")
    runner, sent = fake_runner()
    result = topology.inspect("63.189.75.15", str(key), runner=runner)
    assert result["ssh"] == "PASS"
    assert result["docker"] == "PASS_READ_ONLY"
    assert result["edge_compose_service"] == "YES"
    assert result["edge_config_mount"] == "READ_ONLY"
    assert result["static_caddy_overlay_compatible"] is True
    assert result["production_changed"] is False
    assert result["backup_restore_proven"] is False
    assert result["rollback_proven"] is False
    assert len(sent) == 6


@pytest.mark.parametrize("alter", [
    {"compose": False}, {"repo": False}, {"mount": "true"},
])
def test_unknown_production_layout_never_authorizes_overlay(tmp_path, alter):
    key = tmp_path / "key"
    key.write_text("placeholder")
    runner, sent = fake_runner(**alter)
    status = topology.inspect("63.189.75.15", str(key), runner=runner)
    assert status["ssh"] == "PASS"
    assert status["static_caddy_overlay_compatible"] is False
    assert status["production_changed"] is False
    assert len(sent) == 6


def test_host_key_failure_never_retries_with_unverified_fingerprint(tmp_path):
    key = tmp_path / "key"
    key.write_text("placeholder")
    runner, sent = fake_runner(hostkey_ok=False)
    report = topology.inspect("63.189.75.15", str(key), runner=runner)
    assert report["ssh"] == "BLOCKED"
    assert len(sent) == 1 and report["production_changed"] is False


def test_missing_ssh_key_and_private_ip_rejected(tmp_path):
    with pytest.raises(ValueError):
        topology.inspect("63.189.75.15", str(tmp_path / "no-key"))
    key = tmp_path / "key"
    key.write_text("placeholder")
    with pytest.raises(ValueError):
        topology.inspect("127.0.0.1", str(key))


def test_no_edge_container_is_not_misrepresented_as_caddy(tmp_path):
    key = tmp_path / "key"
    key.write_text("placeholder")
    def run(args, **kwargs):
        s = kwargs["input"]
        result = "VALYQON_SSH_READ_ONLY_OK\n" if s.startswith("echo") else ""
        return subprocess.CompletedProcess(args, 0, stdout=result, stderr="")
    report = topology.inspect("63.189.75.15", str(key), runner=run)
    assert report["edge_instances"] == "NONE"
    assert report["static_caddy_overlay_compatible"] is False
