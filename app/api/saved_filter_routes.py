"""Scoped personal named Discovery filter presets; no background alerts enabled."""
from __future__ import annotations

import asyncio
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.database.backend import StorageError
from app.workspaces.saved_filters import (
    STAGES, SavedSearchPresets, PresetLimitError, PresetMissingError,
    PresetPermissionError,
)
from .organization_workflow_routes import _account, _active_company
from .security import require_same_origin_browser_request

router = APIRouter(prefix="/api/v1/organizations/{organization_id}/saved-searches",
                   tags=["saved-search-filters"])


class FilterFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    keyword: str = Field(max_length=160)
    source: str = Field(max_length=160)
    buyer: str = Field(max_length=160)
    currency: str = Field(max_length=160)
    value: str = Field(max_length=160)
    fit: str = Field(max_length=160)
    deadline: str = Field(max_length=160)
    published: str = Field(max_length=160)


class SavePreset(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    filters: FilterFields


async def _context(organization_id, request):
    if organization_id <= 0:
        raise HTTPException(422, "Invalid organization.")
    actor = await _account(request)
    company = await _active_company(request, actor, organization_id)
    if company is None:
        raise HTTPException(409, "Activate a company to manage saved filters.")
    database = getattr(request.app.state.runtime, "database", None)
    if database is None:
        raise HTTPException(503, "Saved filter storage unavailable.")
    return SavedSearchPresets(database), {
        "organization_id": organization_id, "company_id": company.id, "account_id": actor.id,
    }


async def _call(fn, **params):
    try:
        return await asyncio.to_thread(fn, **params)
    except PresetPermissionError:
        raise HTTPException(403, "Saved filter access denied.") from None
    except PresetMissingError:
        raise HTTPException(404, "Saved filter not found.") from None
    except PresetLimitError:
        raise HTTPException(409, "Maximum 20 saved filters per company.") from None
    except ValueError:
        raise HTTPException(422, "Saved filter payload is invalid.") from None
    except StorageError:
        raise HTTPException(503, "Saved filter storage unavailable.") from None


def response(data):
    return JSONResponse(data, headers={"Cache-Control": "private, no-store"})


@router.get("")
async def list_presets(organization_id: int, request: Request):
    service, scope = await _context(organization_id, request)
    return response(await _call(service.list, **scope))


@router.post("")
async def save_preset(organization_id: int, payload: SavePreset, request: Request):
    require_same_origin_browser_request(request)
    service, scope = await _context(organization_id, request)
    return response(await _call(service.save, **scope, name=payload.name,
                                filters=payload.filters.model_dump()))


@router.delete("/{preset_id}")
async def delete_preset(organization_id: int, preset_id: int, request: Request):
    require_same_origin_browser_request(request)
    if preset_id <= 0:
        raise HTTPException(422, "Invalid saved filter ID.")
    service, scope = await _context(organization_id, request)
    await _call(service.delete, **scope, preset_id=preset_id)
    return response({"deleted": True})
