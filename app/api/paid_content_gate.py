"""Pre-billing public-release safety gate for source-derived tender details.

This is NOT an entitlement service or substitute for verified subscriptions.
If activated, it denies *all* detailed source-derived read/mutation routes:
there is no merchant ledger or verified paid customer to authorize today.

Public deployments enable this guard until real paid entitlements are implemented
and independently audited. Local private preview and development retain their
own existing protected user-owned document workflows.
"""
from __future__ import annotations

import re

from fastapi.responses import JSONResponse

PATH = re.compile(r"^/api/v1/organizations/[0-9]+/(.*)$")
ORG_PREFIXES = (
    "discover/", "discovery/", "shortlist", "activity",
    "monitoring/scan", "monitoring/status", "scoring/evaluate",
)
COMPANY_SOURCE = re.compile(
    r"^companies/[0-9]+/(?:discovery/|analytics(?:/|$)|scoring/runs(?:/|$))"
)
DENIED = {
    "/api/v1/monitoring/scan",
    "/api/v1/monitoring/status",
}
HEADERS = {
    "Cache-Control": "private, no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


def requires_verified_paid_entitlement(path: str) -> bool:
    """Minimal denylist for source-derived tender metadata routes.

    Endpoints added later must be audited and covered by new tests BEFORE
    enabling commercial detail access. This gate cannot secure notification
    workers or external URLs, so commercial release remains blocked.
    """
    if path in DENIED:
        return True
    match = PATH.fullmatch(path)
    if match is None:
        return False
    relative = match.group(1)
    return relative.startswith(ORG_PREFIXES) or bool(COMPANY_SOURCE.match(relative))


async def block_paid_details_before_billing(request, call_next):
    if requires_verified_paid_entitlement(request.url.path):
        return JSONResponse(
            {"detail": "Source details are not yet available: verified paid subscription billing is not enabled.",
             "code": "PAID_SOURCE_DETAILS_LOCKED"},
            status_code=403, headers=HEADERS,
        )
    return await call_next(request)
