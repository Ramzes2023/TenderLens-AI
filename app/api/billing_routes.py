"""Provider-neutral, truthful read-only organization billing readiness.

No payments, invoices, subscriptions or upgrade checkout are fabricated. This
endpoint reports only recorded first-party usage until a real signed payment
gateway/merchant ledger is implemented and accepted in sandbox.
"""
from __future__ import annotations

import asyncio
from contextlib import closing

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.database.backend import StorageError
from .security import current_account

router = APIRouter(prefix="/api/v1/organizations/{organization_id}", tags=["billing"])


class BillingAccessDenied(Exception):
    pass


class BillingNeedsCompany(Exception):
    pass


def billing_snapshot(database, account_id, organization_id):
    if type(account_id) is not int or type(organization_id) is not int or organization_id <= 0:
        raise BillingAccessDenied()
    with closing(database.connect()) as conn:
        membership = conn.execute(
            "SELECT role FROM organization_members WHERE account_id=? AND organization_id=?",
            (account_id, organization_id),
        ).fetchone()
        if membership is None or membership["role"] not in ("owner", "admin"):
            raise BillingAccessDenied()
        org = conn.execute(
            "SELECT personal_account_id FROM organizations WHERE id=?",
            (organization_id,),
        ).fetchone()
        if org is None or org["personal_account_id"] is not None:
            raise BillingNeedsCompany()
        stats = conn.execute(
            "SELECT "
            "(SELECT COUNT(*) FROM discovery_search_history WHERE organization_id=?) AS searches, "
            "(SELECT COUNT(*) FROM saved_opportunities WHERE organization_id=?) AS saved, "
            "(SELECT COUNT(*) FROM company_workspaces WHERE organization_id=?) AS companies, "
            "(SELECT COUNT(*) FROM organization_members WHERE organization_id=?) AS seats",
            (organization_id, organization_id, organization_id, organization_id),
        ).fetchone()
        return {
            "organization_id": organization_id,
            "billing_status": "not_enabled",
            "active_plan": None,
            "subscription": None,
            "next_charge_at": None,
            "payment_method": None,
            "payment_history": [],
            "invoices": [],
            "upgrade_available": False,
            "usage": {
                "recorded_searches": int(stats["searches"]),
                "saved_opportunities": int(stats["saved"]),
                "company_profiles": int(stats["companies"]),
                "team_seats": int(stats["seats"]),
            },
            "notice": "Recorded usage is not a billed quantity. Billing and invoice issuance are not yet configured.",
        }


@router.get("/billing")
async def get_organization_billing(organization_id: int, request: Request):
    if organization_id <= 0:
        raise HTTPException(422, "Invalid organization.")
    account = await current_account(request, touch=False)
    if account is None:
        raise HTTPException(401, "Authentication required.")
    database = getattr(getattr(request.app.state, "runtime", None), "database", None)
    if database is None:
        raise HTTPException(503, "Billing overview unavailable.")
    try:
        data = await asyncio.to_thread(billing_snapshot, database, account.id, organization_id)
    except BillingAccessDenied:
        raise HTTPException(403, "Billing overview requires organization owner/admin.") from None
    except BillingNeedsCompany:
        raise HTTPException(409, "Select a shared organization for company billing.") from None
    except (StorageError, ValueError, TypeError):
        raise HTTPException(503, "Billing overview unavailable.") from None
    return JSONResponse(data, headers={"Cache-Control": "private, no-store"})
