"""Authenticated tender lifecycle endpoints for active organization company."""
from __future__ import annotations

import asyncio
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

from app.database.backend import StorageError
from app.workspaces.lifecycle import (
    SavedTenderWorkflow, WorkflowConflict, WorkflowDenied, WorkflowMissing,
)
from .organization_workflow_routes import _account, _active_company
from .security import require_same_origin_browser_request

router = APIRouter(prefix="/api/v1/organizations/{organization_id}/shortlist",
                   tags=["saved-tender-workflow"])


class WorkflowUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stage: Literal["new", "reviewing", "preparing", "submitted", "won", "lost", "archived"]
    note: str = Field(max_length=2000)
    expected_revision: int = Field(ge=0, lt=2147483647)


async def _scope(request, organization_id, saved_id):
    if organization_id <= 0 or saved_id <= 0:
        raise HTTPException(422, "Invalid organization or saved opportunity ID.")
    account = await _account(request)
    workspace = await _active_company(request, account, organization_id)
    if workspace is None:
        raise HTTPException(409, "Activate a company to manage saved opportunities.")
    database = getattr(request.app.state.runtime, "database", None)
    if database is None:
        raise HTTPException(503, "Tender workflow unavailable.")
    return SavedTenderWorkflow(database), dict(
        account_id=account.id, organization_id=organization_id,
        company_id=workspace.id, saved_id=saved_id,
    )


async def _call(fn, **kwargs):
    try:
        return await asyncio.to_thread(fn, **kwargs)
    except WorkflowDenied:
        raise HTTPException(403, "Workspace access denied.") from None
    except WorkflowMissing:
        raise HTTPException(404, "Saved opportunity not found in the active company.") from None
    except WorkflowConflict:
        raise HTTPException(409, "The opportunity was changed by another team member. Reload.") from None
    except (StorageError, ValueError):
        raise HTTPException(503, "Tender workflow storage unavailable.") from None


@router.get("/{saved_id}/workflow")
async def get_workflow(organization_id: int, saved_id: int, request: Request):
    service, scope = await _scope(request, organization_id, saved_id)
    result = await _call(service.get, **scope)
    return JSONResponse(result, headers={"Cache-Control": "private, no-store"})


@router.patch("/{saved_id}/workflow")
async def update_workflow(organization_id: int, saved_id: int, payload: WorkflowUpdate, request: Request):
    require_same_origin_browser_request(request)
    service, scope = await _scope(request, organization_id, saved_id)
    result = await _call(service.update, **scope, **payload.model_dump())
    return JSONResponse(result, headers={"Cache-Control": "private, no-store"})


@router.get("/{saved_id}/workflow/events")
async def workflow_events(organization_id: int, saved_id: int, request: Request):
    service, scope = await _scope(request, organization_id, saved_id)
    result = await _call(service.events, **scope)
    return JSONResponse(result, headers={"Cache-Control": "private, no-store"})


# Actual organization/company-scoped assignees and internal two-person approvals.
# They are not official procurement submissions or signed contracting decisions.
from app.workspaces.team_decisions import TeamDecision


class TeamAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["assign", "request", "approve", "reject", "withdraw"]
    expected_revision: int = Field(ge=0, le=2147483646)
    assignee_account_id: int | None = Field(default=None, gt=0)


async def _team_scope(request, organization_id, saved_id):
    _, scope = await _scope(request, organization_id, saved_id)
    return TeamDecision(request.app.state.runtime.database), scope


@router.get("/{saved_id}/team")
async def get_team(organization_id: int, saved_id: int, request: Request):
    service, scope = await _team_scope(request, organization_id, saved_id)
    result = await _call(service.get, **scope)
    return JSONResponse(result, headers={"Cache-Control": "private, no-store"})


@router.patch("/{saved_id}/team")
async def update_team(organization_id: int, saved_id: int, payload: TeamAction, request: Request):
    require_same_origin_browser_request(request)
    service, scope = await _team_scope(request, organization_id, saved_id)
    result = await _call(service.change, **scope, **payload.model_dump())
    return JSONResponse(result, headers={"Cache-Control": "private, no-store"})


@router.get("/{saved_id}/team/events")
async def team_events(organization_id: int, saved_id: int, request: Request):
    service, scope = await _team_scope(request, organization_id, saved_id)
    result = await _call(service.events, **scope)
    return JSONResponse(result, headers={"Cache-Control": "private, no-store"})
