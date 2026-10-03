"""Organization-scoped tender history boundaries."""

from __future__ import annotations

import asyncio

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from pydantic import BaseModel

from app.database import (
    DatabaseAuthorizationError,
    DatabaseError,
)
from app.models.tender import TenderAnalysis
from app.scoring.models import ScoringResult

from .schemas import TenderListItem
from .security import current_account


router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}",
    tags=["organization-data"],
)


class OrganizationTenderDetail(BaseModel):
    id: int
    source_filename: str
    pdf_sha256: str
    pages: int | None
    characters: int
    analysis_truncated: bool
    analysis: TenderAnalysis
    scoring: ScoringResult | None
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


def _repository(request: Request):
    repository = getattr(
        request.app.state.runtime,
        "tender_repository",
        None,
    )

    if repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        )

    return repository


def _list_item(record):
    return TenderListItem(
        id=record.id,
        source_filename=record.source_filename,
        pdf_sha256=record.pdf_sha256,
        pages=record.pages,
        title=record.analysis.title,
        tender_number=record.analysis.tender_number,
        customer=record.analysis.customer,
        initial_price=record.analysis.initial_price,
        currency=record.analysis.currency,
        fit_score=(
            record.scoring.fit_score
            if record.scoring is not None
            else None
        ),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _detail(record):
    return OrganizationTenderDetail(
        id=record.id,
        source_filename=record.source_filename,
        pdf_sha256=record.pdf_sha256,
        pages=record.pages,
        characters=record.characters,
        analysis_truncated=record.analysis_truncated,
        analysis=record.analysis,
        scoring=record.scoring,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _data_error(error):
    if isinstance(
        error,
        DatabaseAuthorizationError,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization tender access denied.",
        ) from None

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Organization tender storage is unavailable.",
    ) from None


@router.get(
    "/tenders",
    response_model=list[TenderListItem],
)
async def list_organization_tenders(
    organization_id: int,
    request: Request,
    response: Response,
    limit: int = Query(
        default=10,
        ge=1,
        le=20,
    ),
):
    account = await _account(request)
    repository = _repository(request)

    try:
        records = await asyncio.to_thread(
            repository.list_recent_for_organization,
            account.id,
            organization_id,
            limit,
        )
    except DatabaseError as error:
        _data_error(error)

    response.headers["Cache-Control"] = "no-store"

    return [
        _list_item(record)
        for record in records
    ]


@router.get(
    "/tenders/{tender_id}",
    response_model=OrganizationTenderDetail,
)
async def get_organization_tender(
    organization_id: int,
    tender_id: int,
    request: Request,
    response: Response,
):
    if tender_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="tender_id must be positive.",
        )

    account = await _account(request)
    repository = _repository(request)

    try:
        record = await asyncio.to_thread(
            repository.find_by_id_for_organization,
            account.id,
            organization_id,
            tender_id,
        )
    except DatabaseError as error:
        _data_error(error)

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tender not found.",
        )

    response.headers["Cache-Control"] = "no-store"

    return _detail(record)
