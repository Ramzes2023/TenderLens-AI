"""Organization-scoped shared company workspace HTTP API."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.companies import (
    CompanyAuthorizationError,
    CompanyNotFoundError,
    CompanyRepositoryError,
)
from app.scoring.models import CompanyProfile

from .security import current_account, require_same_origin_browser_request


router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}/companies",
    tags=["organization-companies"],
)


class OrganizationCompanyCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    profile: CompanyProfile


class OrganizationCompanyUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    profile: CompanyProfile | None = None


class OrganizationCompanyResponse(BaseModel):
    id: int
    organization_id: int
    name: str
    profile: CompanyProfile
    created_at: str
    updated_at: str


async def _account(request: Request):
    account = await current_account(request)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    return account


def _service(request: Request):
    service = getattr(
        request.app.state.runtime,
        "company_service",
        None,
    )
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Company workspaces are unavailable.",
        )
    return service


def _response(workspace):
    if workspace.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Organization company scope is unavailable.",
        )

    return OrganizationCompanyResponse(
        id=workspace.id,
        organization_id=workspace.organization_id,
        name=workspace.name,
        profile=workspace.profile,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
    )


def _company_error(error):
    if isinstance(error, CompanyAuthorizationError):
        code = status.HTTP_403_FORBIDDEN
    elif isinstance(error, CompanyNotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif "already exists" in str(error).lower():
        code = status.HTTP_409_CONFLICT
    elif "unavailable" in str(error).lower():
        code = status.HTTP_503_SERVICE_UNAVAILABLE
    else:
        code = status.HTTP_422_UNPROCESSABLE_CONTENT

    raise HTTPException(
        status_code=code,
        detail=str(error),
    ) from None


@router.get(
    "",
    response_model=list[OrganizationCompanyResponse],
)
async def list_companies(
    organization_id: int,
    request: Request,
    response: Response,
):
    if organization_id <= 0:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "organization_id must be positive.",
        )

    account = await _account(request)
    service = _service(request)

    try:
        companies = await asyncio.to_thread(
            service.list_for_organization,
            account.id,
            organization_id,
        )
    except CompanyRepositoryError as error:
        _company_error(error)

    response.headers["Cache-Control"] = "no-store"

    return [
        _response(company)
        for company in companies
    ]


@router.post(
    "",
    response_model=OrganizationCompanyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_company(
    organization_id: int,
    payload: OrganizationCompanyCreateRequest,
    request: Request,
    response: Response,
):
    require_same_origin_browser_request(request)

    account = await _account(request)
    service = _service(request)

    try:
        company = await asyncio.to_thread(
            service.create_for_organization,
            account,
            organization_id,
            payload.name,
            payload.profile,
        )
    except CompanyRepositoryError as error:
        _company_error(error)

    response.headers["Cache-Control"] = "no-store"
    return _response(company)


@router.get(
    "/{company_id}",
    response_model=OrganizationCompanyResponse,
)
async def get_company(
    organization_id: int,
    company_id: int,
    request: Request,
    response: Response,
):
    if organization_id <= 0 or company_id <= 0:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "organization_id and company_id must be positive.",
        )

    account = await _account(request)
    service = _service(request)

    try:
        company = await asyncio.to_thread(
            service.get_for_organization,
            account.id,
            organization_id,
            company_id,
        )
    except CompanyRepositoryError as error:
        _company_error(error)

    if company is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Company not found.",
        )

    response.headers["Cache-Control"] = "no-store"
    return _response(company)


@router.patch(
    "/{company_id}",
    response_model=OrganizationCompanyResponse,
)
async def update_company(
    organization_id: int,
    company_id: int,
    payload: OrganizationCompanyUpdateRequest,
    request: Request,
    response: Response,
):
    require_same_origin_browser_request(request)

    if payload.name is None and payload.profile is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "At least one company field must be supplied.",
        )

    account = await _account(request)
    service = _service(request)

    try:
        company = await asyncio.to_thread(
            service.update_for_organization,
            account.id,
            organization_id,
            company_id,
            profile=payload.profile,
            name=payload.name,
        )
    except CompanyRepositoryError as error:
        _company_error(error)

    response.headers["Cache-Control"] = "no-store"
    return _response(company)


@router.delete(
    "/{company_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_company(
    organization_id: int,
    company_id: int,
    request: Request,
    response: Response,
):
    require_same_origin_browser_request(request)

    account = await _account(request)
    service = _service(request)

    try:
        await asyncio.to_thread(
            service.delete_for_organization,
            account.id,
            organization_id,
            company_id,
        )
    except CompanyRepositoryError as error:
        _company_error(error)

    response.headers["Cache-Control"] = "no-store"
    return None
