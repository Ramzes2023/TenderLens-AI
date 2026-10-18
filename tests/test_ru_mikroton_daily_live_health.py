"""Fail-closed offline contract for independent daily Russian MikroTon live health."""
from pathlib import Path
import yaml

WORKFLOW = Path(".github/workflows/ru-mikroton-daily-live-health.yml")

def _workflow():
    return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

def test_real_live_health_scheduled_and_manually_dispatchable():
    workflow = _workflow()
    assert workflow["on"]["schedule"] == [{"cron": "43 4 * * *"}]
    assert "workflow_dispatch" in workflow["on"]
    assert workflow["permissions"] == {"contents": "read"}
    assert set(workflow["jobs"]) == {
        "mikroton-health-security-offline",
        "mikroton-official-api-real-leased-sql",
        "mikroton-real-authenticated-tenant",
    }

def test_no_fixtures_skips_secrets_production_or_untrusted_runner():
    workflow = _workflow()
    text = WORKFLOW.read_text(encoding="utf-8").lower()
    for unsafe in (
        "continue-on-error", "pull_request_target", "self-hosted",
        "secrets.", "curl -k", "--insecure", "skip-live",
        "mocktransport", "set +e", "|| true", "aws ", "docker login",
    ):
        assert unsafe not in text
    for job in workflow["jobs"].values():
        assert job["runs-on"] == "ubuntu-latest"
        assert not job.get("if")
        for step in job["steps"]:
            assert not step.get("continue-on-error")
            if step.get("uses", "").startswith("actions/checkout@"):
                assert step["with"]["persist-credentials"] == "false"

def test_official_api_actual_worker_sqlite_keyword_and_tenant_are_mandatory():
    workflow = _workflow()
    api = workflow["jobs"]["mikroton-official-api-real-leased-sql"]["steps"]
    commands = [step.get("run") for step in api if step.get("run")]
    assert "python -B -m scripts.ci_ru_mikroton_real_api" in commands
    assert "python -B -m scripts.ci_ru_mikroton_real_worker" in commands
    scoped = workflow["jobs"]["mikroton-real-authenticated-tenant"]["steps"]
    assert "python -B -m scripts.ci_ru_mikroton_authenticated" in [
        step.get("run") for step in scoped
    ]
    source = Path("scripts/ci_ru_mikroton_real_worker.py").read_text(encoding="utf-8")
    assert "run_leased_connector(db, catalog, store, SOURCE" in source
    assert "snapshot_catalog(catalog, store)" in source
    assert "search_terms=(row.external_id,)" in source
    assert "TemporaryDirectory" in source
    assert "SimpleNamespace" not in source
