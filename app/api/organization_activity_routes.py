"""Authenticated, company-scoped audit read view for team owner/admin."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.database.repository import DatabaseAuthorizationError, DatabaseError
from .organization_workflow_routes import _account, _active_company, _shortlist_repository

router = APIRouter(prefix="/api/v1/organizations/{organization_id}", tags=["team-audit"])


@router.get("/activity")
async def company_activity(organization_id: int, request: Request):
    if organization_id <= 0:
        raise HTTPException(status_code=422, detail="Invalid organization.")
    actor = await _account(request)
    company = await _active_company(request, actor, organization_id)
    if company is None:
        raise HTTPException(status_code=409, detail="Activate a company before viewing activity.")
    repo = _shortlist_repository(request)
    try:
        events = await asyncio.to_thread(
            repo.list_organization_activity_for_company,
            account_id=actor.id, organization_id=organization_id,
            company_id=company.id, limit=100,
        )
    except DatabaseAuthorizationError:
        raise HTTPException(status_code=403, detail="Only organization owners and admins can view activity.") from None
    except DatabaseError:
        raise HTTPException(status_code=503, detail="Company activity unavailable.") from None
    return JSONResponse(
        {"company_id": company.id, "events": events, "scope": "selected_company"},
        headers={"Cache-Control": "private, no-store"},
    )
