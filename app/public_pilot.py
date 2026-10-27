"""Marketing-only public pilot startup for hosted single-container previews.

This intentionally does not activate account signup, payment, source workers,
SMTP or LLM. It is not an authorized customer-facing SaaS launch.
"""
from __future__ import annotations

import os
import sys


PUBLIC_PILOT_BLOCKED_FLAGS = {
    "APP_ENV": "production",
    "VALYQON_LEGAL_REQUIRED": "true",
    "VALYQON_LEGAL_APPROVED": "false",
    "VALYQON_PUBLIC_MARKETING_ONLY": "true",
    "VALYQON_EMAIL_MODE": "disabled",
    "VALYQON_PUBLIC_ANALYTICS_MODE": "real",
    "VALYQON_RESTRICT_PAID_SOURCE_DETAILS": "true",
    "VALYQON_PUBLIC_AI_ENABLED": "false",
    "MONITORING_ENABLED": "false",
    "VALYQON_RU_BACKGROUND_CATALOG_ENABLED": "false",
    "VALYQON_DEADLINE_ALERTS_ENABLED": "false",
    "GPB_ETP_PUBLIC_ENABLED": "false",
    "ROSELTORG_PUBLIC_ENABLED": "false",
    "TEKTORG_PUBLIC_ENABLED": "false",
    "B2B_CENTER_ENABLED": "false",
    "EIS_44_HTML_ENABLED": "false",
    "EIS_223_ENABLED": "false",
}


def main() -> int:
    # A pilot release cannot be elevated by externally inherited environment
    # switches. Full operator/onboarding rollout is a separately reviewed step.
    os.environ.update(PUBLIC_PILOT_BLOCKED_FLAGS)
    os.environ["API_HOST"] = "0.0.0.0"
    os.environ["API_RELOAD"] = "false"
    public_port = os.environ.get("PORT", "8000")
    try:
        if str(int(public_port)) != public_port or not 1 <= int(public_port) <= 65535:
            raise ValueError("Invalid port.")
    except (ValueError, OverflowError):
        print("PUBLIC_PILOT_PORT_INVALID", file=sys.stderr)
        return 2
    os.environ["API_PORT"] = public_port

    from app.api.__main__ import main as serve_api
    return serve_api()


if __name__ == "__main__":
    raise SystemExit(main())
