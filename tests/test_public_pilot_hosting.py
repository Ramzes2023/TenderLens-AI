"""Marketing-only hosting release is fail-closed, not a commercial SaaS launch."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from app.public_pilot import PUBLIC_PILOT_BLOCKED_FLAGS, main
from app.api.landing import landing_html


ROOT = Path(__file__).resolve().parents[1]


def test_marketing_pilot_prevents_unaccepted_features_and_uses_host_port(monkeypatch):
    monkeypatch.setenv("PORT", "13749")
    for key in PUBLIC_PILOT_BLOCKED_FLAGS:
        monkeypatch.setenv(key, "true" if key.endswith("ENABLED") else "demo")
    entered=[]
    from app.api import __main__ as api_launcher
    monkeypatch.setattr(api_launcher, "main", lambda: entered.append(True) or 0)
    assert main()==0
    assert entered==[True]
    assert __import__("os").environ["API_PORT"]=="13749"
    assert __import__("os").environ["API_HOST"]=="0.0.0.0"
    for key,value in PUBLIC_PILOT_BLOCKED_FLAGS.items():
        assert __import__("os").environ[key]==value
    assert PUBLIC_PILOT_BLOCKED_FLAGS["VALYQON_LEGAL_APPROVED"]=="false"
    assert PUBLIC_PILOT_BLOCKED_FLAGS["VALYQON_EMAIL_MODE"]=="disabled"
    assert PUBLIC_PILOT_BLOCKED_FLAGS["VALYQON_PUBLIC_ANALYTICS_MODE"]=="real"
    assert PUBLIC_PILOT_BLOCKED_FLAGS["VALYQON_RESTRICT_PAID_SOURCE_DETAILS"]=="true"


@pytest.mark.parametrize("port",["", "0", "-1", "65536", "not-an-integer", "8080;rm", " 8000"])
def test_public_pilot_refuses_untrusted_bind_ports(monkeypatch,port):
    monkeypatch.setenv("PORT",port)
    assert main()==2


def test_public_preview_landing_does_not_offer_disabled_registration(monkeypatch):
    monkeypatch.setenv("VALYQON_PUBLIC_MARKETING_ONLY","true")
    html=landing_html()
    assert "Public product preview." in html
    assert "payments" in html
    assert 'href="/register"' not in html
    assert "Create account" not in html
    assert "Explore features" in html
    assert 'href="/how-it-works"' in html
    assert 'id="guestSearchForm"' in html


def test_regular_application_landing_unchanged(monkeypatch):
    monkeypatch.delenv("VALYQON_PUBLIC_MARKETING_ONLY",raising=False)
    html=landing_html()
    assert 'href="/register"' in html
    assert "Create account" in html
    assert "Public product preview." not in html


def test_hosting_config_uses_reviewed_image_without_claiming_real_service():
    config=json.loads((ROOT/"railway.json").read_text(encoding="utf-8"))
    assert config["build"]["builder"]=="DOCKERFILE"
    assert config["build"]["dockerfilePath"]=="Dockerfile"
    assert config["deploy"]["startCommand"]=="python -m app.public_pilot"
    assert config["deploy"]["healthcheckPath"]=="/health"
    assert "VALYQON_PUBLIC_MARKETING_ONLY" in PUBLIC_PILOT_BLOCKED_FLAGS
    assert "VALYQON_PUBLIC_AI_ENABLED" in PUBLIC_PILOT_BLOCKED_FLAGS
    assert "VALYQON_RU_BACKGROUND_CATALOG_ENABLED" in PUBLIC_PILOT_BLOCKED_FLAGS
    assert "VALYQON_DEADLINE_ALERTS_ENABLED" in PUBLIC_PILOT_BLOCKED_FLAGS
