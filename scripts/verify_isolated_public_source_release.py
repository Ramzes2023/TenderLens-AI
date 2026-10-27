"""Fail-closed active original gate before a public source route cutover.

This verifies a recent SQL state, not actual upstream network acquisition.
It must be combined with independently confirmed same-commit genuine Worker
receipts and source originals. Archived, expired, unknown-deadline or
non-canonical procedures are never counted as active opportunities.
"""
from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from urllib.parse import urlsplit

from app.api.guest_search_routes import _public_preview
from app.api.isolated_public_sources import ISOLATED_SQLITE_URL
from app.database.config import load_database_settings

SOURCES = ("mikroton_tender", "stan_commercial_public")
STAN_NUMBER = re.compile(r"[А-ЯA-Z]{1,4}-20\d{2}-\d{6}")
STAN_PATH = re.compile(r"/etp/[A-Za-z0-9]{8}")
MAX_OBSERVATION_AGE_HOURS = 2


def official_identity(source: str, external_id: str, raw_url: str) -> bool:
    if not isinstance(raw_url, str) or not isinstance(external_id, str):
        return False
    try:
        url = urlsplit(raw_url)
        if (url.scheme != "https" or url.username or url.password or
                url.query or url.fragment or url.port is not None):
            return False
        if source == "mikroton_tender":
            return (url.netloc == "tender.mt52.ru" and
                    external_id.isdecimal() and
                    url.path == "/tenders/" + external_id)
        if source == "stan_commercial_public":
            return (url.netloc == "stantorgi.ru" and
                    STAN_NUMBER.fullmatch(external_id) is not None and
                    STAN_PATH.fullmatch(url.path) is not None)
    except ValueError:
        return False
    return False


def eligible_public_previews(database, *, now: datetime | None = None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("UTC-aware verification time required")
    now = now.astimezone(timezone.utc)
    with closing(database.connect()) as conn:
        rows = conn.execute(
            "SELECT source_id, external_id, notice_json, last_seen "
            "FROM source_opportunities WHERE source_id IN (?,?) "
            "ORDER BY last_seen DESC LIMIT 200",
            SOURCES,
        ).fetchall()

    seen = set()
    counts = {source: 0 for source in SOURCES}
    for row in rows:
        try:
            source = row["source_id"]
            if source not in counts:
                continue
            observed = datetime.fromisoformat(
                str(row["last_seen"]).replace("Z", "+00:00"))
            if observed.tzinfo is None:
                continue
            age = (now - observed.astimezone(timezone.utc)).total_seconds()
            if age < 0 or age > MAX_OBSERVATION_AGE_HOURS * 3600:
                continue
            notice = json.loads(row["notice_json"])
            if not isinstance(notice, dict) or notice.get("source") != source:
                continue
            external_id = row["external_id"]
            if (type(external_id) is not str or
                    notice.get("external_id") != external_id or
                    not official_identity(source, external_id, notice.get("url"))):
                continue
            deadline = datetime.fromisoformat(
                str(notice.get("deadline") or "").replace("Z", "+00:00"))
            if deadline.tzinfo is None or deadline.astimezone(timezone.utc) <= now:
                continue
            public = _public_preview(notice)
            if not public or not public["title"]:
                continue
        except (ValueError, TypeError, AttributeError):
            continue
        identity = (source, external_id)
        if identity in seen:
            continue
        seen.add(identity)
        counts[source] += 1

    total = sum(counts.values())
    return {
        "fresh_open_originals": total,
        "by_source": counts,
        "archived_or_unverified_excluded": max(0, len(rows) - total),
        "promotion_ready": total > 0,
    }


def main():
    import os
    from app.database.backend import Database
    if (os.environ.get("VALYQON_ISOLATED_PUBLIC_SOURCES_ENABLED") != "true" or
            os.environ.get("DATABASE_URL") != ISOLATED_SQLITE_URL):
        print("PUBLIC_SOURCE_PROMOTION=BLOCKED_CONFIG")
        return 2
    database = Database(load_database_settings())
    try:
        result = eligible_public_previews(database)
    except (sqlite3.Error, ValueError, OSError):
        print("PUBLIC_SOURCE_PROMOTION=BLOCKED_STORE")
        return 2
    finally:
        database.close()
    print("PUBLIC_SOURCE_FRESH_OPEN_COUNT="+str(result["fresh_open_originals"]))
    for source, count in result["by_source"].items():
        print("PUBLIC_SOURCE_FRESH_"+source.upper()+"="+str(count))
    print("PUBLIC_SOURCE_PROMOTION="+(
        "CANDIDATE_ONLY" if result["promotion_ready"] else "BLOCKED_NO_FRESH_ORIGINALS"))
    print("OFFICIAL_LIVE_ORIGIN_AND_WORKER_RECEIPT=REQUIRES_INDEPENDENT_CONFIRMATION")
    print("PRODUCTION_CHANGED=NO")
    return 0 if result["promotion_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
