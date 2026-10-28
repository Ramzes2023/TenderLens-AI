"""Isolated-database, no-production gate for Lenobl source originals.

An operator MUST combine this SQL snapshot with independently verified
official HTML originals and a real fenced Worker receipt. SQL may contain
fixtures and cannot independently verify upstream integrity. Only a future
publisher calendar date (never a guessed time zone) can qualify.
"""
from __future__ import annotations

import json
import os
from contextlib import closing
from datetime import datetime, timezone

from app.api.isolated_public_sources import ISOLATED_SQLITE_URL
from app.api.public_source_deadline import eligible_published_deadline
from app.api.guest_search_routes import _public_preview
from app.sources.lenobl_small_public import SOURCE_ID, _canonical


def verify_lenobl_candidate(db, *, now: datetime | None = None):
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Timezone-aware snapshot verification required")
    now=now.astimezone(timezone.utc)
    with closing(db.connect()) as conn:
        rows=conn.execute(
            "SELECT source_id,external_id,notice_json,last_seen "
            "FROM source_opportunities WHERE source_id=? "
            "ORDER BY last_seen DESC LIMIT 100", (SOURCE_ID,),
        ).fetchall()
    current=set()
    for row in rows:
        try:
            observed=datetime.fromisoformat(
                str(row["last_seen"]).replace("Z","+00:00"))
            if observed.tzinfo is None:
                continue
            age=(now-observed.astimezone(timezone.utc)).total_seconds()
            if not 0 <= age <= 7200:
                continue
            notice=json.loads(row["notice_json"])
            identity=row["external_id"]
            if type(identity) is not str or not isinstance(notice,dict):
                continue
            url=notice.get("url")
            if (notice.get("source")!=SOURCE_ID
                or notice.get("external_id")!=identity
                or type(url) is not str
                or _canonical(url)!=(identity,url)
                or notice.get("initial_price") is not None
                or notice.get("currency") is not None
                or notice.get("tender_number") is not None):
                continue
            if not eligible_published_deadline(
                    SOURCE_ID,notice.get("deadline"),now=now):
                continue
            if _public_preview(notice) is None:
                continue
            current.add(identity)
        except (ValueError,TypeError,AttributeError,OverflowError):
            continue
    return {"source":SOURCE_ID,"rows_inspected":len(rows),
            "recent_open_official_rows":len(current),
            "candidate_ready":bool(current)}


def main() -> int:
    if (os.environ.get("VALYQON_ISOLATED_PUBLIC_SOURCES_ENABLED")!="true"
        or os.environ.get("DATABASE_URL")!=ISOLATED_SQLITE_URL
        or os.environ.get("LENOBL_SMALL_PUBLIC_ENABLED")!="true"
        or os.environ.get("KAVKAZ_RF_FIRSTPARTY_ENABLED")!="true"
        or os.environ.get("SOUTH_URAL_PUBLIC_ENABLED")!="true"):
        print("LENOBL_PUBLIC_PROMOTION=BLOCKED_CONFIG")
        return 2
    from app.database.backend import Database
    from app.database.config import load_database_settings
    db=Database(load_database_settings())
    try:
        evidence=verify_lenobl_candidate(db)
    finally:
        db.close()
    print("LENOBL_OPEN_SQL_CANDIDATES="+str(evidence["recent_open_official_rows"]))
    print("LENOBL_PUBLIC_PROMOTION="+(
        "CANDIDATE_ONLY" if evidence["candidate_ready"] else "BLOCKED_NO_CURRENT_ORIGINALS"))
    print("OFFICIAL_ORIGIN_AND_FENCED_WORKER=REQUIRES_SEPARATE_LIVE_PROOF")
    print("PRODUCTION_CHANGED=NO")
    return 0 if evidence["candidate_ready"] else 2


if __name__=="__main__":
    raise SystemExit(main())
