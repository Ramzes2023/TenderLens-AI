"""No network: deployment preflight guard contracts for the existing AWS VPS."""
from types import SimpleNamespace
import pytest

from scripts import valyqon_vps_readonly_preflight as probe


def response(sha="a" * 40, running=("api", "caddy")):
    markers = {
        "PREFLIGHT_SCHEMA": "2",
        "REPO_PRESENT": "YES", "REMOTE_SHA": sha,
        "WORKTREE_CLEAN": "YES", "DOCKER_USABLE": "YES",
        "PUBLIC_COMPOSE_PRESENT": "YES",
        "APP_ENV_FILE_PRESENT": "YES",
        "PRIVATE_PREVIEW_TREE_PRESENT": "YES",
        "PRIVATE_PREVIEW_CONTAINERS_RUNNING": "YES",
        "PUBLIC_api_RUNNING": "YES" if "api" in running else "NO",
        "PUBLIC_caddy_RUNNING": "YES" if "caddy" in running else "NO",
        "PUBLIC_bot_RUNNING": "YES" if "bot" in running else "NO",
        "TELEGRAM_BOT_API_ACK": "NOT_CHECKED",
        "LIVE_TENDER_DB": "NOT_CHECKED",
        "EXTERNAL_HTTPS": "NOT_CHECKED",
        "PRODUCTION_CHANGED": "NO",
    }
    return "\n".join(f"{k}={v}" for k, v in markers.items()) + "\n"


@pytest.mark.parametrize("host", [
    "127.0.0.1", "10.0.0.8", "::1", "-oProxyCommand=x",
    "x@evil.org", "example.com;rm -rf /", "local",
])
def test_never_ssh_invalid_or_private_targets(host):
    with pytest.raises(ValueError):
        probe.validated_host(host)


def test_pinned_host_key_readonly_only_and_exact_sha(tmp_path, monkeypatch):
    key = tmp_path / "test_ed25519"
    key.write_text("not a real key")
    observed = []
    def fake_subprocess(argv, **kw):
        observed.append((argv, kw))
        return SimpleNamespace(returncode=0, stdout=response())
    monkeypatch.setattr(probe.subprocess, "run", fake_subprocess)
    got, same = probe.inspect("63.189.75.15", key, expected_sha="a" * 40)
    assert same and got["REMOTE_SHA"] == "a" * 40
    argv, kw = observed[0]
    assert argv[0] == "ssh" and argv[-2:] == ["sh", "-s"]
    assert "StrictHostKeyChecking=yes" in argv
    assert "BatchMode=yes" in argv
    assert "IdentitiesOnly=yes" in argv
    assert "StrictHostKeyChecking=no" not in argv
    assert "ProxyCommand" not in str(argv)
    assert kw["input"] == probe.REMOTE and kw["timeout"] == 45
    assert kw["capture_output"] and kw["text"]
    for dangerous in ("git pull", "docker compose up", "docker compose down",
                      "docker compose build", "sendMessage", "cat /opt/tenderlens/.env",
                      "rm -rf", "chmod", "ssh-keyscan"):
        assert dangerous not in probe.REMOTE


def test_incomplete_malicious_and_secret_output_is_never_accepted():
    for payload in (
        response().replace("PRODUCTION_CHANGED=NO", "PRODUCTION_CHANGED=YES"),
        response() + "AWS_SECRET_KEY=top-secret\n",
        response().replace("REMOTE_SHA=" + "a"*40, "REMOTE_SHA=secret"),
        response().replace("PREFLIGHT_SCHEMA=2", "PREFLIGHT_SCHEMA=3"),
        response().replace("APP_ENV_FILE_PRESENT=YES\n", ""),
    ):
        with pytest.raises(ValueError):
            probe.parse_status(payload)


def test_missing_key_or_unsafe_expected_revision_prevents_network(tmp_path, monkeypatch):
    monkeypatch.setattr(probe.subprocess, "run",
                        lambda *_a, **_kw: pytest.fail("ssh must not run"))
    with pytest.raises(ValueError):
        probe.inspect("63.189.75.15", tmp_path/"missing", expected_sha="a"*40)
    key = tmp_path / "present"
    key.write_text("x")
    with pytest.raises(ValueError):
        probe.inspect("63.189.75.15", key, expected_sha="main;touch /tmp/file")


def test_ssh_transport_failure_does_not_expose_private_stderr(tmp_path, monkeypatch):
    key = tmp_path/"key"
    key.write_text("x")
    monkeypatch.setattr(probe.subprocess, "run", lambda *_a, **_kw:
                        SimpleNamespace(returncode=255, stdout="",
                                        stderr="private-secret SSH key:token"))
    with pytest.raises(RuntimeError, match="private error suppressed") as exc:
        probe.inspect("63.189.75.15", key)
    assert "private-secret" not in str(exc.value)


def test_private_preview_is_reported_but_never_counts_as_public_release():
    result = probe.parse_status(response(
        sha="a" * 40, running=(),
    ).replace("REPO_PRESENT=YES", "REPO_PRESENT=NO")
     .replace("PUBLIC_COMPOSE_PRESENT=YES", "PUBLIC_COMPOSE_PRESENT=NO")
     .replace("APP_ENV_FILE_PRESENT=YES", "APP_ENV_FILE_PRESENT=NO")
     .replace("PRIVATE_PREVIEW_CONTAINERS_RUNNING=YES",
              "PRIVATE_PREVIEW_CONTAINERS_RUNNING=NO"))
    assert result["PRIVATE_PREVIEW_TREE_PRESENT"] == "YES"
    assert result["PRIVATE_PREVIEW_CONTAINERS_RUNNING"] == "NO"
    assert result["PUBLIC_api_RUNNING"] == "NO"
    assert result["PUBLIC_caddy_RUNNING"] == "NO"
    assert "docker compose up" not in probe.REMOTE
    assert "docker start" not in probe.REMOTE
    assert "docker stop" not in probe.REMOTE


def test_preview_inventory_missing_or_secret_output_is_rejected():
    for bad in (
        response().replace("PRIVATE_PREVIEW_TREE_PRESENT=YES\n", ""),
        response().replace("PRIVATE_PREVIEW_CONTAINERS_RUNNING=YES",
                           "PRIVATE_PREVIEW_CONTAINERS_RUNNING=token-secret"),
        response() + "PRIVATE_PREVIEW_TREE_PRESENT=NO\n",
    ):
        with pytest.raises(ValueError):
            probe.parse_status(bad)
