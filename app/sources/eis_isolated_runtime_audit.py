"""Operator-only EIS 44/223 read-only isolated Worker -> SQLite release evidence.

This audit reports fixed aggregates, never notice text, customer data or URLs.
A fresh successful Worker receipt and recent eligible SQL records are necessary
but INSUFFICIENT for verified public activation: independent upstream-origin
observation and public HTTPS/Caddy routing remain separate release gates.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

from app.api.isolated_public_sources import ISOLATED_SQLITE_URL
from app.api.public_eis_identity import accepted_eis_original
from app.api.public_source_deadline import eligible_published_deadline
from app.api.guest_search_routes import _public_preview
from .isolated_runtime_audit import (
    MAX_AGE_SECONDS, _job_age_minutes, _recent, isolated_environment_valid,
)
from .eis_rss import SourceError, validate_eis_direct_urls
from .eis_223_rss import _validate_feed_url

SOURCES = ("eis", "eis_223")
MAX_ROWS = 200
MAX_JOBS = 500


def _official_feed_configuration(env):
    if (not isolated_environment_valid(env)
            or env.get("EIS_RSS_PUBLIC_ENABLED") != "true"
            or env.get("EIS_223_PUBLIC_ENABLED") != "true"
            or env.get("EIS_223_ENABLED") != "true"
            or env.get("EIS_DIRECT_ENABLED") != "true"
            or env.get("EIS_PROFILE_FEEDS_ENABLED") != "false"
            or env.get("EIS_223_PROFILE_FEEDS_ENABLED") != "false"):
        raise ValueError("Invalid isolated EIS source environment")
    for name, flag in (
        ("eis", "EIS_RSS_URLS"), ("eis_223", "EIS_223_RSS_URLS")
    ):
        urls = tuple(v.strip() for v in env.get(flag, "").split(";") if v.strip())
        if not urls or len(urls) > 5:
            raise ValueError("Official EIS feed missing or exceeds bound")
        try:
            validate_eis_direct_urls(urls)
        except SourceError:
            raise ValueError("Invalid official EIS static feed") from None
        for url in urls:
            query = parse_qs(urlsplit(url).query, keep_blank_values=True)
            wanted = "fz44" if name == "eis" else "fz223"
            other = "fz223" if name == "eis" else "fz44"
            if query.get(wanted) != ["on"] or other in query:
                raise ValueError("EIS official law filter mismatch")
            if name == "eis_223":
                _validate_feed_url(url)


def audit(conn, *, environment, now=None):
    now = now or datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("Audit requires UTC-aware timestamp")
    now = now.astimezone(timezone.utc)
    _official_feed_configuration(environment)
    data = {}
    for source in SOURCES:
        rows = conn.execute(
            "SELECT external_id,notice_json,last_seen FROM source_opportunities "
            "WHERE source_id=? ORDER BY last_seen DESC LIMIT ?",
            (source, MAX_ROWS)).fetchall()
        recent = eligible = 0
        for external_id, payload, seen in rows:
            if not _recent(seen, now):
                continue
            recent += 1
            try:
                notice = json.loads(payload)
                if (not isinstance(notice, dict)
                        or notice.get("source") != source
                        or notice.get("external_id") != external_id
                        or not accepted_eis_original(notice)
                        or not eligible_published_deadline(
                            source, notice.get("deadline"), now=now)
                        or _public_preview(notice) is None):
                    continue
                eligible += 1
            except (ValueError, TypeError, OverflowError):
                continue
        data[source] = {
            "recent_stored_originals": recent,
            "recent_canonical_open_previews": eligible,
            "last_worker_job": "not_found",
            "last_worker_accepted_count": None,
            "last_worker_age_minutes": None,
            "local_ready": False,
        }

    jobs = conn.execute(
        "SELECT payload_json,state,finished_at,result_json FROM durable_jobs "
        "WHERE job_type='connector.sync.v1' ORDER BY created_at DESC LIMIT ?",
        (MAX_JOBS,)).fetchall()
    found = set()
    for raw, state, finished, result in jobs:
        try:
            payload = json.loads(raw)
            source = payload.get("source_id") if isinstance(payload, dict) else None
            if source not in data or source in found:
                continue
            found.add(source)
            encoded_result = json.loads(result) if result else None
            accepted = (encoded_result.get("accepted_count")
                        if isinstance(encoded_result, dict) else None)
            if type(accepted) is not int or accepted < 0:
                accepted = None
            age = _job_age_minutes(finished, now)
            row = data[source]
            row.update(
                last_worker_job=state if state in {"queued","running","succeeded","failed","cancelled"} else "unknown",
                last_worker_accepted_count=accepted,
                last_worker_age_minutes=age,
            )
            row["local_ready"] = (
                state == "succeeded" and age is not None
                and age <= MAX_AGE_SECONDS / 60
                and accepted is not None and accepted > 0
                and row["recent_canonical_open_previews"] > 0
            )
        except (ValueError, TypeError, OverflowError):
            continue
    ready = all(data[k]["local_ready"] for k in SOURCES)
    return {
        "scope": "isolated_eis_44_223_sql_worker_readonly",
        "sources": data,
        "local_candidate_ready": ready,
        "publisher_live_origin_proved": False,
        "public_https_caddy_routing_proved": False,
        "production_modified": False,
    }


def audit_path(path, *, environment, now=None):
    uri = "file:" + quote(str(Path(path).resolve()), safe="/") + "?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=5) as conn:
        conn.execute("PRAGMA query_only=ON")
        return audit(conn, environment=environment, now=now)


def main() -> int:
    try:
        data = audit_path("/app/data/isolated-public-sources.sqlite3",
                          environment=os.environ)
    except (sqlite3.Error, ValueError, OSError):
        print("EIS_ISOLATED_SQL_WORKER_AUDIT=BLOCKED")
        print("PRODUCTION_MODIFIED=NO")
        return 2
    print("EIS_ISOLATED_SQL_WORKER_AUDIT=" +
          ("CANDIDATE_ONLY" if data["local_candidate_ready"]
           else "BLOCKED_NO_REAL_SQL_WORKER_PROOF"))
    print("EIS_ISOLATED_AGGREGATES=" +
          json.dumps(data, sort_keys=True, separators=(",", ":")))
    print("UPSTREAM_AND_PUBLIC_HTTPS=INDEPENDENT_PROOF_REQUIRED")
    print("PRODUCTION_MODIFIED=NO")
    return 0 if data["local_candidate_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
