"""Fail-closed freshness/quality gate before routing public guest traffic.

This is a *supplementary* operator check on a dedicated source database.
It NEVER treats locally inserted fixtures or a green offline test as actual
first-party live proof. The real Worker receipt and official URLs must also
be checked by the operator from the current deployed commit.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from app.api.guest_search_routes import _public_preview
from app.api.isolated_public_sources import ISOLATED_SQLITE_URL
from app.database.config import load_database_settings

SOURCE = "mikroton_tender"
OFFICIAL_HOST = "tender.mt52.ru"
MAX_OBSERVATION_AGE_HOURS = 2


def eligible_public_previews(database, *, now: datetime | None = None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("UTC-aware verification time required")
    now = now.astimezone(timezone.utc)
    with closing(database.connect()) as conn:
        rows = conn.execute(
            "SELECT source_id, external_id, notice_json, last_seen "
            "FROM source_opportunities WHERE source_id=? "
            "ORDER BY last_seen DESC LIMIT 100",
            (SOURCE,),
        ).fetchall()
    fresh_ids = set()
    visible = 0
    for row in rows:
        try:
            observed = datetime.fromisoformat(str(row["last_seen"]).replace("Z", "+00:00"))
            if observed.tzinfo is None:
                continue
            age_seconds = (now - observed.astimezone(timezone.utc)).total_seconds()
            if age_seconds < 0 or age_seconds > MAX_OBSERVATION_AGE_HOURS * 3600:
                continue
            notice = json.loads(row["notice_json"])
            if not isinstance(notice, dict) or notice.get("source") != SOURCE:
                continue
            external_id = str(row["external_id"])
            if not external_id.isdecimal() or notice.get("external_id") != external_id:
                continue
            url = urlsplit(notice.get("url") or "")
            if (url.scheme != "https" or url.netloc != OFFICIAL_HOST or
                    url.path != f"/tenders/{external_id}" or url.query or url.fragment):
                continue
            deadline = datetime.fromisoformat(
                str(notice.get("deadline") or "").replace("Z", "+00:00")
            )
            if deadline.tzinfo is None or deadline.astimezone(timezone.utc) <= now:
                # Archive is real, but not a currently actionable procurement.
                continue
            preview = _public_preview(notice)
            if not preview or not preview["title"]:
                continue
        except (TypeError, ValueError, AttributeError):
            continue
        if external_id in fresh_ids:
            continue
        fresh_ids.add(external_id)
        visible += 1
    return {"fresh_open_originals":visible,
            "archived_or_unverified_excluded":max(0,len(rows)-visible),
            "promotion_ready":visible > 0}


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
    print("PUBLIC_SOURCE_PROMOTION="+("CANDIDATE_ONLY" if result["promotion_ready"] else "BLOCKED_NO_FRESH_ORIGINALS"))
    print("OFFICIAL_LIVE_ORIGIN_AND_WORKER_RECEIPT=REQUIRES_INDEPENDENT_CONFIRMATION")
    print("PRODUCTION_CHANGED=NO")
    return 0 if result["promotion_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
