"""Public search of *persisted real connector notices*, with a strict allowlist.

No upstream requests are made during a guest request, and no private organization
or imported-PDF records are queried. The output intentionally has no record IDs,
URLs, source names, buyers, tender numbers, documents, regions or full summaries.
Never use frontend blur/disabled links as an authorization boundary.
"""
from __future__ import annotations

import asyncio
import json
import math
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app.database.backend import StorageError
from app.sources.lenobl_small_public import _canonical as _official_lenobl_url
from app.sources.ru_samara_public_list import (
    GRID as _official_samara_grid, NATIVE_NUMBER as _samara_native_number,
    SOURCE_ID as _samara_source,
)
from .public_source_deadline import eligible_published_deadline

router = APIRouter(tags=["guest-search"], include_in_schema=False)

# A bounded database snapshot prevents arbitrary anonymous full-table scans.
# The response must never describe these counts as all procurement notices.
MAX_CANDIDATES = 5000
MAX_PREVIEWS = 12
PUBLIC_HEADERS = {
    "Cache-Control": "no-store, max-age=0",
    "Pragma": "no-cache",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}


def _public_title(value):
    """Keep the actual notice title, but do not render embedded URLs."""
    if not isinstance(value, str):
        return ""
    title = re.sub(r"https?://\S+|www\.\S+", "", value, flags=re.I)
    title = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "", title)
    title = " ".join(title.split())
    return title[:200]


def _public_preview(notice):
    """Construct the response from an explicit public field allowlist."""
    title = _public_title(notice.get("title"))
    # A connector may embed the buyer's full name directly in a free-text
    # headline. Remove explicit buyer identity from the published title too.
    buyer = notice.get("customer")
    if isinstance(buyer, str):
        buyer = " ".join(buyer.split())
        if len(buyer) >= 6:
            title = re.sub(re.escape(buyer), "[hidden]", title, flags=re.I)
    if not title:
        return None
    price = notice.get("initial_price")
    if type(price) not in (int, float) or not math.isfinite(price) or price < 0:
        price = None
    currency = notice.get("currency")
    if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
        currency = None
    deadline = notice.get("deadline")
    if not isinstance(deadline, str) or len(deadline) > 120:
        deadline = None
    return {
        "title": title,
        "initial_price": price,
        "currency": currency,
        "deadline": deadline,
    }


def search_persisted_notices(database, query: str, *, limit: int = MAX_PREVIEWS,
                             active_only: bool = False, now=None, allowed_sources=None):
    """Read a bounded snapshot of the shared, real connector storage.

    Do not search saved_opportunities, discovery_search_history or tenant data.
    Mixed-case Cyrillic search is performed with Python casefold to avoid SQLite
    LOWER's ASCII-only limitation and retain PostgreSQL parity.
    """
    limit = max(1, min(int(limit), MAX_PREVIEWS))
    keywords = query.casefold().split()[:12]
    with closing(database.connect()) as conn:
        rows = conn.execute(
            "SELECT notice_json, last_seen FROM source_opportunities "
            "ORDER BY last_seen DESC LIMIT ?",
            (MAX_CANDIDATES,),
        ).fetchall()

    results = []
    if active_only:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("Active-only snapshot requires UTC-aware time.")
        now = now.astimezone(timezone.utc)
    for row in rows:
        try:
            notice = json.loads(row["notice_json"])
        except (ValueError, TypeError, KeyError):
            continue
        if not isinstance(notice, dict) or not isinstance(notice.get("source"), str):
            continue
        if allowed_sources is not None and notice["source"] not in allowed_sources:
            continue
        # Isolated live-source preview must never advertise expired archive
        # procurements as currently actionable. Production's existing guest
        # handler keeps its historical storage/search semantics unchanged.
        if active_only:
            try:
                observed = datetime.fromisoformat(
                    str(row["last_seen"]).replace("Z", "+00:00")
                )
                if observed.tzinfo is None:
                    continue
                age = (now - observed.astimezone(timezone.utc)).total_seconds()
                if not 0 <= age <= 7200:
                    continue
                if not eligible_published_deadline(
                    notice.get("source"), notice.get("deadline"), now=now,
                ):
                    continue
            except (ValueError, TypeError, OverflowError):
                continue
        # Newly staged Lenobl notices must retain the exact official
        # list-discovered canonical identity. Do not expose imported or
        # malformed rows merely because they contain a future-looking date.
        if active_only and notice["source"] == "lenobl_small_public":
            identity = notice.get("external_id")
            original = notice.get("url")
            if (type(identity) is not str or type(original) is not str
                    or _official_lenobl_url(original) != (identity, original)
                    or notice.get("initial_price") is not None
                    or notice.get("currency") is not None
                    or notice.get("tender_number") is not None):
                continue
        if active_only and notice["source"] == _samara_source:
            # First-party Samara native JSON gives original LIST fields only.
            # Its individual deep-detail cards remain unavailable. Never
            # assert that those fields have independently verified deep URLs.
            ident = notice.get("external_id")
            number = notice.get("tender_number")
            price = notice.get("initial_price")
            currency = notice.get("currency")
            if (type(ident) is not str
                    or not re.fullmatch(r"[0-9]{6,12}", ident)
                    or type(number) is not str
                    or _samara_native_number.fullmatch(number) is None
                    or notice.get("url") != _official_samara_grid
                    or notice.get("region") != "Самарская область"
                    or type(notice.get("customer")) is not str
                    or not notice["customer"].strip()
                    or ((price is None and currency is not None)
                        or (price is not None and (
                            type(price) not in (int, float)
                            or not math.isfinite(price) or price <= 0
                            or currency != "RUB")))):
                continue
        # Only the visible title is searchable in guest mode. Searching hidden
        # buyer/URL/source/summary fields creates an information-disclosure oracle.
        public = _public_preview(notice)
        if public is None:
            continue
        haystack = public["title"].casefold()
        if any(keyword not in haystack for keyword in keywords):
            continue
        results.append(public)
        if len(results) >= limit:
            break

    return {
        "results": results,
        "shown": len(results),
        "search": query,
        "limited_preview": True,
        "details_locked": True,
        "source": "stored_connector_notices",
        "scope": "bounded_recent_snapshot",
        "candidate_limit": MAX_CANDIDATES,
        "notice": (
            "Only saved connector notices are searched. Results are previews, "
            "not a live procurement-platform check or an exhaustive count."
        ),
    }


@router.get("/api/v1/public/opportunities")
async def guest_opportunity_search(
    request: Request,
    q: str = Query(default="", max_length=120),
):
    query = " ".join(q.strip().split())
    # Accept empty searches to display real recently persisted notices, but
    # never substitute handcrafted/fake cards when none exist.
    limiter = request.app.state.guest_search_limiter
    peer = getattr(request.client, "host", None) or "unknown"
    retry_after = limiter.consume("guest-search", peer, peer)
    if retry_after is not None:
        raise HTTPException(
            429, "Too many public searches. Try again later.",
            headers={"Retry-After": str(retry_after), **PUBLIC_HEADERS},
        )
    database = getattr(request.app.state.runtime, "database", None)
    if database is None:
        raise HTTPException(503, "Real tender search is temporarily unavailable.",
                            headers=PUBLIC_HEADERS)
    try:
        result = await asyncio.to_thread(
            search_persisted_notices, database, query,
            active_only=(getattr(request.app.state, "public_source_active_only", False) is True),
            allowed_sources=getattr(request.app.state, "public_source_allowed_keys", None),
        )
    except (sqlite3.Error, StorageError, ValueError, TypeError, OSError):
        raise HTTPException(503, "Real tender search is temporarily unavailable.",
                            headers=PUBLIC_HEADERS) from None
    return JSONResponse(result, headers=PUBLIC_HEADERS)
