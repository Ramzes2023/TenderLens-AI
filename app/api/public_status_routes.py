"""Public status without fabricated source success or external delivery claims."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from html import escape

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter(tags=["public-status"], include_in_schema=False)

HEADERS = {
    "Cache-Control": "no-store, max-age=0",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
}


async def snapshot(runtime):
    database = getattr(runtime, "database", None)
    database_up = False
    if database is not None:
        try:
            database_up = bool(await asyncio.to_thread(database.healthy))
        except Exception:
            database_up = False
    checked = datetime.now(timezone.utc).isoformat(timespec="seconds")
    components = [
        {"id": "http", "name": "Public API", "state": "operational",
         "evidence": "The status request reached this application instance."},
        {"id": "database", "name": "Database", "state": "operational" if database_up else "degraded",
         "evidence": "A live read-only database connection succeeded." if database_up
                     else "Live database check did not succeed."},
        {"id": "sources", "name": "Tender sources", "state": "unverified",
         "evidence": "External procurement sites were not independently probed by this request."},
        {"id": "alerts", "name": "Email and Telegram alerts", "state": "unverified",
         "evidence": "Provider configuration does not prove end-to-end delivery."},
        {"id": "payments", "name": "Checkout and billing", "state": "not_enabled",
         "evidence": "Commercial payment collection is disabled for the pilot."},
    ]
    return {
        "checked_at": checked, "scope": "this_app_instance",
        "overall": "partial" if database_up else "degraded",
        "uptime_percent": None, "sources_verified": False,
        "components": components,
        "notice": "This page is a live component snapshot, not a historical SLA or independent uptime proof.",
    }


@router.get("/status.json")
async def public_status_json(request: Request):
    data = await snapshot(request.app.state.runtime)
    return JSONResponse(data, headers=HEADERS)


@router.get("/status", response_class=HTMLResponse)
async def public_status_html(request: Request):
    data = await snapshot(request.app.state.runtime)
    states = {"operational": ("Operational", "#67d8a8"),
              "degraded": ("Degraded", "#ff9185"),
              "unverified": ("Unverified", "#afbbc9"),
              "not_enabled": ("Not enabled", "#afbbc9")}
    cards = []
    for item in data["components"]:
        label, color = states[item["state"]]
        cards.append(
            '<article class="tile"><div class="tilehead"><h2>' + escape(item["name"]) + '</h2>'
            '<span style="color:' + color + '">' + escape(label) + '</span></div><p>'
            + escape(item["evidence"]) + '</p></article>'
        )
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>VALYQON AI — service status</title>'
        '<style>body{font-family:system-ui,sans-serif;background:#091526;color:#ecf4ff;margin:0;'
        'padding:clamp(20px,5vw,64px)}main{max-width:940px;margin:auto}a{color:#b6dbff}'
        'h1{font-size:clamp(26px,5vw,40px)}h2{font-size:18px;margin:0}'
        'p{line-height:1.55;color:#a9bad0}.grid{display:grid;gap:14px;'
        'grid-template-columns:repeat(auto-fit,minmax(260px,1fr))}'
        '.tile{padding:22px;border:1px solid #34465f;border-radius:16px;background:#172940}'
        '.tilehead{display:flex;justify-content:space-between;gap:15px;align-items:center}'
        '.tilehead span{font-size:13px;font-weight:700}footer{margin-top:34px}</style></head>'
        '<body><main><a href="/">VALYQON AI</a><h1>Service status</h1>'
        '<p>Current application-instance diagnostics. Unknown external states are intentionally'
        ' not reported as healthy.</p><div class="grid">' + ''.join(cards) + '</div><footer>'
        '<p>Checked at: ' + escape(data["checked_at"]) + ' UTC · No historical uptime'
        ' percentage is calculated. An unverified source is not confirmed operational.</p>'
        '<p><a href="/status.json">Machine-readable status</a> · '
        '<a href="/dashboard#source-health">Authenticated source diagnostics</a></p>'
        '</footer></main></body></html>'
    )
    return HTMLResponse(html, headers=HEADERS)
