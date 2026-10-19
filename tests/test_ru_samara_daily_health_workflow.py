"""Samara daily real-source health cannot be turned into a fixture-only green."""
from pathlib import Path
import re

import yaml

PATH = Path(__file__).resolve().parents[1] / (
    ".github/workflows/ru-samara-public-list-daily-health.yml"
)


def workflow():
    text = PATH.read_text("utf-8")
    return text, yaml.safe_load(text)


def test_daily_is_read_only_default_branch_safe_and_no_prod_side_effects():
    text, doc = workflow()
    assert re.search(r"(?m)^on:\s*$", text)
    assert "cron: '13 6 * * *'" in text
    assert "workflow_dispatch:" in text and "pull_request:" in text
    assert doc["permissions"] == {"contents": "read"}
    assert doc["concurrency"]["cancel-in-progress"] is False
    assert "github.ref == 'refs/heads/main'" in text
    assert "secrets." not in text and "continue-on-error:" not in text
    for unsafe in (
        "docker compose up", "git push", "aws configure", "ssh -i",
        "RU_SAMARA_PUBLIC_LIST_ENABLED=true", "|| true",
        "ACTUAL_TELEGRAM_MESSAGE_DELIVERED=YES",
    ):
        assert unsafe not in text


def test_every_live_health_gate_is_real_and_fails_closed_without_original_details_claim():
    raw, doc = workflow()
    steps = doc["jobs"][
        "samara-real-list-to-sql-authenticated-tenant-and-local-alert"
    ]["steps"]
    commands = [str(step["run"]) for step in steps if "run" in step]
    required = [
        "python -B -m scripts.ci_ru_samara_public_list_sql",
        "python -B -m scripts.ci_ru_samara_authenticated",
        "python -B -m scripts.ci_ru_samara_telegram_query_delivery",
    ]
    assert all(commands.count(s) == 1 for s in required)
    assert sum("scripts.ci_ru_samara_" in s for s in commands) == 3
    assert any("PUBLIC_LIST_ONLY=YES" in s for s in commands)
    assert any("INDEPENDENT_NOTICE_DETAILS_PROVED=NO" in s for s in commands)
    assert any("ACTUAL_TELEGRAM_MESSAGE_DELIVERED=NO" in s for s in commands)
    assert any("PRODUCTION_ACTIVATION=NO" in s for s in commands)
    assert "pytest -q tests/test_ru_samara_daily_health_workflow.py" in raw
