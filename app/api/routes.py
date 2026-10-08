"""FastAPI routes exposing VALYQON AI services without Telegram."""
from __future__ import annotations

from .landing import landing_html

import asyncio
import hashlib

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
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

from .auth_pages import (
    login_html,
    register_html,
    verify_email_html,
)
from .dashboard import dashboard_html
from .invitation_page import invitation_page_html
from .runtime import ApiRuntime
from .schemas import (
    CompanyActivateRequest,
    CompanyCreateRequest,
    CompanyResponse,
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
from .security import current_account, require_api_or_session, resolve_owner

router = APIRouter()
api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)


def _safe_next_path(
    value: str | None,
) -> str:
    value = (
        value
        or ""
    ).strip()

    if (
        value == "/dashboard"
        or value.startswith("/invite/")
    ):
        return value

    return "/dashboard"


def _runtime(request: Request) -> ApiRuntime:
    return request.app.state.runtime


async def _protected(request: Request, key: str | None = Depends(api_key_scheme)) -> None:
    await require_api_or_session(request, key)


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




def _company_response(workspace) -> CompanyResponse:
    return CompanyResponse(
        id=workspace.id,
        owner_user_id=workspace.owner_user_id,
        name=workspace.name,
        profile=workspace.profile,
        is_active=workspace.is_active,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
    )


@router.get("/", include_in_schema=False)
async def root_page(request: Request):
    account = await current_account(request, touch=False)
    return HTMLResponse(landing_html(account is not None), headers={"Cache-Control": "no-store"})


@router.get(
    "/login",
    response_class=HTMLResponse,
    include_in_schema=False,
)
async def login_page(
    request: Request,
    next_path: str | None = Query(
        default=None,
        alias="next",
    ),
):
    target = _safe_next_path(
        next_path
    )

    if await current_account(
        request,
        touch=False,
    ) is not None:
        return RedirectResponse(
            target,
            status_code=303,
        )

    return HTMLResponse(
        login_html(target),
        headers={
            "Cache-Control":
                "no-store",
            "Referrer-Policy":
                "no-referrer",
        },
    )


@router.get(
    "/register",
    response_class=HTMLResponse,
    include_in_schema=False,
)
async def register_page(
    request: Request,
    next_path: str | None = Query(
        default=None,
        alias="next",
    ),
):
    target = _safe_next_path(
        next_path
    )

    if await current_account(
        request,
        touch=False,
    ) is not None:
        return RedirectResponse(
            target,
            status_code=303,
        )

    return HTMLResponse(
        register_html(target),
        headers={
            "Cache-Control":
                "no-store",
            "Referrer-Policy":
                "no-referrer",
        },
    )


@router.get(
    "/verify-email",
    response_class=HTMLResponse,
    include_in_schema=False,
)
async def verify_email_page(
    request: Request,
    token: str | None = Query(
        default=None,
    ),
    email: str | None = Query(
        default=None,
    ),
    sent: str | None = Query(
        default=None,
    ),
    next_path: str | None = Query(
        default=None,
        alias="next",
    ),
):
    target = _safe_next_path(
        next_path
    )

    account = await current_account(
        request,
        touch=False,
    )

    if (
        account is not None
        and account.email_verified
    ):
        return RedirectResponse(
            target,
            status_code=303,
        )

    sent_value = (
        True
        if sent == "1"
        else (
            False
            if sent == "0"
            else None
        )
    )

    return HTMLResponse(
        verify_email_html(
            token=token,
            email=email,
            next_path=target,
            sent=sent_value,
        ),
        headers={
            "Cache-Control":
                "no-store",
            "Referrer-Policy":
                "no-referrer",
        },
    )


@router.get(
    "/invite/{token}",
    response_class=HTMLResponse,
    include_in_schema=False,
)
async def invitation_page(
    token: str,
):
    return HTMLResponse(
        invitation_page_html(
            token
        ),
        headers={
            "Cache-Control":
                "no-store",
            "Referrer-Policy":
                "no-referrer",
        },
    )


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def dashboard(request: Request):
    """Serve the authenticated VALYQON AI web workspace."""
    if await current_account(request, touch=False) is None:
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(dashboard_html(), headers={"Cache-Control": "no-store"})


@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health(request: Request) -> HealthResponse:
    runtime = _runtime(request)
    components = await asyncio.to_thread(runtime.component_status)
    critical = (components["database"], components["scoring"])
    overall = "ok" if all(value == "ready" for value in critical) else "degraded"
    return HealthResponse(
        status=overall,
        service="VALYQON AI",
        version=__version__,
        components=components,
    )


@router.get(
    "/api/v1/companies",
    response_model=list[CompanyResponse],
    tags=["companies"],
    dependencies=[Depends(_protected)],
)
async def list_companies(request: Request, owner_user_id: int = Query(gt=0)) -> list[CompanyResponse]:
    owner_user_id = await resolve_owner(request, owner_user_id)
    service = _runtime(request).company_service
    if service is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Company workspaces are unavailable.")
    try:
        items = await asyncio.to_thread(service.list, owner_user_id)
    except Exception:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Company storage is unavailable.") from None
    return [_company_response(item) for item in items]


@router.post(
    "/api/v1/companies",
    response_model=CompanyResponse,
    tags=["companies"],
    dependencies=[Depends(_protected)],
)
async def create_company(payload: CompanyCreateRequest, request: Request) -> CompanyResponse:
    owner_user_id = await resolve_owner(request, payload.owner_user_id)
    service = _runtime(request).company_service
    if service is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Company workspaces are unavailable.")
    try:
        item = await asyncio.to_thread(
            service.create, owner_user_id, payload.name, payload.profile,
            make_active=payload.make_active,
        )
    except Exception as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from None
    return _company_response(item)


@router.post(
    "/api/v1/companies/{company_id}/activate",
    response_model=CompanyResponse,
    tags=["companies"],
    dependencies=[Depends(_protected)],
)
async def activate_company(company_id: int, payload: CompanyActivateRequest, request: Request) -> CompanyResponse:
    if company_id <= 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "company_id must be positive.")
    owner_user_id = await resolve_owner(request, payload.owner_user_id)
    service = _runtime(request).company_service
    if service is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Company workspaces are unavailable.")
    try:
        item = await asyncio.to_thread(service.set_active, owner_user_id, company_id)
    except Exception as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from None
    return _company_response(item)


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
    owner_user_id = await resolve_owner(request, owner_user_id)
    repository = _runtime(request).tender_repository
    if repository is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database is unavailable.")
    try:
        records = await asyncio.to_thread(repository.list_recent, owner_user_id, limit)
    except DatabaseError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Document storage is temporarily unavailable.") from None
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
    owner_user_id = await resolve_owner(request, owner_user_id)
    repository = _runtime(request).tender_repository
    if repository is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database is unavailable.")
    try:
        record = await asyncio.to_thread(repository.find_by_id, owner_user_id, tender_id)
    except DatabaseError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Document storage is temporarily unavailable.") from None
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tender not found.")
    return _detail(record)


@router.post(
    "/api/v1/scoring/evaluate",
    response_model=ScoringResult,
    tags=["scoring"],
    dependencies=[Depends(_protected)],
)
async def evaluate_score(
    analysis: TenderAnalysis,
    request: Request,
    owner_user_id: int | None = Query(default=None, gt=0),
) -> ScoringResult:
    owner_user_id = await resolve_owner(request, owner_user_id)
    runtime = _runtime(request)
    account = await current_account(request, touch=False)
    profile = runtime.company_profile
    if owner_user_id is not None and runtime.company_service is not None:
        try:
            if account is not None:
                workspace = await asyncio.to_thread(runtime.company_service.active, owner_user_id)
                profile = workspace.profile if workspace is not None else None
            else:
                profile = await asyncio.to_thread(runtime.company_service.profile_for_owner, owner_user_id)
        except Exception:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Company profile is unavailable.") from None
    if profile is None:
        code = status.HTTP_409_CONFLICT if account is not None else status.HTTP_503_SERVICE_UNAVAILABLE
        detail = (
            "Create a company profile before using company scoring."
            if account is not None
            else "Company profile is unavailable."
        )
        raise HTTPException(code, detail)
    return score_tender(analysis, profile)


@router.post(
    "/api/v1/rag/ask",
    response_model=RagAskResponse,
    tags=["rag"],
    dependencies=[Depends(_protected)],
)
async def rag_ask(payload: RagAskRequest, request: Request) -> RagAskResponse:
    owner_user_id = await resolve_owner(request, payload.owner_user_id)
    runtime = _runtime(request)
    if runtime.rag_service is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "RAG is unavailable.")
    if runtime.provider is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "LLM is unavailable.")
    try:
        answer = await runtime.rag_service.answer(
            owner_user_id,
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
    owner_user_id = await resolve_owner(request, owner_user_id)
    service = _runtime(request).monitoring_service
    if service is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Monitoring is unavailable.")
    subscription = await service.subscription(owner_user_id)
    runtime = _runtime(request)
    account = await current_account(request, touch=False)
    workspace = None
    if runtime.company_service is not None:
        try:
            workspace = await asyncio.to_thread(runtime.company_service.active, owner_user_id)
        except Exception:
            workspace = None

    if account is not None and workspace is None:
        return MonitorStatusResponse(
            background_enabled=service.settings.enabled,
            interval_seconds=service.settings.interval_seconds,
            rss_feeds=0,
            subscription_enabled=False,
            active_company=None,
            feed_mode="no-company",
        )

    profile = workspace.profile if workspace is not None else runtime.company_profile
    if profile is None and hasattr(service, "profile_for_owner"):
        profile = await service.profile_for_owner(owner_user_id)
    if profile is not None and getattr(service.settings, "profile_feeds_enabled", False) and profile.monitoring_keywords:
        feed_count = min(len(profile.monitoring_keywords), getattr(service.settings, "profile_feed_limit", 5))
        feed_mode = "company-profile"
    else:
        feed_count = len(service.settings.eis_rss_urls)
        feed_mode = "static"
    return MonitorStatusResponse(
        background_enabled=service.settings.enabled,
        interval_seconds=service.settings.interval_seconds,
        rss_feeds=feed_count,
        subscription_enabled=bool(subscription and subscription.enabled),
        active_company=(workspace.name if workspace is not None else (profile.company_name if profile else None)),
        feed_mode=feed_mode,
    )


@router.post(
    "/api/v1/monitoring/scan",
    response_model=list[MonitorNoticeResponse],
    tags=["monitoring"],
    dependencies=[Depends(_protected)],
)
async def monitoring_scan(payload: MonitorScanRequest, request: Request) -> list[MonitorNoticeResponse]:
    owner_user_id = await resolve_owner(request, payload.owner_user_id)
    runtime = _runtime(request)
    service = runtime.monitoring_service
    if service is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Monitoring is unavailable.")

    account = await current_account(request, touch=False)
    if account is not None:
        workspace = None
        if runtime.company_service is not None:
            try:
                workspace = await asyncio.to_thread(runtime.company_service.active, owner_user_id)
            except Exception:
                raise HTTPException(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    "Company storage is unavailable.",
                ) from None
        if workspace is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Create a company profile before running monitoring.",
            )

    try:
        matches = await service.scan_new(owner_user_id)
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
    owner_user_id = await resolve_owner(request, owner_user_id)
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
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Document storage is temporarily unavailable.") from None
    if existing is not None:
        duplicate_scoring = existing.scoring
        if runtime.company_service is not None:
            try:
                duplicate_profile = await asyncio.to_thread(
                    runtime.company_service.profile_for_owner, owner_user_id
                )
                if duplicate_profile is not None:
                    duplicate_scoring = score_tender(existing.analysis, duplicate_profile)
            except Exception:
                pass
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
            warnings=["Duplicate PDF: stored analysis reused; LLM was not called. Scoring uses the active company profile."],
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

    warnings: list[str] = []
    active_profile = runtime.company_profile
    if runtime.company_service is not None:
        try:
            resolved_profile = await asyncio.to_thread(runtime.company_service.profile_for_owner, owner_user_id)
            if resolved_profile is not None:
                active_profile = resolved_profile
        except Exception:
            warnings.append("Active company profile could not be loaded; fallback profile used.")
    scoring = score_tender(result.analysis, active_profile) if active_profile else None
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
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Document storage is temporarily unavailable.") from None

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


@router.get("/forgot-password", response_class=HTMLResponse, include_in_schema=False)
async def forgot_password_page():
    from .auth_pages import forgot_password_html
    return HTMLResponse(forgot_password_html(), headers={"Cache-Control": "no-store"})


@router.get("/reset-password", response_class=HTMLResponse, include_in_schema=False)
async def reset_password_page():
    from .auth_pages import reset_password_html
    return HTMLResponse(reset_password_html(), headers={
        "Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
    })
