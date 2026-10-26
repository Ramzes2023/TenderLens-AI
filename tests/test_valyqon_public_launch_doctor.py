"""Public SaaS release diagnostic: real verification boundaries, no remote writes."""
import json
from pathlib import Path
import pytest

from scripts import valyqon_public_launch_doctor as doctor
from scripts import valyqon_vps_readonly_preflight as ssh

REV = "c" * 40


def inputs(tmp_path, **changes):
    key=tmp_path/"private_test_only"
    key.write_text("synthetic")
    return {
        "ssh_host":"63.189.75.15",
        "ssh_key":str(key),
        "hostname":"63-189-75-15.sslip.io",
        "expected_sha":REV,
        **changes,
    }


def fake_ssh(_host, _key, *, expected_sha):
    assert expected_sha==REV
    return ({
        "REPO_PRESENT":"YES",
        "PUBLIC_COMPOSE_PRESENT":"YES",
        "PUBLIC_api_RUNNING":"YES",
        "PUBLIC_caddy_RUNNING":"YES",
        "PRIVATE_PREVIEW_TREE_PRESENT":"YES",
        "PRIVATE_PREVIEW_CONTAINERS_RUNNING":"YES",
    },True)


def fake_https(_url):
    return {"public_edge_pass":True,"homepage":"PASS","health":"PASS"}


def test_full_readonly_edge_is_not_commercial_launch(tmp_path):
    result=doctor.evaluate(**inputs(tmp_path),
        local_check=lambda:{"LOCAL_RELEASE_COMPOSE":"PASS"},
        ssh_check=fake_ssh,https_check=fake_https)
    assert result["technical_staging_edge_pass"] is True
    assert result["public_commercial_launch_approved"] is False
    assert result["production_changed"] is False
    assert result["private_preview_not_counted"] is True
    assert result["local_compose"]=="PASS_SYNTHETIC_ONLY"
    assert len(result["blocked_gates"])==7
    assert "postgresql_operator_restore" in result["blocked_gates"]
    assert "payment_provider_signed_entitlements" in result["blocked_gates"]
    report=json.dumps(result)
    assert str(inputs(tmp_path)["ssh_key"]) not in report
    assert "63.189.75.15" not in report
    assert "sslip.io" not in report


def test_preview_only_host_cannot_satisfy_public_deployment(tmp_path):
    def preview_only(*_a,**_k):
        return ({
            "REPO_PRESENT":"NO",
            "PUBLIC_COMPOSE_PRESENT":"NO",
            "PUBLIC_api_RUNNING":"NO",
            "PUBLIC_caddy_RUNNING":"NO",
            "PRIVATE_PREVIEW_TREE_PRESENT":"YES",
            "PRIVATE_PREVIEW_CONTAINERS_RUNNING":"YES",
        },False)
    r=doctor.evaluate(**inputs(tmp_path),local_check=lambda:{"LOCAL_RELEASE_COMPOSE":"PASS"},
        ssh_check=preview_only,https_check=fake_https)
    assert r["vps_public_tree"]=="BLOCKED"
    assert r["vps_exact_sha"]=="BLOCKED"
    assert r["vps_api_caddy"]=="BLOCKED"
    assert not r["technical_staging_edge_pass"]


def test_old_login_or_degraded_health_is_not_public_readiness(tmp_path):
    result=doctor.evaluate(**inputs(tmp_path),
        local_check=lambda:{"LOCAL_RELEASE_COMPOSE":"PASS"},
        ssh_check=fake_ssh,
        https_check=lambda _:{"public_edge_pass":False,"homepage":"NOT_VERIFIED",
                              "health":"NOT_VERIFIED","redirect_class":"login"})
    assert result["edge_failure_class"]=="login"
    assert result["external_https"]=="BLOCKED"
    assert not result["technical_staging_edge_pass"]
    assert not result["public_commercial_launch_approved"]


def test_ssh_fail_closed_with_sanitized_category_and_independent_edge(tmp_path):
    def inaccessible(*_a,**_k):
        raise ssh.SSHPreflightError("SSH_AUTH_REJECTED")
    result=doctor.evaluate(**inputs(tmp_path),
        local_check=lambda:{"LOCAL_RELEASE_COMPOSE":"PASS"},
        ssh_check=inaccessible,https_check=fake_https)
    assert result["vps_ssh"]=="BLOCKED_SSH_AUTH_REJECTED"
    assert result["external_https"]=="PASS"
    assert not result["technical_staging_edge_pass"]


@pytest.mark.parametrize("bad",[
    {"ssh_host":"127.0.0.1"},
    {"hostname":"localhost"},
    {"hostname":"127.0.0.1"},
    {"hostname":"unsafe.example.invalid"},
    {"expected_sha":"main"},
    {"expected_sha":"deadbeef"},
    {"ssh_key":"/missing/key"},
])
def test_invalid_target_key_sha_stops_before_any_effect(tmp_path,bad):
    seen=[]
    def must_not_run(*_a,**_kw):
        seen.append(True)
        raise AssertionError("external call was made")
    with pytest.raises(ValueError):
        doctor.evaluate(**inputs(tmp_path,**bad),
            local_check=must_not_run,ssh_check=must_not_run,https_check=must_not_run)
    assert not seen


def test_cli_redacts_local_key_and_remote_errors(tmp_path,monkeypatch,capsys):
    key=inputs(tmp_path)["ssh_key"]
    monkeypatch.setattr(doctor,"evaluate",lambda **_a:{
        "kind":"VALYQON_PUBLIC_LAUNCH_READ_ONLY",
        "technical_staging_edge_pass":False,
        "vps_ssh":"BLOCKED_SSH_CONNECT_TIMEOUT",
        "production_changed":False,
        "public_commercial_launch_approved":False,
    })
    rc=doctor.main(["--ssh-host","63.189.75.15","--ssh-key",key,
                     "--hostname","63-189-75-15.sslip.io","--expected-sha",REV])
    output=capsys.readouterr().out
    assert rc==2
    assert "BLOCKED_SSH_CONNECT_TIMEOUT" in output
    assert key not in output
    assert "PRIVATE" not in output
    assert "63.189.75.15" not in output
