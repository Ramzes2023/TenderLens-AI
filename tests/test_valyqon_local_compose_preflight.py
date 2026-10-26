"""Offline temporary Compose verification never moves private source to EC2."""
from pathlib import Path

import pytest

from scripts import valyqon_local_compose_preflight as probe


def prepare(tmp_path):
    for name in probe.COPIED:
        (tmp_path / name).write_text("services: {}\n", encoding="utf-8")
    (tmp_path / ".env").write_text(
        "DATABASE_URL=postgresql://REAL_PRIVATE_PLACEHOLDER\n",
        encoding="utf-8",
    )


def test_temp_compose_uses_only_synthetic_env_and_does_not_modify_real_files(tmp_path, monkeypatch):
    prepare(tmp_path)
    monkeypatch.setattr(probe.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setenv("DATABASE_URL", "postgresql://REAL_PRIVATE_PLACEHOLDER")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "PRIVATE_TEST_TOKEN")
    target_contents = {name: (tmp_path / name).read_bytes() for name in probe.COPIED}
    real_env = (tmp_path / ".env").read_bytes()
    observed = []

    def validate_stub():
        import os
        cwd = Path.cwd()
        observed.append(cwd)
        assert cwd != tmp_path
        assert {p.name for p in cwd.iterdir()} == set(probe.COPIED) | {".env"}
        fake = (cwd / ".env").read_text()
        assert "PRIVATE" not in fake
        assert "synthetic" in fake
        assert os.environ["DATABASE_URL"] == probe.FAKE_ENV["DATABASE_URL"]
        assert "TELEGRAM_BOT_TOKEN" not in os.environ or not os.environ["TELEGRAM_BOT_TOKEN"]
        return {"status": "OFFLINE_OPERATOR_COMPOSE_CONTRACTS_PASS",
                "default_services": ["api", "caddy"]}

    result = probe.local_probe(root=tmp_path, command=validate_stub)
    assert result["LOCAL_RELEASE_COMPOSE"] == "PASS"
    assert result["PRIVATE_SOURCE_SENT_TO_EC2"] == "NO"
    assert result["PRODUCTION_CHANGED"] == "NO"
    assert result["PUBLIC_LAUNCH_APPROVED"] == "NO"
    assert Path.cwd() != observed[0]
    assert not observed[0].exists()
    assert (tmp_path / ".env").read_bytes() == real_env
    assert all((tmp_path / k).read_bytes() == v for k, v in target_contents.items())


def test_missing_reviewed_compose_blocks_before_any_docker_call(tmp_path, monkeypatch):
    monkeypatch.setattr(probe.shutil, "which", lambda name: pytest.fail("Docker not allowed"))
    with pytest.raises(ValueError, match="Missing"):
        probe.local_probe(root=tmp_path)


def test_docker_missing_fails_closed(tmp_path, monkeypatch):
    prepare(tmp_path)
    monkeypatch.setattr(probe.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="not found"):
        probe.local_probe(root=tmp_path)


def test_bad_compose_response_is_never_public_launch_pass(tmp_path, monkeypatch):
    prepare(tmp_path)
    monkeypatch.setattr(probe.shutil, "which", lambda name: "/usr/bin/docker")
    with pytest.raises(ValueError, match="not approved"):
        probe.local_probe(root=tmp_path,
                         command=lambda: {"status": "unverified"})


def test_cli_fail_closed_with_no_remote_transfer(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(probe, "local_probe", lambda: (_ for _ in ()).throw(
        RuntimeError("PRIVATE cause must never appear")))
    assert probe.main() == 2
    out = capsys.readouterr().out
    assert "LOCAL_RELEASE_COMPOSE=BLOCKED" in out
    assert "PRIVATE_SOURCE_SENT_TO_EC2=NO" in out
    assert "PRIVATE cause" not in out
