"""Validate resolved Docker Compose public release configuration.

Reads compose config JSON after interpolation with a synthetic .env. No
containers are run; PASS is configuration only, not live acceptance.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

from scripts.ci_public_pilot_release_policy import UNVERIFIED_FLAGS

EXPECTED_PORTS = {("80", "80", "tcp"), ("443", "443", "tcp"), ("443", "443", "udp")}


def violations(document: dict) -> list[str]:
    errors=[]
    if not isinstance(document, dict) or not isinstance(document.get("services"),dict):
        return ["Invalid resolved Compose document"]
    services=document["services"]
    if set(services)!={"api","bot","caddy"}:
        errors.append("Unexpected public services; only api, bot, caddy allowed")
        return errors
    for name in ("api","bot"):
        service=services[name]
        if service.get("ports"):
            errors.append(name+" must never publish host ports")
        env=service.get("environment")
        if not isinstance(env,dict):
            errors.append(name+" environment missing")
            continue
        if str(env.get("APP_ENV")).lower()!="production":
            errors.append(name+" must have production environment")
        if str(env.get("MONITORING_ENABLED")).lower()!="false":
            errors.append(name+" background monitoring must be off")
        for flag in UNVERIFIED_FLAGS:
            if str(env.get(flag)).lower()!="false":
                errors.append(name+" unverified feature must be off: "+flag)
    api=services["api"]
    bot=services["bot"]
    if api.get("profiles"):
        errors.append("API must be active by default")
    if bot.get("profiles")!=["verified-bot"]:
        errors.append("Bot must require verified-bot profile: MONITORING=false alone is insufficient")
    for flag,want in (
        ("VALYQON_PUBLIC_ANALYTICS_MODE","real"),
        ("VALYQON_RESTRICT_PAID_SOURCE_DETAILS","true"),
    ):
        if str(api.get("environment",{}).get(flag)).lower()!=want:
            errors.append("Invalid API effective flag: "+flag)
    caddy=services["caddy"]
    if caddy.get("profiles"):
        errors.append("Public HTTPS proxy must start by default")
    ports=caddy.get("ports")
    if not isinstance(ports,list):
        errors.append("Missing Caddy published ports")
    else:
        found=set()
        for row in ports:
            if not isinstance(row,dict):
                errors.append("Invalid Caddy port record")
                continue
            found.add((str(row.get("published")),str(row.get("target")),str(row.get("protocol","tcp"))))
        if found!=EXPECTED_PORTS:
            errors.append("Public edge must expose only 80/tcp, 443/tcp, 443/udp")
    dependencies=caddy.get("depends_on")
    depends=set(dependencies) if isinstance(dependencies,(dict,list)) else set()
    if depends!={"api"}:
        errors.append("Caddy must depend on API only")
    if not caddy.get("environment",{}).get("TENDERLENS_DOMAIN"):
        errors.append("Public domain missing")
    return errors


def main() -> int:
    if len(sys.argv)!=2:
        raise SystemExit("Usage: python -m scripts.ci_public_compose_resolved <config.json>")
    document=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    issues=violations(document)
    print("RESOLVED_PUBLIC_COMPOSE="+("BLOCKED" if issues else "PASS"))
    print("RESOLVED_PUBLIC_POLICY_ISSUES="+json.dumps(issues,ensure_ascii=False))
    print("BOT_DEFAULT_POLLING="+("BLOCKED" if not issues else "NOT_VERIFIED"))
    print("CURRENT_UPSTREAM_WORKER_DELIVERY=NOT_TESTED")
    print("PRODUCTION_DEPLOYMENT=NOT_PERFORMED")
    return int(bool(issues))


if __name__=="__main__":
    raise SystemExit(main())
