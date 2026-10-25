"""Public pilot security smoke — static evidence is NOT live tender acceptance."""
from pathlib import Path

import pytest

from scripts.ci_public_pilot_release_policy import (
    ROOT, UNVERIFIED_FLAGS, main, public_pilot_failures, service_regions,
)

COMPOSE = (ROOT / "compose.public.yaml").read_text(encoding="utf-8")
ENV = (ROOT / ".env.example").read_text(encoding="utf-8")


def test_approved_pilot_compose_only_exposes_caddy_and_disables_unverified_sources(capsys):
    assert public_pilot_failures(COMPOSE, ENV) == []
    assert main() == 0
    log = capsys.readouterr().out
    assert "PUBLIC_PILOT_STATIC_POLICY=PASS" in log
    assert "CURRENT_REAL_TENDER_INGESTION_VERIFIED_BY_THIS_STEP=NO" in log
    assert "REAL_TELEGRAM_BOT_API_ACK_VERIFIED_BY_THIS_STEP=NO" in log
    assert "PRODUCTION_CHANGED=NO" in log


@pytest.mark.parametrize("source_flag", UNVERIFIED_FLAGS)
def test_each_source_can_never_be_enabled_from_public_env_file(source_flag):
    # Either service can cause an unreviewed source/alert to go live.
    exposed = COMPOSE.replace(
        f'{source_flag}: "false"', f'{source_flag}: "true"', 1
    )
    assert source_flag in " ".join(public_pilot_failures(exposed, ENV))


def test_production_bot_alerts_cannot_be_implicitly_enabled():
    bad = COMPOSE.replace('MONITORING_ENABLED: "false"', 'MONITORING_ENABLED: "true"')
    assert any("Bot API" in x for x in public_pilot_failures(bad, ENV))


def test_demo_analytics_and_paywall_bypass_never_pass_static_release_gate():
    fake_demo = COMPOSE.replace('VALYQON_PUBLIC_ANALYTICS_MODE: "real"',
                                'VALYQON_PUBLIC_ANALYTICS_MODE: "demo"')
    assert any("demo" in x for x in public_pilot_failures(fake_demo, ENV))
    unlocked = COMPOSE.replace('VALYQON_RESTRICT_PAID_SOURCE_DETAILS: "true"',
                               'VALYQON_RESTRICT_PAID_SOURCE_DETAILS: "false"')
    assert any("billing" in x for x in public_pilot_failures(unlocked, ENV))


def test_no_accidental_direct_public_api_or_bot_ports():
    api = COMPOSE.replace("    expose:\n      - \"8000\"",
                          "    ports:\n      - \"8000:8000\"")
    assert any("publish" in x for x in public_pilot_failures(api, ENV))
    bot = COMPOSE.replace("  bot:\n    build:", "  bot:\n    ports:\n      - \"8001:8001\"\n    build:")
    assert any("publish" in x for x in public_pilot_failures(bot, ENV))


def test_duplicate_environment_override_is_rejected():
    altered = COMPOSE.replace('      GPB_ETP_PUBLIC_ENABLED: "false"',
                              '      GPB_ETP_PUBLIC_ENABLED: "false"\n'
                              '      GPB_ETP_PUBLIC_ENABLED: "false"', 1)
    assert any("Duplicate" in x for x in public_pilot_failures(altered, ENV))


def test_example_cannot_switch_to_illustrative_marketing_charts():
    fake = ENV.replace("VALYQON_PUBLIC_ANALYTICS_MODE=real",
                       "VALYQON_PUBLIC_ANALYTICS_MODE=demo")
    assert "Analytics .env example must use real source data only" in public_pilot_failures(COMPOSE, fake)


def test_no_production_or_network_mutation_inside_static_checker():
    code = (ROOT / "scripts/ci_public_pilot_release_policy.py").read_text()
    assert "requests." not in code and "httpx." not in code
    assert "docker compose up" not in code
    assert "subprocess." not in code
    assert set(("api", "bot", "caddy")).issubset(service_regions(COMPOSE))


def test_production_real_metrics_are_empty_when_no_verified_source_data():
    assert 'VALYQON_PUBLIC_ANALYTICS_MODE: "real"' in COMPOSE
    assert 'VALYQON_PUBLIC_ANALYTICS_MODE: "demo"' not in COMPOSE
    assert 'VALYQON_PUBLIC_ANALYTICS_MODE=real' in ENV
    assert 'MONITORING_ENABLED: "false"' in service_regions(COMPOSE)['bot']


def test_public_api_background_monitoring_also_cannot_start_from_stale_env():
    api_block = service_regions(COMPOSE)["api"]
    assert 'MONITORING_ENABLED: "false"' in api_block
    bad = COMPOSE.replace('MONITORING_ENABLED: "false"',
                          'MONITORING_ENABLED: "true"', 1)
    failures = public_pilot_failures(bad, ENV)
    assert any("api:" in f and "monitoring" in f for f in failures)


@pytest.mark.parametrize("flag", ("VALYQON_DEADLINE_ALERTS_ENABLED", "VALYQON_PUBLIC_AI_ENABLED"))
def test_public_ai_and_customer_deadline_sends_stay_off_in_both_services(flag):
    for name in ("api", "bot"):
        assert f'{flag}: "false"' in service_regions(COMPOSE)[name]
    malicious = COMPOSE.replace(f'{flag}: "false"', f'{flag}: "true"', 1)
    assert flag in " ".join(public_pilot_failures(malicious, ENV))
