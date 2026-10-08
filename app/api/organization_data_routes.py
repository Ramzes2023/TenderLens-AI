"""Organization-scoped tender history boundaries."""

from __future__ import annotations

import asyncio
import hashlib
from typing import Annotated

from fastapi import (
    APIRouter,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel, ConfigDict, Field

from app.companies import (
    CompanyAuthorizationError,
    CompanyRepositoryError,
)
from app.database import (
    DatabaseAuthorizationError,
    DatabaseError,
)
from app.llm.base import LLMError
from app.models.tender import TenderAnalysis
from app.organizations import OrganizationError
from app.parsers.pdf import MAX_BYTES
from app.jobs import JobScope, JobValueError
from app.rag.documents import DocumentError
from app.rag.ingestion import pipeline_identity, vector_scope
from app.rag import (
    QdrantStoreError,
    RagError,
)
from app.scoring.engine import score_tender
from app.scoring.models import ScoringResult
from app.services.pdf import summarize_pdf
from app.services.tender_analysis import (
    AnalysisError,
    analyze_tender,
)

from .schemas import (
    PdfAnalysisResponse,
    RagAskResponse,
    RagSource,
    TenderListItem,
)
from .security import (
    current_account,
    require_same_origin_browser_request,
)


router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}",
    tags=["organization-data"],
)


class IngestionAskRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    question: Annotated[str, Field(min_length=1, max_length=2000)]


async def _ingestion_scope(request, organization_id, company_id, *, write=False):
    account = await _account(request)
    try:
        await asyncio.to_thread(_organization_service(request).require_membership, account, organization_id,
                                {'owner', 'admin', 'member'} if write else {'owner', 'admin', 'member', 'viewer'})
        if company_id is not None:
            workspace = await asyncio.to_thread(_company_service(request).get_for_organization,
                                                account.id, organization_id, company_id)
            if workspace is None:
                raise HTTPException(404, 'Company not found.')
    except (OrganizationError, CompanyAuthorizationError):
        raise HTTPException(403, 'Organization access denied.') from None
    except CompanyRepositoryError:
        raise HTTPException(503, 'Company storage unavailable.') from None
    return JobScope(account.id, organization_id, company_id)


def _ingestion(request):
    service = _runtime(request).rag_ingestion_service
    if service is None:
        raise HTTPException(503, 'RAG ingestion unavailable.')
    return service


async def _ingestion_job(service, job_id, scope):
    try:
        job = await asyncio.to_thread(service.get, job_id, scope=scope)
    except Exception:
        raise HTTPException(503, 'RAG job storage unavailable.') from None
    if job is None:
        raise HTTPException(404, 'RAG job not found.')
    return job


@router.post('/rag/documents', status_code=202)
@router.post('/companies/{company_id}/rag/documents', status_code=202)
async def enqueue_rag_document(organization_id: int, request: Request, response: Response,
                               file: UploadFile = File(...), company_id: int | None = None):
    require_same_origin_browser_request(request)
    scope = await _ingestion_scope(request, organization_id, company_id, write=True)
    service = _ingestion(request)
    try:
        data = await file.read(MAX_BYTES + 1)
    finally:
        await file.close()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, 'PDF exceeds 10 MiB limit.')
    try:
        job = await asyncio.to_thread(service.stage_and_enqueue, data, scope=scope)
    except DocumentError:
        raise HTTPException(422, 'Invalid PDF staging request.') from None
    except JobValueError:
        raise HTTPException(403, 'Ingestion scope unavailable.') from None
    except Exception:
        raise HTTPException(503, 'RAG ingestion unavailable.') from None
    await _ingestion_scope(request, organization_id, company_id, write=True)
    response.headers['Cache-Control'] = 'no-store'
    return service.public_status(job)


@router.get('/rag/jobs/{job_id}')
@router.get('/companies/{company_id}/rag/jobs/{job_id}')
async def rag_job_status(organization_id: int, job_id: str, request: Request, response: Response,
                         company_id: int | None = None):
    scope = await _ingestion_scope(request, organization_id, company_id)
    service = _ingestion(request)
    job = await _ingestion_job(service, job_id, scope)
    await _ingestion_scope(request, organization_id, company_id)
    response.headers['Cache-Control'] = 'no-store'
    return service.public_status(job)


@router.post('/rag/jobs/{job_id}/ask', response_model=RagAskResponse)
@router.post('/companies/{company_id}/rag/jobs/{job_id}/ask', response_model=RagAskResponse)
async def ask_ingested_document(organization_id: int, job_id: str, payload: IngestionAskRequest,
                                request: Request, response: Response, company_id: int | None = None):
    require_same_origin_browser_request(request)
    scope = await _ingestion_scope(request, organization_id, company_id)
    job = await _ingestion_job(_ingestion(request), job_id, scope)
    if job.state != 'succeeded':
        raise HTTPException(409, 'Document is not ready.')
    runtime = _runtime(request)
    if runtime.rag_service is None or runtime.provider is None:
        raise HTTPException(503, 'RAG answering unavailable.')
    if job.payload['pipeline_version'] != pipeline_identity(runtime.rag_service.settings):
        raise HTTPException(409, 'Document requires ingestion with the current pipeline.')
    try:
        answer = await runtime.rag_service.answer(0, job.payload['sha256'], payload.question, runtime.provider,
                                                ingestion_scope=vector_scope(scope),
                                                pipeline_version=job.payload['pipeline_version'])
    except LLMError:
        raise HTTPException(502, 'AI generation unavailable.') from None
    except (RagError, QdrantStoreError):
        raise HTTPException(503, 'RAG answering unavailable.') from None
    await _ingestion_scope(request, organization_id, company_id)
    response.headers['Cache-Control'] = 'no-store'
    return RagAskResponse(answer=answer.answer,
                          sources=[RagSource(page_number=item.page_number, chunk_index=item.chunk_index,
                                             score=item.score) for item in answer.sources])


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


class OrganizationRagAskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pdf_sha256: Annotated[
        str,
        Field(pattern=r"^[0-9a-fA-F]{64}$"),
    ]
    question: Annotated[
        str,
        Field(min_length=1, max_length=2000),
    ]


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


def _runtime(request: Request):
    return request.app.state.runtime


def _organization_service(request: Request):
    service = getattr(
        _runtime(request),
        "organization_service",
        None,
    )

    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Organizations are unavailable.",
        )

    return service


def _company_service(request: Request):
    service = getattr(
        _runtime(request),
        "company_service",
        None,
    )

    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Company workspaces are unavailable.",
        )

    return service


async def _require_write_membership(
    request: Request,
    account,
    organization_id: int,
):
    service = _organization_service(request)

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
            detail="Organization write access denied.",
        ) from None


async def _active_company(
    request: Request,
    account,
    organization_id: int,
):
    service = _company_service(request)

    try:
        workspace = await asyncio.to_thread(
            service.active_for_organization,
            account.id,
            organization_id,
        )
    except CompanyAuthorizationError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization access denied.",
        ) from None
    except CompanyRepositoryError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Company storage is unavailable.",
        ) from None

    return workspace


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

@router.post(
    "/analysis/pdf",
    response_model=PdfAnalysisResponse,
)
async def analyze_organization_pdf(
    organization_id: int,
    request: Request,
    response: Response,
    file: UploadFile = File(...),
):
    require_same_origin_browser_request(request)

    account = await _account(request)

    await _require_write_membership(
        request,
        account,
        organization_id,
    )

    workspace = await _active_company(
        request,
        account,
        organization_id,
    )

    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Create an organization company profile "
                "before analyzing PDFs."
            ),
        )

    runtime = _runtime(request)
    repository = _repository(request)

    name = (
        file.filename
        or "document.pdf"
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

    digest = hashlib.sha256(
        data
    ).hexdigest()

    try:
        existing = await asyncio.to_thread(
            repository.find_by_hash_for_organization,
            account.id,
            organization_id,
            digest,
        )
    except DatabaseError as error:
        _data_error(error)

    if existing is not None:
        duplicate_scoring = score_tender(
            existing.analysis,
            workspace.profile,
        )

        response.headers[
            "Cache-Control"
        ] = "no-store"

        return PdfAnalysisResponse(
            duplicate=True,
            record_id=existing.id,
            pdf_sha256=existing.pdf_sha256,
            source_filename=existing.source_filename,
            pages=existing.pages,
            characters=existing.characters,
            analysis_truncated=existing.analysis_truncated,
            analysis=existing.analysis,
            scoring=duplicate_scoring,
            rag_indexed_chunks=None,
            warnings=[
                (
                    "Duplicate PDF: stored organization analysis "
                    "reused; LLM was not called. Scoring uses the "
                    "shared active company profile."
                )
            ],
        )

    if runtime.provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM is unavailable.",
        )

    summary = await summarize_pdf(data)

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
        result = await analyze_tender(
            summary.text,
            runtime.provider,
            runtime.tender_max_chars,
        )
    except AnalysisError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from None
    except LLMError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="LLM request failed.",
        ) from None

    # The active company may have changed during the expensive
    # PDF/LLM operation, so resolve the shared context again.
    workspace = await _active_company(
        request,
        account,
        organization_id,
    )

    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Create an organization company profile "
                "before analyzing PDFs."
            ),
        )

    scoring = score_tender(
        result.analysis,
        workspace.profile,
    )

    # Save FIRST. This method re-checks write membership inside
    # BEGIN IMMEDIATE. Qdrant must not receive the PDF text when
    # the final organization authorization fails.
    try:
        stored = await asyncio.to_thread(
            repository.save_success_for_organization,
            account_id=account.id,
            organization_id=organization_id,
            pdf_sha256=digest,
            source_filename=name,
            pages=summary.pages,
            characters=summary.characters,
            analysis=result.analysis,
            scoring=scoring,
            analysis_truncated=result.truncated,
        )
    except DatabaseError as error:
        _data_error(error)

    warnings: list[str] = []
    rag_chunks: int | None = None

    if runtime.rag_service is not None:
        try:
            rag_chunks = await asyncio.to_thread(
                runtime.rag_service.index_pdf_for_organization,
                organization_id,
                digest,
                summary,
            )
        except Exception:
            warnings.append(
                "Organization RAG indexing failed; "
                "analysis was still completed."
            )

    # RAG embedding/indexing can be relatively expensive.
    # Re-check organization read authorization before returning
    # potentially sensitive analysis to the caller.
    try:
        confirmed = await asyncio.to_thread(
            repository.find_by_hash_for_organization,
            account.id,
            organization_id,
            digest,
        )
    except DatabaseError as error:
        _data_error(error)

    if confirmed is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tender document not found.",
        )

    response.headers[
        "Cache-Control"
    ] = "no-store"

    return PdfAnalysisResponse(
        duplicate=False,
        record_id=stored.id,
        pdf_sha256=digest,
        source_filename=name,
        pages=summary.pages,
        characters=summary.characters,
        analysis_truncated=result.truncated,
        analysis=result.analysis,
        scoring=scoring,
        rag_indexed_chunks=rag_chunks,
        warnings=warnings,
    )


@router.post(
    "/rag/ask",
    response_model=RagAskResponse,
)
async def ask_organization_rag(
    organization_id: int,
    payload: OrganizationRagAskRequest,
    request: Request,
    response: Response,
):
    require_same_origin_browser_request(request)

    account = await _account(request)
    runtime = _runtime(request)
    repository = _repository(request)

    digest = payload.pdf_sha256.lower()

    try:
        record = await asyncio.to_thread(
            repository.find_by_hash_for_organization,
            account.id,
            organization_id,
            digest,
        )
    except DatabaseError as error:
        _data_error(error)

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tender document not found.",
        )

    if runtime.rag_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RAG is unavailable.",
        )

    if runtime.provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM is unavailable.",
        )

    try:
        answer = await runtime.rag_service.answer_for_organization(
            organization_id,
            digest,
            payload.question,
            runtime.provider,
        )
    except LLMError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="LLM request failed.",
        ) from None
    except QdrantStoreError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RAG storage is unavailable.",
        ) from None
    except RagError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from None
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="RAG request failed.",
        ) from None

    # Do not return potentially sensitive generated content if
    # membership was revoked during the external RAG/LLM call.
    try:
        confirmed = await asyncio.to_thread(
            repository.find_by_hash_for_organization,
            account.id,
            organization_id,
            digest,
        )
    except DatabaseError as error:
        _data_error(error)

    if confirmed is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tender document not found.",
        )

    response.headers[
        "Cache-Control"
    ] = "no-store"

    return RagAskResponse(
        answer=answer.answer,
        sources=[
            RagSource(
                page_number=item.page_number,
                chunk_index=item.chunk_index,
                score=item.score,
            )
            for item in answer.sources
        ],
    )
