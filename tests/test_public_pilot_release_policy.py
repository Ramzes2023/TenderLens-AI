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


def test_real_claims_and_paywall_bypass_never_pass_static_release_gate():
    fake_real = COMPOSE.replace('VALYQON_PUBLIC_ANALYTICS_MODE: "demo"',
                                'VALYQON_PUBLIC_ANALYTICS_MODE: "real"')
    assert any("demo" in x for x in public_pilot_failures(fake_real, ENV))
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


def test_example_never_advertises_fake_real_analytics():
    fake = ENV.replace("VALYQON_PUBLIC_ANALYTICS_MODE=demo",
                       "VALYQON_PUBLIC_ANALYTICS_MODE=real")
    assert "Analytics .env example must be demo" in public_pilot_failures(COMPOSE, fake)


def test_no_production_or_network_mutation_inside_static_checker():
    code = (ROOT / "scripts/ci_public_pilot_release_policy.py").read_text()
    assert "requests." not in code and "httpx." not in code
    assert "docker compose up" not in code
    assert "subprocess." not in code
    assert set(("api", "bot", "caddy")).issubset(service_regions(COMPOSE))
