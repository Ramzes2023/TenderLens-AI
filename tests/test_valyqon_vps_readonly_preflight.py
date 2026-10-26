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



@pytest.mark.parametrize("message,code", [
    ("Host key verification failed.", "SSH_HOST_KEY_UNVERIFIED"),
    ("WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!", "SSH_HOST_KEY_UNVERIFIED"),
    ("Permission denied (publickey).", "SSH_AUTH_REJECTED"),
    ("ssh: connect to host 203.0.113.7 port 22: Connection timed out", "SSH_CONNECT_TIMEOUT"),
    ("ssh: connect to host 203.0.113.7 port 22: Connection refused", "SSH_CONNECTION_REFUSED"),
    ("ssh: connect to host 203.0.113.7 port 22: No route to host", "SSH_ROUTE_UNREACHABLE"),
    ("Could not resolve hostname example.invalid", "SSH_DNS_FAILURE"),
    ("token=PRIVATE no useful details", "SSH_UNCLASSIFIED"),
])
def test_ssh_stderr_is_reported_as_enum_only(tmp_path, monkeypatch, message, code):
    key = tmp_path / "key"
    key.write_text("synthetic key not a credential")
    monkeypatch.setattr(probe.subprocess, "run", lambda *_a, **_kw: SimpleNamespace(
        returncode=255, stdout="", stderr=message,
    ))
    with pytest.raises(probe.SSHPreflightError) as result:
        probe.inspect("63.189.75.15", key)
    assert result.value.failure_code == code
    assert message not in str(result.value)
    assert "PRIVATE" not in str(result.value)


def test_subprocess_timeout_safe_code_not_private_stderr(tmp_path, monkeypatch):
    import subprocess
    key = tmp_path / "key"
    key.write_text("synthetic")
    def timeout(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="ssh PRIVATE", timeout=45,
                                        stderr=b"SECRET")
    monkeypatch.setattr(probe.subprocess, "run", timeout)
    with pytest.raises(probe.SSHPreflightError) as e:
        probe.inspect("63.189.75.15", key)
    assert e.value.failure_code == "SSH_PROCESS_TIMEOUT"
    assert "SECRET" not in str(e.value)


def test_main_emits_only_sanitized_failure_code(monkeypatch, capsys):
    monkeypatch.setattr(probe, "inspect", lambda *_a, **_kw: (
        (_ for _ in ()).throw(probe.SSHPreflightError("SSH_AUTH_REJECTED"))
    ))
    rc = probe.main(["--host", "63.189.75.15", "--key", "/dummy"])
    printed = capsys.readouterr().out
    assert rc == 2
    assert "FAILURE_CODE=SSH_AUTH_REJECTED" in printed
    assert "PRODUCTION_CHANGED=NO" in printed
    assert "token" not in printed.lower()


def test_remote_script_failure_is_distinguished_from_successful_minimal_ssh_shell(
    tmp_path, monkeypatch,
):
    key = tmp_path / "test"
    key.write_text("synthetic")
    calls = []

    def fake_runner(args, **kwargs):
        calls.append((args, kwargs))
        if len(calls) == 1:
            assert args[-2:] == ["sh", "-s"]
            assert kwargs["input"] == probe.REMOTE
            return SimpleNamespace(
                returncode=2, stdout="private data MUST NOT LEAK",
                stderr="SECRET\nVALYQON_PREFLIGHT_STAGE=DOCKER\nSSH PRIVATE",
            )
        assert args[-2:] == ["sh", "-s"]
        assert kwargs["input"] == "echo VALYQON_REMOTE_SHELL_OK\n"
        return SimpleNamespace(
            returncode=0, stdout="VALYQON_REMOTE_SHELL_OK\n",
            stderr="private SSH token",
        )

    monkeypatch.setattr(probe.subprocess, "run", fake_runner)
    with pytest.raises(probe.SSHPreflightError) as caught:
        probe.inspect("63.189.75.15", key)
    assert caught.value.failure_code == "SSH_REMOTE_SCRIPT_FAILED"
    assert caught.value.stage == "DOCKER"
    assert caught.value.exit_class == "REMOTE_NONZERO"
    assert "SECRET" not in str(caught.value)
    assert len(calls) == 2
    assert all("StrictHostKeyChecking=yes" in args
               and "IdentitiesOnly=yes" in args for args, _ in calls)


def test_remote_shell_restriction_is_not_misidentified_as_script_failure(
    tmp_path, monkeypatch,
):
    key = tmp_path / "test"
    key.write_text("synthetic")
    attempts = []

    def denied(args, **kwargs):
        attempts.append(args)
        if len(attempts) == 1:
            return SimpleNamespace(returncode=127, stdout="",
                                   stderr="SECRET; inaccessible shell")
        return SimpleNamespace(returncode=127, stdout="",
                               stderr="SECRET; sh missing")

    monkeypatch.setattr(probe.subprocess, "run", denied)
    with pytest.raises(probe.SSHPreflightError) as caught:
        probe.inspect("63.189.75.15", key)
    assert caught.value.failure_code == "SSH_REMOTE_SHELL_UNAVAILABLE"
    assert caught.value.stage == "UNKNOWN"
    assert caught.value.exit_class == "REMOTE_NONZERO"
    assert len(attempts) == 2


def test_ssh_stage_parser_is_enum_only_and_cannot_echo_private_data():
    assert probe._safe_remote_stage(
        "token=secret\nVALYQON_PREFLIGHT_STAGE=REPOSITORY\n"
        "VALYQON_PREFLIGHT_STAGE=DOCKER\n"
        "VALYQON_PREFLIGHT_STAGE=token_private"
    ) == "DOCKER"
    assert probe._safe_remote_stage(
        "VALYQON_PREFLIGHT_STAGE=UNKNOWN\nprivate"
    ) == "UNKNOWN"


def test_remote_failure_cli_reports_only_enum_and_exit_class(monkeypatch, capsys):
    def blocked(*_args, **_kwargs):
        raise probe.SSHPreflightError(
            "SSH_REMOTE_SCRIPT_FAILED", stage="PUBLIC_COMPOSE", exit_code=127
        )
    monkeypatch.setattr(probe, "inspect", blocked)
    assert probe.main(["--host", "63.189.75.15", "--key", "dummy"]) == 2
    output = capsys.readouterr().out
    assert "FAILURE_CODE=SSH_REMOTE_SCRIPT_FAILED" in output
    assert "FAILURE_STAGE=PUBLIC_COMPOSE" in output
    assert "FAILURE_EXIT_CLASS=REMOTE_NONZERO" in output
    assert "PRODUCTION_CHANGED=NO" in output
