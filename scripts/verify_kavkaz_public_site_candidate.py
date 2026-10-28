"""Candidate gate for real, currently open Kavkaz.RF corporate procurement.

This checks the isolated SQLite state only. A GREEN candidate is NOT proof
that the official publisher was reached: the separate genuine original ->
leased Worker -> disposable SQL test and VPS-side receipt must pass too.

Never assume an end-of-day UTC time for a first-party date-only deadline.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

from app.api.guest_search_routes import _public_preview
from app.api.public_source_deadline import eligible_published_deadline
from app.api.isolated_public_sources import ISOLATED_SQLITE_URL
from app.sources.kavkaz_rf_firstparty import (
    SOURCE_ID, NATIVE_NUMBER, _canonical,
)

MAX_AGE_SECONDS = 7200


def verify_kavkaz_candidate(db, *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Timezone-aware UTC verification required")
    now = now.astimezone(timezone.utc)
    with closing(db.connect()) as conn:
        rows = conn.execute(
            "SELECT source_id,external_id,notice_json,last_seen "
            "FROM source_opportunities WHERE source_id=? "
            "ORDER BY last_seen DESC LIMIT 30", (SOURCE_ID,),
        ).fetchall()
    known = set()
    for row in rows:
        try:
            observed = datetime.fromisoformat(
                str(row["last_seen"]).replace("Z", "+00:00"))
            if observed.tzinfo is None:
                continue
            lag = (now - observed.astimezone(timezone.utc)).total_seconds()
            if not 0 <= lag <= MAX_AGE_SECONDS:
                continue
            notice = json.loads(row["notice_json"])
            identity = row["external_id"]
            if (not isinstance(notice, dict) or
                    notice.get("source") != SOURCE_ID or
                    type(identity) is not str or
                    NATIVE_NUMBER.fullmatch(identity) is None or
                    notice.get("external_id") != identity or
                    notice.get("tender_number") != identity or
                    notice.get("customer") != "АО «КАВКАЗ.РФ»" or
                    notice.get("region") != "Северный Кавказ"):
                continue
            raw_url = notice.get("url")
            if type(raw_url) is not str or _canonical(raw_url) != raw_url:
                continue
            if not eligible_published_deadline(
                    SOURCE_ID, notice.get("deadline"), now=now):
                continue
            price = notice.get("initial_price")
            if (type(price) not in (float, int) or price <= 0 or
                    notice.get("currency") != "RUB" or
                    not isinstance(notice.get("published_at"), str) or
                    _public_preview(notice) is None):
                continue
            known.add(identity)
        except (ValueError, TypeError, AttributeError, OverflowError):
            continue
    return {
        "source": SOURCE_ID,
        "fresh_canonical_open_originals": len(known),
        "rows_inspected": len(rows),
        "candidate_ready": bool(known),
        "independent_eis_dedup_proved": False,
    }


def main() -> int:
    if (os.environ.get("VALYQON_ISOLATED_PUBLIC_SOURCES_ENABLED") != "true"
            or os.environ.get("DATABASE_URL") != ISOLATED_SQLITE_URL
            or os.environ.get("KAVKAZ_RF_FIRSTPARTY_ENABLED") != "true"
            or os.environ.get("SOUTH_URAL_PUBLIC_ENABLED") != "true"):
        print("KAVKAZ_PUBLIC_PROMOTION=BLOCKED_CONFIG")
        return 2
    from app.database.backend import Database
    from app.database.config import load_database_settings
    db = Database(load_database_settings())
    try:
        result = verify_kavkaz_candidate(db)
    except (sqlite3.Error, ValueError, OSError):
        print("KAVKAZ_PUBLIC_PROMOTION=BLOCKED_STORE")
        return 2
    finally:
        db.close()
    print("KAVKAZ_FRESH_CANONICAL_OPEN=" + str(result["fresh_canonical_open_originals"]))
    print("KAVKAZ_PUBLIC_PROMOTION=" + (
        "CANDIDATE_ONLY" if result["candidate_ready"] else "BLOCKED_NO_ACTIVE_ORIGINALS"))
    print("REAL_UPSTREAM_WORKER_RECEIPT=REQUIRES_INDEPENDENT_LIVE_VERIFICATION")
    print("EIS_CROSSPOST_DEDUP_NOT_PROVED=YES")
    print("PRODUCTION_CHANGED=NO")
    return 0 if result["candidate_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
