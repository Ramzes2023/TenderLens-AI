"""Static guard for actual read-only daily GPB integration health, not live proof."""
from pathlib import Path
import yaml

PATH = Path(".github/workflows/ru-gpb-firstparty-daily-live.yml")


def test_gpb_job_is_daily_and_offline_ci_is_not_live_substitute():
    workflow = yaml.load(PATH.read_text("utf-8"), Loader=yaml.BaseLoader)
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["on"]["schedule"] == [{"cron": "23 5 * * *"}]
    assert "workflow_dispatch" in workflow["on"]
    assert set(workflow["jobs"]) == {
        "gpb-daily-health-offline-security", "gpb-firstparty-live-worker-and-tenant",
    }
    job = workflow["jobs"]["gpb-firstparty-live-worker-and-tenant"]
    assert job["runs-on"] == "ubuntu-latest"
    cmds = [step.get("run") for step in job["steps"] if step.get("run")]
    a = "python -B -m scripts.ci_ru_gpb_public_worker"
    b = "python -B -m scripts.ci_ru_gpb_authenticated"
    assert a in cmds and b in cmds and cmds.index(a) < cmds.index(b)
    assert not any(step.get("continue-on-error") for step in job["steps"])


def test_gpb_checks_use_original_url_genuine_worker_and_ephemeral_sql():
    worker = Path("scripts/ci_ru_gpb_public_worker.py").read_text("utf-8")
    auth = Path("scripts/ci_ru_gpb_authenticated.py").read_text("utf-8")
    adapter = Path("app/sources/gpb_etp_public.py").read_text("utf-8")
    for token in ("JobRepository(", "Worker(", "ConnectorSyncService(",
                  "OpportunityRepository(", "TemporaryDirectory(",
                  "snapshot_catalog(", "etpgpb.ru/procedures/etp/"):
        assert token in worker, token
    for token in ("TestClient(", "status_code != 403", "snapshot_catalog(",
                  "source.fetch(", "TemporaryDirectory("):
        assert token in auth, token
    for token in ('follow_redirects=False', 'trust_env=False', 'parse_gpb_verified_detail('):
        assert token in adapter, token


def test_runner_no_credentials_faked_live_or_network_downgrade():
    data = PATH.read_text("utf-8").lower()
    for bad in ("self-hosted", "pull_request_target", "continue-on-error",
                "secrets.", "aws ", "|| true", "curl -k", "--insecure",
                "mocktransport", "skip-live", "production_changed=yes"):
        assert bad not in data
    assert "persist-credentials: false" in data
