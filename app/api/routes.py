"""FastAPI routes exposing TenderLens services without Telegram."""
from __future__ import annotations

import asyncio
import hashlib

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.security import APIKeyHeader

from app import __version__

from app.database import DatabaseError
from app.llm.base import LLMError
from app.models.tender import TenderAnalysis
from app.parsers.pdf import MAX_BYTES
from app.scoring.engine import score_tender
from app.scoring.models import ScoringResult
from app.services.pdf import summarize_pdf
from app.services.tender_analysis import AnalysisError, analyze_tender

from .runtime import ApiRuntime
from .schemas import (
    HealthResponse,
    MonitorNoticeResponse,
    MonitorScanRequest,
    MonitorStatusResponse,
    PdfAnalysisResponse,
    RagAskRequest,
    RagAskResponse,
    RagSource,
    TenderDetail,
    TenderListItem,
)
from .security import require_api_key

router = APIRouter()
api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)


def _runtime(request: Request) -> ApiRuntime:
    return request.app.state.runtime


async def _protected(request: Request, key: str | None = Depends(api_key_scheme)) -> None:
    await require_api_key(request, key)


def _list_item(record) -> TenderListItem:
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
        fit_score=record.scoring.fit_score if record.scoring is not None else None,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _detail(record) -> TenderDetail:
    return TenderDetail(
        id=record.id,
        owner_user_id=record.owner_user_id,
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


@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health(request: Request) -> HealthResponse:
    runtime = _runtime(request)
    components = runtime.component_status()
    critical = (components["database"], components["scoring"])
    overall = "ok" if all(value == "ready" for value in critical) else "degraded"
    return HealthResponse(
        status=overall,
        service="TenderLens AI",
        version=__version__,
        components=components,
    )


@router.get(
    "/api/v1/tenders",
    response_model=list[TenderListItem],
    tags=["history"],
    dependencies=[Depends(_protected)],
)
async def list_tenders(
    request: Request,
    owner_user_id: int = Query(gt=0),
    limit: int = Query(10, ge=1, le=20),
) -> list[TenderListItem]:
    repository = _runtime(request).tender_repository
    if repository is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database is unavailable.")
    try:
        records = await asyncio.to_thread(repository.list_recent, owner_user_id, limit)
    except DatabaseError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from None
    return [_list_item(record) for record in records]


@router.get(
    "/api/v1/tenders/{tender_id}",
    response_model=TenderDetail,
    tags=["history"],
    dependencies=[Depends(_protected)],
)
async def get_tender(
    tender_id: int,
    request: Request,
    owner_user_id: int = Query(gt=0),
) -> TenderDetail:
    if tender_id <= 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "tender_id must be positive.")
    repository = _runtime(request).tender_repository
    if repository is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database is unavailable.")
    try:
        record = await asyncio.to_thread(repository.find_by_id, owner_user_id, tender_id)
    except DatabaseError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from None
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tender not found.")
    return _detail(record)


@router.post(
    "/api/v1/scoring/evaluate",
    response_model=ScoringResult,
    tags=["scoring"],
    dependencies=[Depends(_protected)],
)
async def evaluate_score(analysis: TenderAnalysis, request: Request) -> ScoringResult:
    profile = _runtime(request).company_profile
    if profile is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Company profile is unavailable.")
    return score_tender(analysis, profile)


@router.post(
    "/api/v1/rag/ask",
    response_model=RagAskResponse,
    tags=["rag"],
    dependencies=[Depends(_protected)],
)
async def rag_ask(payload: RagAskRequest, request: Request) -> RagAskResponse:
    runtime = _runtime(request)
    if runtime.rag_service is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "RAG is unavailable.")
    if runtime.provider is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "LLM is unavailable.")
    try:
        answer = await runtime.rag_service.answer(
            payload.owner_user_id,
            payload.pdf_sha256.lower(),
            payload.question,
            runtime.provider,
        )
    except LLMError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "LLM request failed.") from None
    except Exception:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "RAG request failed.") from None
    return RagAskResponse(
        answer=answer.answer,
        sources=[
            RagSource(page_number=item.page_number, chunk_index=item.chunk_index, score=item.score)
            for item in answer.sources
        ],
    )


@router.get(
    "/api/v1/monitoring/status",
    response_model=MonitorStatusResponse,
    tags=["monitoring"],
    dependencies=[Depends(_protected)],
)
async def monitoring_status(
    request: Request,
    owner_user_id: int = Query(gt=0),
) -> MonitorStatusResponse:
    service = _runtime(request).monitoring_service
    if service is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Monitoring is unavailable.")
    subscription = await service.subscription(owner_user_id)
    return MonitorStatusResponse(
        background_enabled=service.settings.enabled,
        interval_seconds=service.settings.interval_seconds,
        rss_feeds=len(service.settings.eis_rss_urls),
        subscription_enabled=bool(subscription and subscription.enabled),
    )


@router.post(
    "/api/v1/monitoring/scan",
    response_model=list[MonitorNoticeResponse],
    tags=["monitoring"],
    dependencies=[Depends(_protected)],
)
async def monitoring_scan(payload: MonitorScanRequest, request: Request) -> list[MonitorNoticeResponse]:
    service = _runtime(request).monitoring_service
    if service is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Monitoring is unavailable.")
    try:
        matches = await service.scan_new(payload.owner_user_id)
    except Exception:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "EIS monitoring request failed.") from None
    return [
        MonitorNoticeResponse(
            source=match.notice.source,
            external_id=match.notice.external_id,
            title=match.notice.title,
            url=match.notice.url,
            tender_number=match.notice.tender_number,
            customer=match.notice.customer,
            initial_price=match.notice.initial_price,
            currency=match.notice.currency,
            deadline=match.notice.deadline,
            region=match.notice.region,
            reasons=list(match.reasons),
        )
        for match in matches
    ]


@router.post(
    "/api/v1/analysis/pdf",
    response_model=PdfAnalysisResponse,
    tags=["analysis"],
    dependencies=[Depends(_protected)],
)
async def analyze_pdf_endpoint(
    request: Request,
    owner_user_id: int = Form(gt=0),
    file: UploadFile = File(...),
) -> PdfAnalysisResponse:
    runtime = _runtime(request)
    if runtime.tender_repository is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database is unavailable.")
    if runtime.provider is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "LLM is unavailable.")

    name = (file.filename or "document.pdf")[:200]
    content_type = (file.content_type or "").lower()
    if content_type != "application/pdf" and not name.lower().endswith(".pdf"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only PDF files are supported.")
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "PDF exceeds 10 MiB limit.")
    digest = hashlib.sha256(data).hexdigest()

    try:
        existing = await asyncio.to_thread(runtime.tender_repository.find_by_hash, owner_user_id, digest)
    except DatabaseError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from None
    if existing is not None:
        return PdfAnalysisResponse(
            duplicate=True,
            record_id=existing.id,
            pdf_sha256=existing.pdf_sha256,
            source_filename=existing.source_filename,
            pages=existing.pages,
            characters=existing.characters,
            analysis_truncated=existing.analysis_truncated,
            analysis=existing.analysis,
            scoring=existing.scoring,
            rag_indexed_chunks=None,
            warnings=["Duplicate PDF: stored analysis reused; LLM was not called."],
        )

    summary = await summarize_pdf(data)
    if summary.status != "ok":
        messages = {
            "no_text": "PDF has no extractable text; OCR is not enabled.",
            "encrypted": "PDF is password protected.",
            "invalid": "Invalid or damaged PDF.",
            "too_large": "PDF exceeds 10 MiB limit.",
            "too_many_pages": "PDF exceeds 200 page limit.",
            "too_much_text": "PDF exceeds extracted text limit.",
            "timeout": "PDF parsing timed out.",
        }
        code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE if summary.status == "too_large" else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(code, messages.get(summary.status, "PDF parsing failed."))

    try:
        result = await analyze_tender(summary.text, runtime.provider, runtime.tender_max_chars)
    except AnalysisError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from None
    except LLMError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "LLM request failed.") from None

    scoring = score_tender(result.analysis, runtime.company_profile) if runtime.company_profile else None
    warnings: list[str] = []
    rag_chunks: int | None = None
    if runtime.rag_service is not None:
        try:
            rag_chunks = await asyncio.to_thread(
                runtime.rag_service.index_pdf, owner_user_id, digest, summary
            )
        except Exception:
            warnings.append("RAG indexing failed; analysis was still completed.")

    try:
        stored = await asyncio.to_thread(
            runtime.tender_repository.save_success,
            owner_user_id=owner_user_id,
            chat_id=owner_user_id,
            pdf_sha256=digest,
            source_filename=name,
            pages=summary.pages,
            characters=summary.characters,
            analysis=result.analysis,
            scoring=scoring,
            analysis_truncated=result.truncated,
        )
    except DatabaseError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from None

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
