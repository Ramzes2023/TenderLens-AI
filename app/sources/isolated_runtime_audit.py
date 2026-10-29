"""Read-only, per-source visibility for the isolated public tender Worker.

Run *inside the already deployed isolated guest-sources container*:
    python -m app.sources.isolated_runtime_audit

No network calls, no migrations, no account records, no source payload printing,
and no writes. A real Worker success is shown separately from a recent public
preview; neither is an independently verified live publisher response.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from app.api.public_source_deadline import eligible_published_deadline
from app.api.guest_search_routes import _public_preview
from app.api.isolated_public_sources import ISOLATED_SQLITE_URL

SOURCE_FLAGS = (
    ("mikroton_tender", "MIKROTON_TENDER_ENABLED"),
    ("stan_commercial_public", "STAN_COMMERCIAL_PUBLIC_ENABLED"),
    ("south_ural_public", "SOUTH_URAL_PUBLIC_ENABLED"),
    ("kavkaz_rf_firstparty", "KAVKAZ_RF_FIRSTPARTY_ENABLED"),
    ("lenobl_small_public", "LENOBL_SMALL_PUBLIC_ENABLED"),
    ("ru_samara_public_list", "RU_SAMARA_PUBLIC_LIST_ENABLED"),
)
MAX_AGE_SECONDS = 7200
MAX_SOURCE_ROWS = 200
MAX_JOBS = 600


def isolated_environment_valid(environment):
    return (
        environment.get("DATABASE_URL") == ISOLATED_SQLITE_URL
        and environment.get("VALYQON_ISOLATED_PUBLIC_SOURCES_ENABLED") == "true"
        and environment.get("MONITORING_ENABLED") == "false"
        and environment.get("TELEGRAM_BOT_TOKEN", "") == ""
        and environment.get("VALYQON_EMAIL_MODE") == "disabled"
        and environment.get("VALYQON_RESTRICT_PAID_SOURCE_DETAILS") == "true"
    )


def _timestamp(raw):
    if not isinstance(raw, str):
        return None
    try:
        result = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, OverflowError):
        return None
    return result.astimezone(timezone.utc) if result.tzinfo else None


def _recent(raw, now):
    stamp = _timestamp(raw)
    return stamp is not None and 0 <= (now - stamp).total_seconds() <= MAX_AGE_SECONDS


def _job_age_minutes(raw, now):
    """durable_jobs.finished_at is BIGINT Unix microseconds, not ISO text.

    An absent, malformed or future finish time must never be presented as
    recent Worker evidence. Source observation clocks are ISO strings and
    deliberately continue through _recent instead.
    """
    if type(raw) is not int or not 0 < raw < 2**63:
        return None
    age_us = int(now.timestamp() * 1_000_000) - raw
    return round(age_us / 60_000_000, 1) if age_us >= 0 else None


def audit_connection(conn, *, environment, now=None):
    """Return only aggregate evidence, never raw titles, URLs, IDs or tenant data."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Timezone-aware clock required")
    now = now.astimezone(timezone.utc)
    if not isolated_environment_valid(environment):
        raise ValueError("Not the isolated public-source runtime")

    result = {}
    for source, flag in SOURCE_FLAGS:
        value = environment.get(flag, "false")
        if value not in {"true", "false"}:
            raise ValueError("Invalid source switch")
        recent = open_rows = 0
        rows = conn.execute(
            "SELECT notice_json,last_seen FROM source_opportunities "
            "WHERE source_id=? ORDER BY last_seen DESC LIMIT ?",
            (source, MAX_SOURCE_ROWS),
        ).fetchall()
        for raw, seen in rows:
            if not _recent(seen, now):
                continue
            recent += 1
            try:
                notice = json.loads(raw)
                if (not isinstance(notice, dict)
                        or notice.get("source") != source
                        or not eligible_published_deadline(source, notice.get("deadline"), now=now)
                        or _public_preview(notice) is None):
                    continue
                open_rows += 1
            except (ValueError, TypeError, OverflowError, AttributeError):
                continue
        result[source] = {
            "enabled_in_isolated_container": value == "true",
            "recent_stored_rows": recent,
            "recent_future_deadline_previews": open_rows,
            "last_worker_job": "not_found",
            "last_worker_age_minutes": None,
            "last_worker_accepted_count": None,
        }

    # The durable queue is shared by *only this isolated* container's private
    # source volume. Never query saved user/customer data.
    jobs = conn.execute(
        "SELECT payload_json,state,finished_at,result_json FROM durable_jobs "
        "WHERE job_type='connector.sync.v1' ORDER BY created_at DESC LIMIT ?",
        (MAX_JOBS,),
    ).fetchall()
    for raw, state, finished, raw_result in jobs:
        try:
            payload = json.loads(raw)
            source = payload.get("source_id") if isinstance(payload, dict) else None
            if source not in result or result[source]["last_worker_job"] != "not_found":
                continue
            if state not in {"queued", "running", "succeeded", "failed", "cancelled"}:
                state = "unknown"
            evidence = json.loads(raw_result) if raw_result else None
            accepted = evidence.get("accepted_count") if isinstance(evidence, dict) else None
            if type(accepted) is not int or accepted < 0:
                accepted = None
            age = _job_age_minutes(finished, now)
            result[source].update(
                last_worker_job=state,
                last_worker_age_minutes=age,
                last_worker_accepted_count=accepted,
            )
        except (ValueError, TypeError, OverflowError, AttributeError):
            continue

    return {
        "scope": "isolated_public_sources_readonly",
        "sources": result,
        "enabled_count": sum(x["enabled_in_isolated_container"] for x in result.values()),
        "stored_open_preview_count": sum(x["recent_future_deadline_previews"] for x in result.values()),
        "publisher_live_acceptance_proved_by_this_audit": False,
        "public_https_caddy_routing_proved_by_this_audit": False,
        "production_changed": False,
    }


def audit_path(path, *, environment, now=None):
    # Read-only URI fails if the file does not exist; never creates a fake DB.
    uri = "file:" + quote(str(Path(path).resolve()), safe="/") + "?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=5) as conn:
        conn.execute("PRAGMA query_only=ON")
        return audit_connection(conn, environment=environment, now=now)


def main():
    if not isolated_environment_valid(os.environ):
        print("ISOLATED_PUBLIC_SOURCE_AUDIT=BLOCKED_UNSAFE_ENV")
        return 2
    path = Path("/app/data/isolated-public-sources.sqlite3")
    try:
        data = audit_path(path, environment=os.environ)
    except (sqlite3.Error, OSError, ValueError):
        print("ISOLATED_PUBLIC_SOURCE_AUDIT=BLOCKED_STORAGE")
        return 2
    print("ISOLATED_PUBLIC_SOURCE_AUDIT=PASS_READONLY")
    print("ISOLATED_PUBLIC_SOURCE_STATUS=" + json.dumps(data, sort_keys=True, separators=(",", ":")))
    print("PRODUCTION_CHANGED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
