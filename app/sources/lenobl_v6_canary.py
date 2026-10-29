"""Lenobl V6 first-party HTTPS canary from the EXISTING isolated Worker network.

Manually run inside the approved isolated six-source Worker container:
    python -m app.sources.lenobl_v6_canary

One bounded first-party listing GET and at most three detail GETs. No queue,
SQL, user, Telegram or email I/O. This is not a Worker/SQL or HTTPS release gate.
Only aggregate counts and safe exception classes are emitted.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime, timezone

from app.api.public_source_deadline import eligible_published_deadline
from app.sources.http import FetchPolicy, bounded_fetch
from app.sources.isolated_runtime_audit import isolated_environment_valid
from app.sources.lenobl_small_public import HOST, SOURCE_ID, LenoblSmallPublicSource
from app.sources.opportunities import validate_notice

MAX_REQUESTS = 4
MAX_RECORDS = 30


def safe_environment(env):
    return (
        isolated_environment_valid(env)
        and env.get("LENOBL_SMALL_PUBLIC_ENABLED") == "true"
        and env.get("VALYQON_CONNECTOR_MAX_RECORDS") == str(MAX_RECORDS)
        and env.get("OUTBOUND_PROXY_URL", "") == ""
        and env.get("VALYQON_RU_BACKGROUND_CATALOG_ENABLED") == "false"
    )


def _failure_label(error):
    """Only the Python exception class and a bounded transport category.

    Never print exception str(), traceback, source URL, titles or buyer data.
    """
    label = type(error).__name__
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", label) is None:
        label = "UnknownException"
    reason = getattr(error, "reason", None)
    if reason not in ("network", "timeout", "policy", "tls", "dns",
                      "http_status", "size", "redirect"):
        reason = "none"
    return label, reason


async def probe_source(*, source=None, now=None):
    """Read-only actual first-party calls using the same four-request cap as V6."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Aware clock required")
    policy = FetchPolicy(frozenset({HOST}), max_requests=MAX_REQUESTS)
    base = {
        "source": SOURCE_ID,
        "max_http_gets": MAX_REQUESTS,
        "verified_originals": 0,
        "safely_open_originals": 0,
        "exception_class": "none",
        "transport_reason": "none",
        "worker_sql_receipt_proved": False,
        "public_https_delivery_proved": False,
        "telegram_send_authorized": False,
        "production_changed": False,
    }
    try:
        with bounded_fetch(policy):
            notices = await asyncio.wait_for(
                (source or LenoblSmallPublicSource()).fetch(MAX_RECORDS),
                timeout=125,
            )
        if (type(notices) is not list or not 1 <= len(notices) <= 3
                or policy.requests < 2 or policy.requests > MAX_REQUESTS):
            raise ValueError("Unverified canary result")
        for notice in notices:
            if notice.source != SOURCE_ID:
                raise ValueError("Unexpected canary source")
            validate_notice(notice, SOURCE_ID)
        base["verified_originals"] = len(notices)
        base["safely_open_originals"] = sum(
            bool(eligible_published_deadline(SOURCE_ID, item.deadline, now=now))
            for item in notices
        )
        base["status"] = ("SOURCE_GET_CANDIDATE_ONLY"
                          if base["safely_open_originals"] > 0
                          else "BLOCKED_NO_CURRENT_ORIGINAL")
    except Exception as error:
        base["exception_class"], base["transport_reason"] = _failure_label(error)
        base["status"] = "BLOCKED_FIRSTPARTY_SOURCE"
    base["observed_http_gets"] = policy.requests
    return base


def main(environ=None):
    env = os.environ if environ is None else environ
    if not safe_environment(env):
        print("LENOBL_V6_SAME_NETWORK_CANARY=BLOCKED_UNSAFE_ENV")
        print("PRODUCTION_CHANGED=NO")
        return 2
    data = asyncio.run(probe_source())
    print("LENOBL_V6_CANARY_STATUS=" + data["status"])
    print("LENOBL_V6_CANARY_AGGREGATE=" + json.dumps(
        data, sort_keys=True, separators=(",", ":")))
    print("PRODUCTION_CHANGED=NO")
    return 0 if data["status"] == "SOURCE_GET_CANDIDATE_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
