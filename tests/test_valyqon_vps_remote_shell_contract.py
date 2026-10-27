"""Execute the real pinned-SSH read-only payload under a disposable POSIX shell.

Simulates command failures. No network, real SSH key, Docker daemon or production
path is accessed: absolute operator paths are replaced with temporary folders.
"""
from __future__ import annotations

import os
import shutil
import subprocess

import pytest

from scripts import valyqon_vps_readonly_preflight as probe


@pytest.mark.skipif(shutil.which("sh") is None, reason="POSIX shell unavailable")
@pytest.mark.parametrize(
    "git_status,docker_compose,expected_clean,expected_api,expected_caddy",
    [
        ("fail", "fail", "UNKNOWN", "UNKNOWN", "UNKNOWN"),
        ("clean", "running", "YES", "YES", "YES"),
        ("dirty", "running", "NO", "YES", "YES"),
    ],
)
def test_readonly_remote_report_preserves_unknown_on_failed_commands(
    tmp_path, git_status, docker_compose, expected_clean, expected_api,
    expected_caddy,
):
    repo = tmp_path / "disposable-repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "compose.public.yaml").write_text("services: {}\n", encoding="utf-8")
    (repo / ".env").write_text("synthetic=YES\n", encoding="utf-8")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    git = bindir / "git"
    git.write_text(
        "#!/bin/sh\n"
        "case \"$*\" in\n"
        "  *rev-parse*) echo 0123456789abcdef0123456789abcdef01234567;;\n"
        f"  *status*) {'exit 129' if git_status=='fail' else 'echo modified' if git_status=='dirty' else ':'};;\n"
        "  *) exit 125;;\n"
        "esac\n", encoding="utf-8",
    )
    docker = bindir / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        "case \"$*\" in\n"
        "  info) exit 0;;\n"
        f"  *compose*) {'exit 17' if docker_compose=='fail' else 'printf \'api\\ncaddy\\n\''};;\n"
        "  *ps*) exit 0;;\n"
        "  *) exit 125;;\n"
        "esac\n", encoding="utf-8",
    )
    git.chmod(0o700)
    docker.chmod(0o700)
    payload = (probe.REMOTE
               .replace("/opt/tenderlens", str(repo))
               .replace("/home/ubuntu/valyqon-personal-preview",
                        str(tmp_path / "isolated-preview")))
    environment = {
        "PATH": str(bindir) + os.pathsep + os.environ.get("PATH", ""),
        "HOME": str(tmp_path),
    }
    syntax = subprocess.run(
        ["sh", "-n"], input=payload, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=environment, timeout=8,
    )
    assert syntax.returncode == 0, "The read-only SSH POSIX payload must parse"
    run = subprocess.run(
        ["sh", "-s"], input=payload, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=environment, cwd=tmp_path, timeout=12,
    )
    assert run.returncode == 0, "Unexpected local read-only payload failure"
    result = probe.parse_status(run.stdout)
    assert result["PREFLIGHT_SCHEMA"] == "2"
    assert result["REMOTE_SHA"] == "0123456789abcdef0123456789abcdef01234567"
    assert result["WORKTREE_CLEAN"] == expected_clean
    assert result["PUBLIC_api_RUNNING"] == expected_api
    assert result["PUBLIC_caddy_RUNNING"] == expected_caddy
    assert result["PUBLIC_bot_RUNNING"] == (
        "UNKNOWN" if docker_compose == "fail" else "NO"
    )
    assert result["DOCKER_USABLE"] == "YES"
    assert result["PRODUCTION_CHANGED"] == "NO"
    assert probe._safe_remote_stage(run.stderr) == "COMPLETE"
    assert "synthetic=YES" not in run.stdout
    assert "synthetic=YES" not in run.stderr
