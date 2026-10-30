"""Fail-closed public EIS registry contract (offline; no publisher or VPS access)."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

FLAGS = {
    "EIS_RSS_URLS": "",
    "EIS_PROFILE_FEEDS_ENABLED": "false",
    "EIS_223_RSS_URLS": "",
    "EIS_223_PROFILE_FEEDS_ENABLED": "false",
    "EIS_44_HTML_ENABLED": "false",
    "EIS_223_ENABLED": "false",
}


def compose(path):
    data = yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data["services"]


def assert_eis_disabled(environment):
    for name, expected in FLAGS.items():
        assert environment.get(name) == expected, (
            "Public source not proven ready but runtime flag remains active: " + name
        )


def test_real_public_api_cannot_advertise_default_eis_profile():
    services = compose("compose.public.yaml")
    assert_eis_disabled(services["api"]["environment"])


def test_isolated_six_source_public_worker_never_implicitly_enables_eis():
    services = compose("ops/public_sources/compose.yaml")
    raw = services["worker"]["environment"]
    env = {**services["guest-sources"]["environment"]}
    # The isolated compose uses a shared YAML anchor for all source flags.
    assert_eis_disabled(env)
    assert_eis_disabled(raw)


def test_production_optional_worker_does_not_activate_unverified_eis():
    services = compose("compose.public-operator.yaml")
    env = services["connector-worker"]["environment"]
    assert env["EIS_44_HTML_ENABLED"] == "false"
    assert env["EIS_223_ENABLED"] == "false"
    assert env["VALYQON_RU_BACKGROUND_CATALOG_ENABLED"] == "false"
