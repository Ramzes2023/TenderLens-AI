"""Public, identity-free aggregates for the VALYQON visual intelligence wall.

All values originate from one bounded read of the normalized shared connector
store. No sample notices, invented percentages, buyer/platform breakdowns,
tenant data or currency mixing are used. The numbers describe this snapshot,
NOT every tender in Russia or the world.
"""
from __future__ import annotations

import asyncio
import json
import math
import sqlite3
from collections import Counter
from contextlib import closing
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from app.database.backend import StorageError
from .guest_search_routes import PUBLIC_HEADERS
from .public_market_routes import MAX_OBSERVED

router = APIRouter(tags=["public-market-intelligence"], include_in_schema=False)

RUB_BANDS = ("under_1m", "1_to_5m", "5_to_10m", "10_to_50m", "50m_plus")
DEADLINE_BANDS = ("overdue", "within_7d", "8_to_30d", "over_30d", "unspecified")


def _utc_date(raw):
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).date()
    except (ValueError, TypeError, OverflowError):
        return None


def market_intelligence_snapshot(database, *, today=None, allowed_sources=None):
    today = today or datetime.now(timezone.utc).date()
    start = today - timedelta(days=13)
    observed = {start + timedelta(days=i): {"total": 0, "priced": 0}
                for i in range(14)}
    rub = dict.fromkeys(RUB_BANDS, 0)
    deadlines = dict.fromkeys(DEADLINE_BANDS, 0)
    currencies = Counter()
    completeness = dict.fromkeys(("title", "price", "currency", "deadline"), 0)
    first_week, second_week = 0, 0
    priced_notices, priced_rub = 0, 0
    valid_observations = 0

    # Read only shared connector notices, bounded; never query tenant-owned
    # saved opportunities or organization search history.
    with closing(database.connect()) as conn:
        rows = conn.execute(
            "SELECT source_id, notice_json, first_seen FROM source_opportunities "
            "ORDER BY last_seen DESC LIMIT ?", (MAX_OBSERVED,)
        ).fetchall()

    if allowed_sources is not None:
        rows = [row for row in rows if row["source_id"] in allowed_sources]
    for row in rows:
        try:
            notice = json.loads(row["notice_json"])
        except (ValueError, TypeError):
            continue
        if not isinstance(notice, dict) or not isinstance(notice.get("source"), str):
            continue
        valid_observations += 1
        first_date = _utc_date(row["first_seen"])
        title_ok = isinstance(notice.get("title"), str) and bool(notice["title"].strip())
        price = notice.get("initial_price")
        price_ok = type(price) in (float, int) and math.isfinite(price) and price >= 0
        currency = notice.get("currency")
        currency_ok = isinstance(currency, str) and len(currency) == 3 and currency.isalpha() and currency.isupper()
        deadline = _utc_date(notice.get("deadline"))
        for key, okay in (("title", title_ok), ("price", price_ok),
                          ("currency", currency_ok), ("deadline", deadline is not None)):
            completeness[key] += int(okay)

        if first_date in observed:
            observed[first_date]["total"] += 1
            observed[first_date]["priced"] += int(price_ok)
            if first_date < today - timedelta(days=6):
                first_week += 1
            else:
                second_week += 1

        if price_ok:
            priced_notices += 1
        if price_ok and currency == "RUB":
            priced_rub += 1
            rub[
                "under_1m" if price < 1_000_000 else
                "1_to_5m" if price < 5_000_000 else
                "5_to_10m" if price < 10_000_000 else
                "10_to_50m" if price < 50_000_000 else
                "50m_plus"
            ] += 1
        if currency_ok:
            # Aggregate into a small fixed group, no platform or buyer keys.
            currencies[currency if currency in {"RUB", "EUR", "USD", "KZT", "AZN"} else "OTHER"] += 1

        if deadline is None:
            deadlines["unspecified"] += 1
        else:
            days_left = (deadline - today).days
            deadlines[
                "overdue" if days_left < 0 else
                "within_7d" if days_left <= 7 else
                "8_to_30d" if days_left <= 30 else
                "over_30d"
            ] += 1

    days = [
        {"date": day.isoformat(), "count": stats["total"], "priced": stats["priced"]}
        for day, stats in observed.items()
    ]
    return {
        "scope": "bounded_persisted_source_observations",
        "window_days": 14,
        "sample_cap": MAX_OBSERVED,
        "scanned_recent_rows": len(rows),
        "valid_records_in_sample": valid_observations,
        "new_notices_14d": first_week + second_week,
        "week_comparison": {"previous_7d": first_week, "latest_7d": second_week},
        "daily": days,
        "priced_notices": priced_notices,
        "priced_rub_notices": priced_rub,
        "rub_price_bands": rub,
        "deadline_bands": deadlines,
        "currency_counts": {key: currencies[key] for key in ("RUB", "EUR", "USD", "KZT", "AZN", "OTHER")},
        "field_coverage": completeness,
        "note": "Only observed stored source notices in a capped snapshot; categories are not market-wide, source health or real-time indicators. Currency amounts are never combined.",
    }


@router.get("/api/v1/public/market-intelligence")
async def public_market_intelligence(request: Request):
    peer = getattr(request.client, "host", None) or "unknown"
    retry = request.app.state.guest_search_limiter.consume("guest-search", peer, peer)
    if retry is not None:
        raise HTTPException(429, "Too many public requests.",
                            headers={"Retry-After": str(retry), **PUBLIC_HEADERS})
    database = getattr(request.app.state.runtime, "database", None)
    if database is None:
        raise HTTPException(503, "Market intelligence unavailable.", headers=PUBLIC_HEADERS)
    try:
        report = await asyncio.to_thread(
            market_intelligence_snapshot, database,
            allowed_sources=getattr(request.app.state, "public_source_allowed_keys", None),
        )
    except (sqlite3.Error, StorageError, ValueError, TypeError, OSError):
        raise HTTPException(503, "Market intelligence unavailable.", headers=PUBLIC_HEADERS) from None
    return JSONResponse(report, headers=PUBLIC_HEADERS)
