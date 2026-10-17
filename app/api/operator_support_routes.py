"""Extra opt-in, verified-superadmin-only tenant support diagnostics; SELECT-only."""
from __future__ import annotations

import asyncio
from contextlib import closing
from html import escape
import logging
import os

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from .operator_routes import _operator, NO_STORE

router = APIRouter(tags=["operator-support"], include_in_schema=False)


def tenant_rows(database, *, after_id=0, limit=25):
    """Bounded one-page organization counts; no tender content, account emails or tokens."""
    if type(after_id) is not int or after_id < 0 or not 1 <= limit <= 25:
        raise ValueError("Unsupported tenant cursor.")
    with closing(database.connect()) as conn:
        rows = conn.execute(
            """SELECT o.id, o.name, o.created_at,
                CASE WHEN o.personal_account_id IS NULL THEN 0 ELSE 1 END AS personal,
                (SELECT COUNT(*) FROM organization_members m WHERE m.organization_id=o.id) AS members,
                (SELECT COUNT(*) FROM company_workspaces w WHERE w.organization_id=o.id) AS companies,
                (SELECT COUNT(*) FROM discovery_search_history h WHERE h.organization_id=o.id) AS searches,
                (SELECT MAX(h.created_at) FROM discovery_search_history h WHERE h.organization_id=o.id) AS last_search,
                (SELECT COUNT(*) FROM saved_opportunities s WHERE s.organization_id=o.id) AS saved,
                (SELECT COUNT(*) FROM deadline_alert_receipts r WHERE r.organization_id=o.id AND r.state='sent') AS alerts_sent,
                (SELECT COUNT(*) FROM deadline_alert_receipts r WHERE r.organization_id=o.id AND r.state='failed') AS alerts_failed,
                (SELECT COUNT(*) FROM deadline_alert_preferences p WHERE p.organization_id=o.id AND (p.email_enabled=1 OR p.telegram_enabled=1)) AS alert_opt_ins,
                (SELECT COUNT(*) FROM support_tickets t WHERE t.organization_id=o.id) AS tickets
               FROM organizations o WHERE o.id>? ORDER BY o.id LIMIT ?""",
            (after_id, limit),
        ).fetchall()
    result = []
    for row in rows:
        result.append({
            "id": int(row["id"]), "name": str(row["name"]), "created_at": str(row["created_at"]),
            "personal": bool(row["personal"]), "members": int(row["members"]),
            "companies": int(row["companies"]), "searches": int(row["searches"]),
            "last_search": row["last_search"], "saved": int(row["saved"]),
            "alerts_sent": int(row["alerts_sent"]), "alerts_failed": int(row["alerts_failed"]),
            "alert_opt_ins": int(row["alert_opt_ins"]), "tickets": int(row["tickets"]),
            "subscription": "billing_not_implemented",
        })
    return result


async def _scope(request: Request):
    if os.environ.get("VALYQON_OPERATOR_SUPPORT_ENABLED") != "1":
        raise HTTPException(404, "Not found.")
    actor = await _operator(request)
    database = getattr(getattr(request.app.state, "runtime", None), "database", None)
    if database is None:
        raise HTTPException(503, "Operator support metrics unavailable.")
    return actor, database


async def _page(request: Request, after_id: int):
    actor, database = await _scope(request)
    try:
        rows = await asyncio.to_thread(tenant_rows, database, after_id=after_id)
    except Exception:
        raise HTTPException(503, "Operator support metrics unavailable.") from None
    logging.getLogger("valyqon.operator").info(
        "operator.tenant_list_read actor_id=%s cursor=%s", actor.id, after_id,
    )
    return rows


@router.get("/api/v1/operator/tenants")
async def operator_tenant_list(request: Request, after_id: int = Query(default=0, ge=0)):
    rows = await _page(request, after_id)
    return JSONResponse({
        "tenants": rows,
        "next_after_id": rows[-1]["id"] if len(rows) == 25 else None,
        "billing_controls": "disabled",
        "audit_retention": "application_logs_only",
    }, headers=NO_STORE)


@router.get("/operator/tenants", response_class=HTMLResponse)
async def operator_tenant_page(request: Request, after_id: int = Query(default=0, ge=0)):
    rows = await _page(request, after_id)
    body = []
    for item in rows:
        body.append(
            "<tr><td>" + str(item["id"]) + "</td><td>" + escape(item["name"]) + "</td><td>"
            + str(item["members"]) + "</td><td>" + str(item["companies"])
            + "</td><td>" + str(item["searches"]) + "</td><td>" + str(item["saved"])
            + "</td><td>" + str(item["alert_opt_ins"]) + "</td><td>"
            + str(item["alerts_sent"]) + "</td><td>" + str(item["alerts_failed"])
            + "</td><td>" + str(item["tickets"]) + "</td></tr>"
        )
    next_page = (f'<a href="/operator/tenants?after_id={rows[-1]["id"]}">Next page →</a>'
                 if len(rows) == 25 else "")
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>VALYQON — operator tenant diagnostics</title><style>'
        'body{font-family:system-ui,sans-serif;background:#071625;color:#eaf1fc;padding:30px}'
        'main{max-width:1250px;margin:auto}a{color:#a7d9ff}table{border-collapse:collapse;width:100%}'
        'th,td{border-bottom:1px solid #31465d;padding:12px;text-align:left}'
        'th{color:#add1eb}table{display:block;overflow-x:auto}p{color:#b0c3d3}'
        '</style></head><body><main><p><a href="/operator">Operator overview</a></p>'
        '<h1>Tenant support diagnostics</h1>'
        '<p>Read-only. Restricted to the verified operator, separately enabled.'
        ' No account email, tender body or private team note is returned.</p>'
        '<p>Counts are recorded application data, not proof of successful provider delivery.'
        ' Billing/subscriptions are not implemented; action reads are logged by the application,'
        ' not guaranteed as a durable audit ledger.</p><table><thead><tr>'
        '<th>ID</th><th>Organization</th><th>Members</th><th>Companies</th>'
        '<th>Searches</th><th>Saved</th><th>Alert opt-ins</th><th>Sent</th>'
        '<th>Failed</th><th>Support tickets</th></tr></thead><tbody>'
        + "".join(body) + '</tbody></table><p>' + next_page +
        '</p></main></body></html>'
    )
    return HTMLResponse(html, headers=NO_STORE)
