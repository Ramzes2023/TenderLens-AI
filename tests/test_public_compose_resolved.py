"""Resolved Docker Compose gate (synthetic effective environment; no deploy)."""
from copy import deepcopy
from scripts.ci_public_compose_resolved import violations
from scripts.ci_public_pilot_release_policy import UNVERIFIED_FLAGS


def sample():
    settings = dict(APP_ENV="production", MONITORING_ENABLED="false")
    settings.update({key:"false" for key in UNVERIFIED_FLAGS})
    api=dict(environment={
        **settings, "VALYQON_PUBLIC_ANALYTICS_MODE":"real",
        "VALYQON_RESTRICT_PAID_SOURCE_DETAILS":"true",
    })
    bot=dict(environment=settings,profiles=["verified-bot"])
    caddy=dict(environment={"TENDERLENS_DOMAIN":"audit.example.org"},
        depends_on={"api":{"condition":"service_healthy"}},
        ports=[
            dict(published="80",target=80,protocol="tcp"),
            dict(published="443",target=443,protocol="tcp"),
            dict(published="443",target=443,protocol="udp"),
        ])
    return {"services":{"api":api,"bot":bot,"caddy":caddy}}


def test_resolved_public_config_is_safe():
    assert violations(sample())==[]


def test_bot_polling_profile_is_mandatory_even_if_monitoring_disabled():
    data=sample()
    del data["services"]["bot"]["profiles"]
    assert any("verified-bot" in msg for msg in violations(data))


def test_no_exposed_internal_ports_or_public_paid_details():
    for name in ("api","bot"):
        data=sample()
        data["services"][name]["ports"]=[dict(published="8000",target=8000)]
        assert any(name in msg and "ports" in msg for msg in violations(data))
    data=sample()
    data["services"]["api"]["environment"]["VALYQON_RESTRICT_PAID_SOURCE_DETAILS"]="false"
    assert any("paid" in msg.lower() for msg in violations(data))


def test_each_unverified_feature_fails_after_environment_interpolation():
    for flag in UNVERIFIED_FLAGS:
        for service in ("api","bot"):
            data=sample()
            data["services"][service]["environment"][flag]="true"
            assert flag in " ".join(violations(data))


def test_public_only_caddy_ports_and_active_api():
    data=sample()
    data["services"]["caddy"]["ports"].append(
        dict(published="18865",target=18865,protocol="tcp"))
    assert any("edge" in msg for msg in violations(data))
    data=sample()
    data["services"]["api"]["profiles"]=["manual-api"]
    assert any("API must" in msg for msg in violations(data))


def test_actual_public_requires_real_metrics_and_no_extra_service():
    data=sample()
    data["services"]["api"]["environment"]["VALYQON_PUBLIC_ANALYTICS_MODE"]="demo"
    assert any("ANALYTICS" in msg for msg in violations(data))
    data=sample()
    data["services"]["collector"]={}
    assert any("Unexpected public services" in msg for msg in violations(data))
