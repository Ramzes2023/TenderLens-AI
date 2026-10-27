"""Static no-network regression for explicit public AI operator opt-in."""
from pathlib import Path

from scripts.ci_public_pilot_release_policy import (
    ROOT, UNVERIFIED_FLAGS, public_pilot_failures,
)

BASE = (ROOT / "compose.public.yaml").read_text(encoding="utf-8")
OVERLAY = (ROOT / "compose.public-ai.yaml").read_text(encoding="utf-8")
TEMPLATE = (ROOT / ".env.example").read_text(encoding="utf-8")


def test_default_public_deployment_remains_fail_closed():
    assert 'VALYQON_PUBLIC_AI_ENABLED: "false"' in BASE
    assert "VALYQON_PUBLIC_AI_ENABLED" in UNVERIFIED_FLAGS
    assert "VALYQON_PUBLIC_AI_ENABLED=false" in TEMPLATE
    assert public_pilot_failures(BASE, TEMPLATE) == []


def test_operator_overlay_is_explicit_opt_in_only_for_api():
    assert 'VALYQON_PUBLIC_AI_ENABLED: "${VALYQON_PUBLIC_AI_ENABLED:-false}"' in OVERLAY
    assert OVERLAY.count("  api:") == 1
    assert "  bot:" not in OVERLAY
    assert "  connector-worker:" not in OVERLAY
    assert "  caddy:" not in OVERLAY
    assert "    ports:" not in OVERLAY
    assert "    volumes:" not in OVERLAY
    assert "GIGACHAT_CREDENTIALS:" not in OVERLAY
    assert "GROQ_API_KEY:" not in OVERLAY
    assert "VALYQON_RESTRICT_PAID_SOURCE_DETAILS:" not in OVERLAY
    assert "VALYQON_DEADLINE_ALERTS_ENABLED:" not in OVERLAY


def test_public_release_gate_still_rejects_unreviewed_activation():
    changed = BASE.replace('VALYQON_PUBLIC_AI_ENABLED: "false"',
                           'VALYQON_PUBLIC_AI_ENABLED: "true"', 1)
    assert any("VALYQON_PUBLIC_AI_ENABLED" in problem
               for problem in public_pilot_failures(changed, TEMPLATE))
