"""Genuine current South Ural official originals; ZERO fixtures or test DB writes.

This is a *live research release gate*, run alongside the existing genuine
fenced-Worker→SQLite→query job. If the source is stale, empty or unavailable,
the CI must fail and PR must stay unmerged, rather than showing closed tenders.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.sources.south_ural_public import SouthUralPublicSource
from scripts.verify_south_ural_public_site_candidate import canonical_original


def main():
    try:
        notices = asyncio.run(SouthUralPublicSource(timeout=20).fetch(limit=10))
        now = datetime.now(timezone.utc)
        open_originals = set()
        for notice in notices:
            if not canonical_original(notice.external_id, notice.url):
                raise AssertionError("Unverified first-party original identity")
            if not isinstance(notice.deadline, str):
                continue
            due = datetime.fromisoformat(notice.deadline.replace("Z", "+00:00"))
            if due.tzinfo is None:
                raise AssertionError("Unverified timezone")
            if due.astimezone(timezone.utc) > now:
                open_originals.add(notice.external_id)
        if not open_originals:
            print("SOUTH_URAL_LIVE_CURRENT_OPEN=BLOCKED_NO_OPEN_ORIGINALS")
            return 2
        print("SOUTH_URAL_LIVE_CURRENT_OPEN=PASS")
        print("CURRENT_OPEN_FIRSTPARTY_IDS_COUNT="+str(len(open_originals)))
        print("NO_FIXTURES=YES")
        print("PRODUCTION_CHANGED=NO")
        return 0
    except Exception as exc:
        print("SOUTH_URAL_LIVE_CURRENT_OPEN=BLOCKED")
        print("FAILURE_CLASS="+type(exc).__name__)
        print("PRODUCTION_CHANGED=NO")
        return 2


if __name__=="__main__":
    raise SystemExit(main())
