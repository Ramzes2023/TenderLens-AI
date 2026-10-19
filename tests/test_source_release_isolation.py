"""Release isolation: external-source live workflows may not be triggered by unrelated adapters.

These are offline trigger-contract tests. They do NOT prove publisher availability,
real notices, or production delivery. Shared regressions are exercised by main CI.
"""
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = {
    "cis-kz-gov-public-html-live.yml": "app/sources/kz_gov_html.py",
    "asia-jetro-bid-acceptance.yml": "app/sources/jp_jetro_bid_rss.py",
    "asia-seven-query-acceptance.yml": "app/sources/asia_seven.py",
    "asia-source-acceptance.yml": "app/sources/asia_public.py",
    "ru-b2b-bounded-fallback.yml": "app/sources/b2b_center.py",
    "ru-b2b-real-worker.yml": "app/sources/b2b_center.py",
    "ru-dagestan-public-list-optin.yml": "app/sources/ru_dagestan_public_list.py",
    "ru-nmck-native-acceptance.yml": "app/sources/nmck_native_public.py",
    "ru-south-ural-metadata.yml": "app/sources/south_ural_public.py",
    "ru-south-ural-depth.yml": "app/sources/south_ural_public.py",
    "ru-kavkaz-rf-firstparty-live.yml": "app/sources/kavkaz_rf_firstparty.py",
    "ru-south-ural-research.yml": "scripts/research_ru_south_ural_public.py",
    "ru-stan-commercial-acceptance.yml": "app/sources/stan_commercial_public.py",
    "ru-south-ural-integration.yml": "app/sources/south_ural_public.py",
    "ru-stan-commercial-probe.yml": "scripts/research_ru_stan_commercial.py",
}
GENERIC_LIVE_TRIGGERS = {
    "app/sources/**",
    "app/sources/catalog.py",
    "app/sources/ingestion.py",
    "app/sources/opportunities.py",
    "app/monitoring/config.py",
    "tests/test_source_catalog.py",
    "tests/test_connector_workers.py",
}


def workflow_events(name):
    document = yaml.safe_load(
        (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
    )
    # YAML 1.1 parses the unquoted GitHub 'on:' key as a boolean True.
    result = document.get("on", document.get(True))
    assert isinstance(result, dict), name
    return result


@pytest.mark.parametrize("name,own_adapter", WORKFLOWS.items())
def test_live_pr_gates_are_owned_by_their_publisher(name, own_adapter):
    events = workflow_events(name)
    assert "pull_request" in events
    paths = events["pull_request"].get("paths", [])
    assert paths and all(isinstance(p, str) for p in paths)
    assert own_adapter in paths
    assert not GENERIC_LIVE_TRIGGERS.intersection(paths), name
    # Editing the workflow's own YAML is a configuration change, not
    # evidence that the publisher itself changed or became unavailable.
    # The repository-wide isolation contract must check these edits instead.
    assert f".github/workflows/{name}" not in paths
    assert "workflow_dispatch" in events, "Strict source live verification must remain available"


def test_shared_core_and_source_contracts_still_run():
    core = workflow_events("ci.yml")
    assert "pull_request" in core
    assert not core["pull_request"].get("paths"), "Shared CI must not be path-limited"
    source = workflow_events("ru-source-contracts.yml")
    assert "pull_request" in source
    assert "app/sources/**" in source["pull_request"]["paths"]
    # Independent live source gates are not substitutes for these shared checks.
    ci_text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "python -m pytest" in ci_text
