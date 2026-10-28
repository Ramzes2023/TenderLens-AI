"""Operator-only live-release gate for current original South Ural tenders.

The source has previously passed independent original→fenced Worker→SQL gates.
This extra gate rejects archived, stale, malformed, non-original or undated
procurements in the separate isolated-source SQLite volume. It does not
fake an original-host HTTP acceptance, create accounts, or touch production.
"""
from __future__ import annotations

import json
import os
import re
from contextlib import closing
from datetime import datetime, timezone
from urllib.parse import urlsplit, parse_qs

from app.api.guest_search_routes import _public_preview
from app.api.isolated_public_sources import ISOLATED_SQLITE_URL
from app.database.backend import Database
from app.database.config import load_database_settings

SOURCE = "south_ural_public"
HOST = "www.vendorportal.ru"
DETAIL = re.compile(r"/Market/OfferInvitationOpen/View/([0-9]{5,8})")
MAX_AGE_SECONDS = 7200


def canonical_original(identifier: str, url: str) -> bool:
    if type(identifier) is not str or not identifier.isdecimal() or type(url) is not str:
        return False
    try:
        parsed = urlsplit(url)
        match = DETAIL.fullmatch(parsed.path)
        return bool(
            parsed.scheme == "https"
            and parsed.netloc == HOST
            and parsed.username is None and parsed.password is None
            and parsed.fragment == ""
            and match and match.group(1) == identifier
            and parsed.query == "isReadOnly=True"
        )
    except ValueError:
        return False


def verify(db, *, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Verification requires timezone-aware UTC datetime.")
    now = now.astimezone(timezone.utc)
    with closing(db.connect()) as conn:
        rows = conn.execute(
            "SELECT external_id,notice_json,last_seen FROM source_opportunities "
            "WHERE source_id=? ORDER BY last_seen DESC LIMIT 100", (SOURCE,),
        ).fetchall()
    current = set()
    for row in rows:
        try:
            record = json.loads(row["notice_json"])
            observed = datetime.fromisoformat(str(row["last_seen"]).replace("Z", "+00:00"))
            deadline = datetime.fromisoformat(str(record.get("deadline") or "").replace("Z", "+00:00"))
            if observed.tzinfo is None or deadline.tzinfo is None:
                continue
            age = (now - observed.astimezone(timezone.utc)).total_seconds()
            if age < 0 or age > MAX_AGE_SECONDS or deadline.astimezone(timezone.utc) <= now:
                continue
            identity = row["external_id"]
            if (record.get("source") != SOURCE
                or record.get("external_id") != identity
                or not canonical_original(identity, record.get("url"))
                or record.get("region") != "Челябинская область"
                or _public_preview(record) is None):
                continue
            current.add(identity)
        except (ValueError, TypeError, AttributeError):
            continue
    return {"source":SOURCE, "verified_recent_open_originals":len(current),
            "stored_source_rows_scanned":len(rows),
            "candidate_ready":len(current)>0}


def main():
    if (os.environ.get("VALYQON_ISOLATED_PUBLIC_SOURCES_ENABLED") != "true"
        or os.environ.get("DATABASE_URL") != ISOLATED_SQLITE_URL
        or os.environ.get("SOUTH_URAL_PUBLIC_ENABLED") != "true"):
        print("SOUTH_URAL_PUBLIC_CANDIDATE=BLOCKED_CONFIG")
        return 2
    db = Database(load_database_settings())
    try:
        result = verify(db)
    finally:
        db.close()
    print("SOUTH_URAL_RECENT_OPEN_ORIGINALS="+str(result["verified_recent_open_originals"]))
    print("SOUTH_URAL_PUBLIC_CANDIDATE="+(
        "SQL_READY_REQUIRES_INDEPENDENT_LIVE_WORKER_PROOF"
        if result["candidate_ready"] else "BLOCKED_NO_CURRENT_ORIGINALS"))
    print("PRODUCTION_CHANGED=NO")
    return 0 if result["candidate_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
