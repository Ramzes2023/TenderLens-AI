"""Read-only per-source inventory for the isolated VALYQON public feed.

Only run inside the reviewed isolated guest-sources container. This diagnostic
NEVER touches the production database, network, queues, operator secrets or
customer data. Saved-row presence is not proof of a live source Worker receipt.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone

EXPECTED_DB = "sqlite:////app/data/isolated-public-sources.sqlite3"
SOURCE_FLAGS = (
    ("mikroton_tender", "MIKROTON_TENDER_ENABLED"),
    ("stan_commercial_public", "STAN_COMMERCIAL_PUBLIC_ENABLED"),
    ("south_ural_public", "SOUTH_URAL_PUBLIC_ENABLED"),
    ("kavkaz_rf_firstparty", "KAVKAZ_RF_FIRSTPARTY_ENABLED"),
    ("lenobl_small_public", "LENOBL_SMALL_PUBLIC_ENABLED"),
    ("ru_samara_public_list", "RU_SAMARA_PUBLIC_LIST_ENABLED"),
)
MAX_PER_SOURCE = 1000


def inventory(conn, flags, *, now=None):
    from app.api.guest_search_routes import _public_preview
    from app.api.public_source_deadline import eligible_published_deadline

    now = now or datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("UTC-aware inventory clock required")
    now = now.astimezone(timezone.utc)
    recent_after = now - timedelta(hours=2)
    result = []
    for key, flag in SOURCE_FLAGS:
        setting = flags.get(flag)
        if setting not in {"true", "false"}:
            raise ValueError("Missing or invalid isolated source approval flag: " + flag)
        rows = conn.execute(
            "SELECT notice_json,last_seen FROM source_opportunities "
            "WHERE source_id=? ORDER BY last_seen DESC LIMIT ?", (key, MAX_PER_SOURCE)
        ).fetchall()
        recent = 0
        current = 0
        for raw, seen in rows:
            try:
                timestamp = datetime.fromisoformat(str(seen).replace("Z", "+00:00"))
                if timestamp.tzinfo is None:
                    continue
                timestamp = timestamp.astimezone(timezone.utc)
                if not recent_after <= timestamp <= now:
                    continue
                recent += 1
                notice = json.loads(raw)
                if (not isinstance(notice, dict) or notice.get("source") != key
                        or not eligible_published_deadline(
                            key, notice.get("deadline"), now=now)
                        or _public_preview(notice) is None):
                    continue
                current += 1
            except (ValueError, TypeError, OverflowError, AttributeError):
                continue
        result.append({
            "key": key,
            "config_enabled": setting == "true",
            "sampled_stored_rows": len(rows),
            "recent_2h_rows": recent,
            "recent_2h_unexpired_previews": current,
        })
    return result


def main() -> int:
    if (os.environ.get("VALYQON_ISOLATED_PUBLIC_SOURCES_ENABLED") != "true"
            or os.environ.get("DATABASE_URL") != EXPECTED_DB):
        print("ISOLATED_PUBLIC_INVENTORY=BLOCKED_WRONG_CONTAINER")
        return 2
    dbpath = "/app/data/isolated-public-sources.sqlite3"
    # Read-only URI does not create a missing database and never opens write mode.
    try:
        with sqlite3.connect("file:" + dbpath + "?mode=ro", uri=True, timeout=5.0) as conn:
            conn.execute("PRAGMA query_only=ON")
            stats = inventory(conn, os.environ)
    except (sqlite3.Error, ValueError, OSError):
        print("ISOLATED_PUBLIC_INVENTORY=BLOCKED_STORE_OR_FLAGS")
        return 2
    for item in stats:
        label = item["key"].upper()
        print("SOURCE_" + label + "_CONFIG=" + ("ON" if item["config_enabled"] else "OFF"))
        print("SOURCE_" + label + "_SAMPLED_ROWS=" + str(item["sampled_stored_rows"]))
        print("SOURCE_" + label + "_RECENT_2H_ROWS=" + str(item["recent_2h_rows"]))
        print("SOURCE_" + label + "_RECENT_2H_OPEN_PREVIEWS=" + str(item["recent_2h_unexpired_previews"]))
    print("ISOLATED_PUBLIC_INVENTORY=READ_ONLY_COMPLETE")
    print("PROVENANCE_AND_WORKER_RECEIPTS=NOT_VERIFIED_BY_THIS_AUDIT")
    print("PUBLIC_CADDY_ROUTE_AND_CUSTOMER_DELIVERY=NOT_VERIFIED_BY_THIS_AUDIT")
    print("PRODUCTION_CHANGED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
