"""Anonymous, aggregate-only market pulse from saved source observations.

This endpoint never reads tenant tables or returns a procurement identity.
It reports 14 UTC calendar-day counts of *first recorded* notices in a bounded
recent persistence snapshot; it is not a complete market census.
"""
from __future__ import annotations

import asyncio
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.database.backend import StorageError
from .guest_search_routes import PUBLIC_HEADERS

router = APIRouter(tags=["public-market-pulse"], include_in_schema=False)

MAX_OBSERVED = 5000
WINDOW_DAYS = 14


def market_pulse_snapshot(database, *, today=None):
    today = today or datetime.now(timezone.utc).date()
    start = today - timedelta(days=WINDOW_DAYS - 1)
    daily = {start + timedelta(days=i): 0 for i in range(WINDOW_DAYS)}
    # Restrict our read to the shared public notice store. No source identifiers,
    # procurement IDs, buyer details, URLs, or per-user analytics leave this route.
    with closing(database.connect()) as conn:
        rows = conn.execute(
            "SELECT first_seen FROM source_opportunities "
            "ORDER BY last_seen DESC LIMIT ?", (MAX_OBSERVED,)
        ).fetchall()
    for row in rows:
        raw = row["first_seen"]
        if not isinstance(raw, str):
            continue
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            d = dt.astimezone(timezone.utc).date()
        except (TypeError, ValueError, OverflowError):
            continue
        if d in daily:
            daily[d] += 1
    days = [{"date": day.isoformat(), "count": count} for day, count in daily.items()]
    return {
        "days": days,
        "window_days": WINDOW_DAYS,
        "new_notices_in_sample": sum(daily.values()),
        "scanned_recent_rows": len(rows),
        "sample_cap": MAX_OBSERVED,
        "scope": "bounded_persisted_source_observations",
        "freshness": "database_first_seen_utc",
        "note": "Actual saved connector notices, not demo or the total market. Missing/late source ingestion changes coverage.",
    }


@router.get("/api/v1/public/market-pulse")
async def public_market_pulse(request: Request):
    peer = getattr(request.client, "host", None) or "unknown"
    retry = request.app.state.guest_search_limiter.consume("guest-search", peer, peer)
    if retry is not None:
        raise HTTPException(
            429, "Too many public requests.",
            headers={"Retry-After": str(retry), **PUBLIC_HEADERS},
        )
    database = getattr(request.app.state.runtime, "database", None)
    if database is None:
        raise HTTPException(503, "Market snapshot unavailable.", headers=PUBLIC_HEADERS)
    try:
        snapshot = await asyncio.to_thread(market_pulse_snapshot, database)
    except (sqlite3.Error, StorageError, ValueError, TypeError, OSError):
        raise HTTPException(503, "Market snapshot unavailable.", headers=PUBLIC_HEADERS) from None
    return JSONResponse(snapshot, headers=PUBLIC_HEADERS)
