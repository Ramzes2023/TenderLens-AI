"""Opt-in aggregate-only root operator console; NEVER a customer/admin billing API.

Requires a verified active session AND an exact operator account ID/email digest,
both installed out-of-band. Disabled by default. No mutation endpoints and no PII.
"""
from __future__ import annotations

import asyncio
from contextlib import closing
import hashlib
from html import escape
import hmac
import logging
import os
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from .security import current_account

router = APIRouter(tags=["operator-console"], include_in_schema=False)

FIELDS = {
    "accounts": "SELECT COUNT(*) FROM auth_accounts",
    "organizations": "SELECT COUNT(*) FROM organizations",
    "companies": "SELECT COUNT(*) FROM company_workspaces",
    "running_jobs": "SELECT COUNT(*) FROM durable_jobs WHERE state='running'",
    "queued_jobs": "SELECT COUNT(*) FROM durable_jobs WHERE state='queued'",
    "failed_jobs": "SELECT COUNT(*) FROM durable_jobs WHERE state='failed'",
    "recorded_sources": "SELECT COUNT(DISTINCT source_id) FROM source_opportunities",
    "saved_opportunities": "SELECT COUNT(*) FROM saved_opportunities",
    "support_tickets": "SELECT COUNT(*) FROM support_tickets",
    "quota_admissions": "SELECT COUNT(*) FROM quota_admissions",
    "synchronous_usage": "SELECT COUNT(*) FROM synchronous_usage",
}
NO_STORE = {
    "Cache-Control": "no-store, no-cache, private, max-age=0",
    "Pragma": "no-cache",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy":
        "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; "
        "form-action 'none'; frame-ancestors 'none'",
}


def authorized(account, environment=None):
    env = os.environ if environment is None else environment
    if env.get("VALYQON_OPERATOR_PANEL_ENABLED") != "1" or account is None:
        return False
    if not getattr(account, "is_active", False) or not getattr(account, "email_verified", False):
        return False
    identifier = env.get("VALYQON_SUPERADMIN_ACCOUNT_ID", "")
    digest = env.get("VALYQON_SUPERADMIN_EMAIL_SHA256", "")
    if not re.fullmatch(r"[1-9][0-9]{0,17}", identifier):
        return False
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        return False
    email = str(getattr(account, "email", "") or "").strip().lower()
    account_id = getattr(account, "id", None)
    if type(account_id) is not int or account_id != int(identifier):
        return False
    return hmac.compare_digest(hashlib.sha256(email.encode("utf-8")).hexdigest(), digest)


async def _operator(request: Request):
    # Fail as not found when the feature is disabled; don't disclose its existence.
    if os.environ.get("VALYQON_OPERATOR_PANEL_ENABLED") != "1":
        raise HTTPException(status_code=404, detail="Not found.")
    account = await current_account(request, touch=False)
    if account is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    if not authorized(account):
        raise HTTPException(status_code=403, detail="Operator access required.")
    return account


def overview(database):
    """Aggregate SELECT queries only; never return IDs, emails, payloads or tender text."""
    with closing(database.connect()) as connection:
        result = {}
        for field, sql in FIELDS.items():
            value = connection.execute(sql).fetchone()
            if value is None or type(value[0]) is not int or value[0] < 0:
                raise ValueError("Invalid operator overview count.")
            result[field] = value[0]
    return result


async def _collect(request: Request):
    await _operator(request)
    runtime = getattr(request.app.state, "runtime", None)
    database = getattr(runtime, "database", None)
    if database is None:
        raise HTTPException(status_code=503, detail="Operator metrics unavailable.")
    try:
        result = await asyncio.to_thread(overview, database)
    except Exception:
        raise HTTPException(status_code=503, detail="Operator metrics unavailable.") from None
    # Never log an authenticated account email/token or raw SQL/driver exceptions.
    logging.getLogger("valyqon.operator").info("operator.aggregate_read")
    return result


@router.get("/api/v1/operator/overview")
async def operator_overview(request: Request):
    data = await _collect(request)
    return JSONResponse({"status": "ready", "counts": data,
                         "billing_controls": "not_implemented",
                         "scope": "aggregate_only"}, headers=NO_STORE)


@router.get("/operator", response_class=HTMLResponse)
async def operator_console(request: Request):
    data = await _collect(request)
    labels = {
        "accounts": "Accounts", "organizations": "Organizations",
        "companies": "Company profiles", "running_jobs": "Running jobs",
        "queued_jobs": "Queued jobs", "failed_jobs": "Failed jobs (all-time)",
        "recorded_sources": "Sources with stored opportunities",
        "saved_opportunities": "Saved opportunities",
        "support_tickets": "Support tickets",
        "quota_admissions": "Quota admissions",
        "synchronous_usage": "Synchronous usage entries",
    }
    tiles = "".join(
        '<div class="metric"><span>' + escape(labels[key]) + '</span>'
        '<strong>' + str(data[key]) + '</strong></div>' for key in FIELDS
    )
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>VALYQON Operator Console</title><style>'
        'body{font-family:system-ui,sans-serif;background:#0b1422;color:#e9f0fb;'
        'margin:0;padding:clamp(16px,4vw,60px)}main{max-width:1100px;margin:auto}'
        'h1{font-size:clamp(24px,4vw,40px)}p{color:#a8bdd3;line-height:1.6}'
        '.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px}'
        '.metric{background:#19283d;border:1px solid #354762;border-radius:13px;'
        'padding:22px;display:flex;flex-direction:column;gap:13px}'
        '.metric span{color:#b8cde3;font-size:14px}.metric strong{font-size:31px}'
        'a{color:#a6d9ff}footer{margin-top:30px}</style></head><body><main>'
        '<p>VALYQON AI · Internal operations</p><h1>Operator overview</h1>'
        '<p>Verified account access · aggregate counters only · read-only.</p>'
        '<div class="grid">' + tiles + '</div><footer><p>'
        'Subscription changes, source overrides and AI-dispute content access '
        'are intentionally disabled until audited, scoped operator permissions exist.'
        '</p><p>Refresh this page to reload the latest counts.</p></footer>'
        '</main></body></html>'
    )
    return HTMLResponse(page, headers=NO_STORE)
