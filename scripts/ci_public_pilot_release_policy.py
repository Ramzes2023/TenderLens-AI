"""Fail-closed STATIC public-pilot deployment policy; not a live acceptance.

Never interprets a successful Compose/security review as actual tenders, payment
readiness, HTTPS availability or real Telegram Bot API customer delivery.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNVERIFIED_FLAGS = (
    "GPB_ETP_PUBLIC_ENABLED",
    "TEKTORG_PUBLIC_ENABLED",
    "B2B_CENTER_ENABLED",
    "EIS_44_HTML_ENABLED",
    "EIS_223_ENABLED",
    "VALYQON_RU_BACKGROUND_CATALOG_ENABLED",
    "ROSELTORG_PUBLIC_ENABLED",  # unmerged candidate; future default-deny
)


def service_regions(content: str) -> dict[str, str]:
    """Read only deterministic service boundaries, without a YAML dependency."""
    result: dict[str, str] = {}
    key = None
    lines: list[str] = []
    for line in content.splitlines():
        if line.startswith("  ") and not line.startswith("    ") and line.rstrip().endswith(":"):
            if key is not None:
                result[key] = "\n".join(lines)
            key = line.strip()[:-1]
            lines = []
        elif key is not None and (not line.strip() or line.startswith("    ")):
            lines.append(line)
        elif key is not None and line.strip() and not line.startswith(" "):
            result[key] = "\n".join(lines)
            key = None
            lines = []
    if key is not None:
        result[key] = "\n".join(lines)
    return result


def _environment(service: str):
    result = {}
    in_env = False
    for line in service.splitlines():
        if line == "    environment:":
            in_env = True
            continue
        if in_env and line.startswith("    ") and not line.startswith("      "):
            in_env = False
        if not in_env or not line.startswith("      ") or line.lstrip().startswith("#"):
            continue
        stripped = line.strip()
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key in result:
            raise ValueError("Duplicate security environment override: " + key)
        result[key] = value
    return result


def public_pilot_failures(compose: str, template: str) -> list[str]:
    services = service_regions(compose)
    problems = []
    for name in ("api", "bot", "caddy"):
        if name not in services:
            problems.append("Missing public service " + name)
    if problems:
        return problems
    for service_name in ("api", "bot"):
        body = services[service_name]
        if any(line == "    ports:" for line in body.splitlines()):
            problems.append(service_name + " must not publish API/bot ports")
        try:
            env = _environment(body)
        except ValueError as exc:
            problems.append(str(exc))
            continue
        if env.get("APP_ENV") != "production":
            problems.append(service_name + " must use production application settings")
        for key in UNVERIFIED_FLAGS:
            if env.get(key) != "false":
                problems.append(service_name + ": " + key + " must be forced false")
        if service_name == "bot" and env.get("MONITORING_ENABLED") != "false":
            problems.append("Unverified real Bot API sends must stay off in pilot")
        if service_name == "api":
            if env.get("VALYQON_PUBLIC_ANALYTICS_MODE") != "real":
                problems.append("Public metrics must use real data only; no illustrative/demo values")
            if env.get("VALYQON_RESTRICT_PAID_SOURCE_DETAILS") != "true":
                problems.append("Unverified merchant billing must not unlock paid details")
    if not any(line == "    ports:" for line in services["caddy"].splitlines()):
        problems.append("Public edge must explicitly publish only Caddy ports")
    defaults = {}
    for raw in template.splitlines():
        item = raw.strip()
        if not item or item.startswith("#") or "=" not in item:
            continue
        k, v = item.split("=", 1)
        defaults[k] = v.strip()
    for flag in UNVERIFIED_FLAGS:
        if flag in defaults and defaults[flag].lower() != "false":
            problems.append("Default is unsafe: " + flag)
    if defaults.get("VALYQON_PUBLIC_ANALYTICS_MODE") != "real":
        problems.append("Analytics .env example must use real source data only")
    return problems


def main() -> int:
    compose = (ROOT / "compose.public.yaml").read_text(encoding="utf-8")
    template = (ROOT / ".env.example").read_text(encoding="utf-8")
    failures = public_pilot_failures(compose, template)
    print("PUBLIC_PILOT_STATIC_POLICY=" + ("BLOCKED" if failures else "PASS"))
    print("PUBLIC_PILOT_RULES=" + json.dumps(failures, ensure_ascii=False))
    print("CURRENT_REAL_TENDER_INGESTION_VERIFIED_BY_THIS_STEP=NO")
    print("REAL_TELEGRAM_BOT_API_ACK_VERIFIED_BY_THIS_STEP=NO")
    print("DOMAIN_TLS_AND_PAYMENT_READINESS_VERIFIED_BY_THIS_STEP=NO")
    print("PRODUCTION_CHANGED=NO")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
