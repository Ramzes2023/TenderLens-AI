"""Railway-outage fallback is strictly marketing-only and manual deployment."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def test_render_blueprint_is_single_opt_in_public_pilot_service():
    source=(ROOT/"render.yaml").read_text(encoding="utf-8")
    required=[
        "services:", "- type: web", "name: valyqon-public-pilot",
        "runtime: docker", "plan: free", "region: frankfurt",
        "dockerfilePath: ./Dockerfile", "dockerContext: .",
        "dockerCommand: python -m app.public_pilot",
        "healthCheckPath: /health", "autoDeployTrigger: 'off'",
    ]
    for term in required:
        assert term in source,term
    assert source.count("- type: web")==1
    for forbidden in (
        "type: worker", "type: cron", "type: pserv", "databases:",
        "disk:", "numInstances:", "domains:", "preDeployCommand:",
        "initialDeployHook:", "autoDeployTrigger: commit",
        "value: true", "plan: starter", "plan: standard", "sync: false",
        "TELEGRAM_BOT_TOKEN", "GIGACHAT_", "DATABASE_URL:",
    ):
        assert forbidden not in source,forbidden


def test_fallback_uses_explicit_fail_closed_entrypoint():
    source=(ROOT/"app/public_pilot.py").read_text(encoding="utf-8")
    for setting in (
        '"VALYQON_PUBLIC_MARKETING_ONLY": "true"',
        '"VALYQON_PUBLIC_ANALYTICS_MODE": "real"',
        '"VALYQON_LEGAL_APPROVED": "false"',
        '"VALYQON_EMAIL_MODE": "disabled"',
        '"VALYQON_PUBLIC_AI_ENABLED": "false"',
        '"VALYQON_RESTRICT_PAID_SOURCE_DETAILS": "true"',
        '"VALYQON_DEADLINE_ALERTS_ENABLED": "false"',
        '"MONITORING_ENABLED": "false"',
        '"API_HOST"] = "0.0.0.0"',
        '"API_PORT"] = public_port',
    ):
        assert setting in source,setting
    assert "from app.api.__main__ import main as serve_api" in source


def test_railway_outage_procedure_does_not_claim_a_live_website():
    docs=(ROOT/"docs/PUBLIC_PILOT_RENDER_FALLBACK_RU.md").read_text(encoding="utf-8")
    assert "https://status.railway.com/" in docs
    assert "https://render.com/docs/free" in docs
    assert "NOT_DEPLOYED" in docs
    assert "autoDeployTrigger: off" in docs
    assert "production" in docs
