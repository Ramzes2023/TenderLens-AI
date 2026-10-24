"""Authenticated opt-in deadline-notification settings for active company."""
from __future__ import annotations

import asyncio
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from app.launch.deadline_alerts import DeadlineAlerts
from .organization_workflow_routes import _account, _active_company
from .security import require_same_origin_browser_request

router = APIRouter(prefix="/api/v1/organizations/{organization_id}",
                   tags=["deadline-alerts"])

class DeadlinePreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email_enabled: bool = False
    telegram_enabled: bool = False

async def _scope(organization_id, request):
    account = await _account(request)
    company = await _active_company(request, account, organization_id)
    if company is None:
        raise HTTPException(409, "Activate a company before configuring reminders.")
    database = getattr(request.app.state.runtime, "database", None)
    if database is None:
        raise HTTPException(503, "Deadline settings unavailable.")
    return account, company, DeadlineAlerts(database)

@router.get("/deadline-alerts/preferences", response_model=DeadlinePreferences)
async def get_preferences(organization_id: int, request: Request):
    account, company, service = await _scope(organization_id, request)
    return await asyncio.to_thread(
        service.preferences, account_id=account.id, organization_id=organization_id,
        company_id=company.id,
    )

@router.put("/deadline-alerts/preferences", response_model=DeadlinePreferences)
async def update_preferences(organization_id: int, payload: DeadlinePreferences,
                             request: Request):
    require_same_origin_browser_request(request)
    account, company, service = await _scope(organization_id, request)
    try:
        return await asyncio.to_thread(
            service.set_preferences, account_id=account.id,
            organization_id=organization_id, company_id=company.id,
            email_enabled=payload.email_enabled,
            telegram_enabled=payload.telegram_enabled,
        )
    except PermissionError:
        raise HTTPException(403, "Organization membership required.") from None


@router.get("/deadline-alerts/history")
async def get_deadline_delivery_history(organization_id: int, request: Request):
    """Actual sender receipts for this account and selected company only."""
    account, company, service = await _scope(organization_id, request)
    try:
        result = await asyncio.to_thread(
            service.delivery_history, account_id=account.id,
            organization_id=organization_id, company_id=company.id,
        )
    except PermissionError:
        raise HTTPException(403, "Organization membership required.") from None
    except (ValueError, TypeError):
        raise HTTPException(503, "Delivery journal unavailable.") from None
    from fastapi.responses import JSONResponse
    return JSONResponse(result, headers={"Cache-Control": "private, no-store"})
