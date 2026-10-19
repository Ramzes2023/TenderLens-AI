"""Daily Dagestan public-list health must prove real Worker/SQL, not fixtures."""
from pathlib import Path
import re
import yaml


WORKFLOW = Path(__file__).resolve().parents[1] / (
    ".github/workflows/ru-dagestan-public-list-daily-health.yml"
)


def workflow():
    raw = WORKFLOW.read_text("utf-8")
    doc = yaml.safe_load(raw)
    assert type(doc) is dict
    return raw, doc


def test_daily_main_safe_readonly_schedule_and_manual_trigger():
    raw, doc = workflow()
    # PyYAML 1.1 may parse "on" as a boolean; the literal workflow must
    # explicitly include on: and not be replaced by a GitHub YAML trick.
    assert re.search(r"(?m)^on:\s*$", raw)
    assert re.search(r"(?m)^\s+- cron: '37 5 \* \* \*'\s*$", raw)
    assert "workflow_dispatch:" in raw and "pull_request:" in raw
    assert doc["permissions"] == {"contents": "read"}
    assert doc["concurrency"]["cancel-in-progress"] is False
    assert "github.ref == 'refs/heads/main'" in raw
    assert "secrets." not in raw and "with: write" not in raw


def test_live_health_is_really_original_list_worker_sql_and_tenant_keyword():
    raw, doc = workflow()
    jobs = doc["jobs"]
    health = jobs["original-public-list-to-fenced-sql-keyword-daily"]
    assert health["timeout-minutes"] <= 12
    steps = health["steps"]
    cmds = [str(x["run"]) for x in steps if "run" in x]
    real = [c for c in cmds if "scripts.ci_ru_dagestan_public_list_sql" in c]
    assert real == ["python -B -m scripts.ci_ru_dagestan_public_list_sql"]
    assert any("PRODUCTION_ACTIVATION=NO" in c for c in cmds)
    assert any("INDIVIDUAL_NOTICE_LOGIN_PROTECTED=YES" in c for c in cmds)
    assert "pytest" in " ".join(str(x) for x in jobs["strict-daily-health-contract"]["steps"])


def test_never_activates_deploys_or_emits_dummy_green():
    raw, _ = workflow()
    assert "PRODUCTION_ACTIVATION=NO" in raw
    banned = (
        "docker compose up", "git push", "ssh -i", "aws configure",
        "RU_DAGESTAN_PUBLIC_LIST_ENABLED=true",
        "continue-on-error: true", "|| true", "pytest -k dummy",
    )
    for item in banned:
        assert item not in raw
    assert "pytest -q tests/test_ru_dagestan_daily_health_workflow.py" in raw
