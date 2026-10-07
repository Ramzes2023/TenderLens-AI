"""Organization-scoped shared company workspace HTTP API."""

from __future__ import annotations

import asyncio

from fastapi import (
    APIRouter,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel, ConfigDict, Field

from app.companies import (
    CompanyAuthorizationError,
    CompanyNotFoundError,
    CompanyRepositoryError,
)
from app.llm.base import LLMError
from app.organizations import OrganizationError
from app.parsers.pdf import MAX_BYTES
from app.scoring.models import CompanyProfile
from app.services.company_profile_analysis import (
    CompanySearchProfileDraft,
    ProfileDraftError,
    analyze_company_search_profile,
    merge_company_profile_draft,
)
from app.services.pdf import summarize_pdf

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
    is_active: bool
    created_at: str
    updated_at: str


class CompanyProfilePdfPreviewResponse(BaseModel):
    company_id: int
    source_filename: str
    pages: int | None
    characters: int
    analysis_truncated: bool
    draft: CompanySearchProfileDraft
    current_profile: CompanyProfile
    suggested_profile: CompanyProfile
    warnings: list[str] = Field(default_factory=list)


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


def _organization_service(request: Request):
    service = getattr(
        request.app.state.runtime,
        "organization_service",
        None,
    )

    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Organization service is unavailable.",
        )

    return service


async def _require_profile_generation_access(
    request: Request,
    account,
    organization_id: int,
):
    service = _organization_service(
        request
    )

    try:
        await asyncio.to_thread(
            service.require_membership,
            account,
            organization_id,
            {
                "owner",
                "admin",
                "member",
            },
        )

    except OrganizationError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Company profile generation access denied.",
        ) from None


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
        is_active=workspace.is_active,
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
    "/active",
    response_model=OrganizationCompanyResponse | None,
)
async def active_company(
    organization_id: int,
    request: Request,
    response: Response,
):
    account = await _account(request)
    service = _service(request)

    try:
        company = await asyncio.to_thread(
            service.active_for_organization,
            account.id,
            organization_id,
        )
    except CompanyRepositoryError as error:
        _company_error(error)

    response.headers["Cache-Control"] = "no-store"

    return (
        _response(company)
        if company is not None
        else None
    )


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


@router.post(
    "/{company_id}/activate",
    response_model=OrganizationCompanyResponse,
)
async def activate_company(
    organization_id: int,
    company_id: int,
    request: Request,
    response: Response,
):
    require_same_origin_browser_request(request)

    account = await _account(request)
    service = _service(request)

    try:
        company = await asyncio.to_thread(
            service.set_active_for_organization,
            account.id,
            organization_id,
            company_id,
        )
    except CompanyRepositoryError as error:
        _company_error(error)

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


@router.post(
    "/{company_id}/profile-from-pdf/preview",
    response_model=CompanyProfilePdfPreviewResponse,
)
async def preview_company_profile_from_pdf(
    organization_id: int,
    company_id: int,
    request: Request,
    response: Response,
    file: UploadFile = File(...),
):
    require_same_origin_browser_request(
        request
    )

    if (
        organization_id <= 0
        or company_id <= 0
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "organization_id and company_id must be positive."
            ),
        )

    account = await _account(
        request
    )

    await _require_profile_generation_access(
        request,
        account,
        organization_id,
    )

    service = _service(
        request
    )

    try:
        company = await asyncio.to_thread(
            service.get_for_organization,
            account.id,
            organization_id,
            company_id,
        )

    except CompanyRepositoryError as error:
        _company_error(
            error
        )

    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found.",
        )

    name = (
        file.filename
        or "company-profile.pdf"
    )[:200]

    content_type = (
        file.content_type
        or ""
    ).lower()

    if (
        content_type != "application/pdf"
        and not name.lower().endswith(".pdf")
    ):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF files are supported.",
        )

    data = await file.read(
        MAX_BYTES + 1
    )

    if len(data) > MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="PDF exceeds 10 MiB limit.",
        )

    runtime = request.app.state.runtime

    if runtime.provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM is unavailable.",
        )

    summary = await summarize_pdf(
        data
    )

    if summary.status != "ok":
        messages = {
            "no_text":
                "PDF has no extractable text; OCR is not enabled.",
            "encrypted":
                "PDF is password protected.",
            "invalid":
                "Invalid or damaged PDF.",
            "too_large":
                "PDF exceeds 10 MiB limit.",
            "too_many_pages":
                "PDF exceeds 200 page limit.",
            "too_much_text":
                "PDF exceeds extracted text limit.",
            "timeout":
                "PDF parsing timed out.",
        }

        code = (
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
            if summary.status == "too_large"
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )

        raise HTTPException(
            status_code=code,
            detail=messages.get(
                summary.status,
                "PDF parsing failed.",
            ),
        )

    try:
        result = await analyze_company_search_profile(
            summary.text,
            runtime.provider,
            runtime.tender_max_chars,
        )

    except ProfileDraftError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from None

    except LLMError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="LLM request failed.",
        ) from None

    # Re-check authorization and reload after the
    # potentially expensive PDF/LLM operation.
    await _require_profile_generation_access(
        request,
        account,
        organization_id,
    )

    try:
        current = await asyncio.to_thread(
            service.get_for_organization,
            account.id,
            organization_id,
            company_id,
        )

    except CompanyRepositoryError as error:
        _company_error(
            error
        )

    if current is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found.",
        )

    suggested = (
        merge_company_profile_draft(
            current.profile,
            result.draft,
        )
    )

    warnings = []

    if result.truncated:
        warnings.append(
            "Only the bounded beginning of the extracted "
            "document text was sent for AI analysis."
        )

    response.headers["Cache-Control"] = "no-store"

    return CompanyProfilePdfPreviewResponse(
        company_id=current.id,
        source_filename=name,
        pages=summary.pages,
        characters=summary.characters,
        analysis_truncated=result.truncated,
        draft=result.draft,
        current_profile=current.profile,
        suggested_profile=suggested,
        warnings=warnings,
    )


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
