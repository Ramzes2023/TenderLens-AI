"""Organization-scoped scoring and on-demand monitoring workflows."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.companies import (
    CompanyAuthorizationError,
    CompanyRepositoryError,
)
from app.database import (
    DatabaseAuthorizationError,
    DatabaseError,
)
from app.models.tender import TenderAnalysis
from app.tenancy import organization_owner_id
from app.monitoring import (
    MonitoringAuthorizationError,
    MonitoringRepositoryError,
)
from app.organizations import OrganizationError
from app.scoring.engine import score_tender
from app.services.tender_analysis import analysis_from_notice
from app.scoring.models import ScoringResult

from .schemas import (
    MonitorNoticeResponse,
    MonitorStatusResponse,
    TenderDiscoveryItem,
    TenderDiscoveryResponse,
)
from .security import (
    current_account,
    require_same_origin_browser_request,
)


router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}",
    tags=["organization-workflows"],
)


class SavedOpportunityResponse(BaseModel):
    id: int
    organization_id: int
    company_id: int
    opportunity: TenderDiscoveryItem
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


def _shortlist_repository(
    request: Request,
):
    repository = getattr(
        request.app.state.runtime,
        "tender_repository",
        None,
    )

    if repository is None:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "Saved opportunity storage "
                "is unavailable."
            ),
        )

    return repository


def _shortlist_data_error(
    error: Exception,
):
    if isinstance(
        error,
        DatabaseAuthorizationError,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Saved opportunity access denied."
            ),
        ) from None

    raise HTTPException(
        status_code=(
            status.HTTP_503_SERVICE_UNAVAILABLE
        ),
        detail=(
            "Saved opportunity storage "
            "is unavailable."
        ),
    ) from None


def _saved_opportunity_response(
    record,
):
    try:
        opportunity = (
            TenderDiscoveryItem
            .model_validate_json(
                record.snapshot_json
            )
        )
    except Exception:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "Saved opportunity data "
                "is unavailable."
            ),
        ) from None

    return SavedOpportunityResponse(
        id=record.id,
        organization_id=(
            record.organization_id
        ),
        company_id=record.company_id,
        opportunity=opportunity,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _company_service(request: Request):
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


def _monitoring_service(request: Request):
    service = getattr(
        request.app.state.runtime,
        "monitoring_service",
        None,
    )

    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Monitoring is unavailable.",
        )

    return service


def _discovery_service(request: Request):
    service = getattr(
        request.app.state.runtime,
        "tender_discovery_service",
        None,
    )

    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Tender discovery is unavailable.",
        )

    return service


def _source_catalog(request: Request):
    catalog = getattr(
        request.app.state.runtime,
        "source_catalog",
        None,
    )

    if catalog is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Procurement source catalog is unavailable.",
        )

    return catalog


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


# VALYQON METADATA PREVIEW SCORING V2


def _metadata_preview_scoring(
    metadata_analysis,
    profile,
):
    """
    Rank metadata opportunities by product relevance.

    Search prefilter and metadata scoring intentionally
    use the same keyword matcher.

    Full document scoring remains unchanged.
    """
    from app.monitoring.service import (
        _term_match,
    )

    result = score_tender(
        metadata_analysis,
        profile,
    )

    title = (
        metadata_analysis.title
        or ""
    )

    object_text = (
        metadata_analysis.procurement_object
        or ""
    )

    technical = " ".join(
        metadata_analysis.technical_requirements
        or []
    )

    full_text = " ".join(
        (
            title,
            object_text,
            technical,
        )
    )

    primary_object = (
        object_text[:350]
    )

    product_keywords = [
        keyword
        for keyword
        in profile.product_keywords
        if str(keyword).strip()
    ]

    all_matches = [
        keyword
        for keyword
        in product_keywords
        if _term_match(
            full_text,
            keyword,
        )
    ]

    title_matches = [
        keyword
        for keyword
        in all_matches
        if _term_match(
            title,
            keyword,
        )
    ]

    primary_matches = [
        keyword
        for keyword
        in all_matches
        if _term_match(
            primary_object,
            keyword,
        )
    ]

    if not all_matches:
        relevance = 0.0

    elif title_matches:
        relevance = 70.0

    elif primary_matches:
        relevance = 60.0

    else:
        relevance = 35.0

    lower_primary = (
        (
            title
            + " "
            + object_text[:700]
        )
        .casefold()
        .replace("?", "?")
    )

    supply_signals = (
        "supply",
        "purchase",
        "delivery of",
        "replacement of",
        "supply and install",
        "\u043f\u043e\u0441\u0442\u0430\u0432\u043a",
        "\u0437\u0430\u043a\u0443\u043f\u043a",
        "\u043f\u0440\u0438\u043e\u0431\u0440\u0435\u0442\u0435\u043d",
    )

    service_only_signals = (
        "condition assessment",
        "building assessment",
        "consultancy",
        "consulting services",
        "advisory services",
        "feasibility study",
        "audit services",
        "survey services",
        "inspection services",
        "design services",
        "\u043e\u0431\u0441\u043b\u0435\u0434\u043e\u0432\u0430\u043d\u0438",
        "\u043a\u043e\u043d\u0441\u0443\u043b\u044c\u0442\u0430\u0446",
        "\u0430\u0443\u0434\u0438\u0442",
    )

    has_supply_intent = any(
        signal in lower_primary
        for signal in supply_signals
    )

    service_only = any(
        signal in lower_primary
        for signal in service_only_signals
    )

    if (
        all_matches
        and has_supply_intent
    ):
        relevance += 10.0

    if (
        service_only
        and not has_supply_intent
        and not title_matches
    ):
        relevance = min(
            relevance,
            20.0,
        )

    relevance = round(
        min(
            90.0,
            max(
                0.0,
                relevance,
            ),
        ),
        1,
    )

    updated_criteria = []

    for criterion in result.criteria:
        if criterion.code != "category":
            updated_criteria.append(
                criterion
            )
            continue

        if relevance >= 65:
            status = "matched"
            explanation = (
                "Strong product relevance in "
                "tender metadata."
            )

        elif relevance > 0:
            status = "partial"
            explanation = (
                "Product evidence exists, but "
                "the metadata indicates only "
                "partial or contextual relevance."
            )

        else:
            status = "failed"
            explanation = (
                "No meaningful product match "
                "was found in tender metadata."
            )

        earned = round(
            criterion.weight
            * relevance
            / 100.0,
            1,
        )

        updated_criteria.append(
            criterion.model_copy(
                update={
                    "status": status,
                    "earned_points": earned,
                    "explanation": explanation,
                    "evidence": list(
                        all_matches[:10]
                    ),
                }
            )
        )

    return result.model_copy(
        update={
            "fit_score": relevance,
            "criteria": updated_criteria,
        }
    )




def _discovery_item(
    match,
    profile,
):
    notice = match.notice

    metadata_analysis = analysis_from_notice(
        notice
    )

    return TenderDiscoveryItem(
        source=notice.source,
        external_id=notice.external_id,
        title=notice.title,
        url=notice.url,
        tender_number=notice.tender_number,
        customer=notice.customer,
        initial_price=notice.initial_price,
        currency=notice.currency,
        deadline=notice.deadline,
        region=notice.region,
        reasons=list(match.reasons),
        published_at=notice.published_at,
        summary=notice.summary,
        analysis_stage="metadata_preview",
        metadata_analysis=metadata_analysis,
        preliminary_scoring=_metadata_preview_scoring(
            metadata_analysis,
            profile,
        ),
        full_ai_analyzed=False,
    )


def _notice_response(match):
    notice = match.notice

    return MonitorNoticeResponse(
        source=notice.source,
        external_id=notice.external_id,
        title=notice.title,
        url=notice.url,
        tender_number=notice.tender_number,
        customer=notice.customer,
        initial_price=notice.initial_price,
        currency=notice.currency,
        deadline=notice.deadline,
        region=notice.region,
        reasons=list(match.reasons),
    )


@router.get(
    "/shortlist",
    response_model=list[
        SavedOpportunityResponse
    ],
)
async def list_saved_opportunities(
    organization_id: int,
    request: Request,
    response: Response,
):
    account = await _account(
        request
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
                "Create and activate an "
                "organization company before "
                "using the shortlist."
            ),
        )

    repository = _shortlist_repository(
        request
    )

    try:
        records = await asyncio.to_thread(
            repository
            .list_saved_opportunities_for_organization,
            account.id,
            organization_id,
            workspace.id,
            200,
        )
    except DatabaseError as error:
        _shortlist_data_error(
            error
        )

    response.headers[
        "Cache-Control"
    ] = "no-store"

    return [
        _saved_opportunity_response(
            record
        )
        for record in records
    ]


@router.post(
    "/shortlist",
    response_model=SavedOpportunityResponse,
)
async def save_discovered_opportunity(
    organization_id: int,
    payload: TenderDiscoveryItem,
    request: Request,
    response: Response,
):
    require_same_origin_browser_request(
        request
    )

    account = await _account(
        request
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
                "Create and activate an "
                "organization company before "
                "saving opportunities."
            ),
        )

    repository = _shortlist_repository(
        request
    )

    try:
        record = await asyncio.to_thread(
            repository
            .save_opportunity_for_organization,
            account_id=account.id,
            organization_id=organization_id,
            company_id=workspace.id,
            source=payload.source,
            external_id=payload.external_id,
            snapshot_json=(
                payload.model_dump_json()
            ),
        )
    except DatabaseError as error:
        _shortlist_data_error(
            error
        )

    response.headers[
        "Cache-Control"
    ] = "no-store"

    return _saved_opportunity_response(
        record
    )


@router.delete(
    "/shortlist/{saved_id}",
    status_code=(
        status.HTTP_204_NO_CONTENT
    ),
)
async def remove_saved_opportunity(
    organization_id: int,
    saved_id: int,
    request: Request,
):
    require_same_origin_browser_request(
        request
    )

    if saved_id <= 0:
        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=(
                "saved_id must be positive."
            ),
        )

    account = await _account(
        request
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
                "Create and activate an "
                "organization company before "
                "using the shortlist."
            ),
        )

    repository = _shortlist_repository(
        request
    )

    try:
        removed = await asyncio.to_thread(
            repository
            .delete_saved_opportunity_for_organization,
            account_id=account.id,
            organization_id=organization_id,
            company_id=workspace.id,
            saved_id=saved_id,
        )
    except DatabaseError as error:
        _shortlist_data_error(
            error
        )

    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Saved opportunity not found."
            ),
        )

    return Response(
        status_code=(
            status.HTTP_204_NO_CONTENT
        ),
        headers={
            "Cache-Control": "no-store",
        },
    )


@router.post(
    "/discover/tenders",
    response_model=TenderDiscoveryResponse,
)
async def organization_discover_tenders(
    organization_id: int,
    request: Request,
    response: Response,
):
    """Search enabled procurement sources for the active company."""

    require_same_origin_browser_request(
        request
    )

    account = await _account(
        request
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
                "before discovering tenders."
            ),
        )

    discovery = _discovery_service(
        request
    )

    catalog = _source_catalog(
        request
    )

    try:
        matches, report = (
            await discovery.fetch_matches_from_catalog_for_profile(
                catalog,
                workspace.profile,
            )
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Global procurement discovery failed.",
        ) from None

    response.headers[
        "Cache-Control"
    ] = "no-store"

    return TenderDiscoveryResponse(
        items=[
            _discovery_item(
                match,
                workspace.profile,
            )
            for match in matches
        ],
        attempted_sources=list(
            report.attempted_sources
        ),
        successful_sources=list(
            report.successful_sources
        ),
        failed_sources=[
            failure.source
            for failure in report.failures
        ],
        partial_failure=report.partial_failure,
        total_failure=report.total_failure,
    )


@router.post(
    "/scoring/evaluate",
    response_model=ScoringResult,
)
async def organization_scoring(
    organization_id: int,
    analysis: TenderAnalysis,
    request: Request,
    response: Response,
):
    require_same_origin_browser_request(request)

    account = await _account(request)
    workspace = await _active_company(
        request,
        account,
        organization_id,
    )

    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Create an organization company profile before scoring.",
        )

    response.headers["Cache-Control"] = "no-store"

    return score_tender(
        analysis,
        workspace.profile,
    )


@router.get(
    "/monitoring/status",
    response_model=MonitorStatusResponse,
)
async def organization_monitoring_status(
    organization_id: int,
    request: Request,
    response: Response,
):
    account = await _account(request)
    workspace = await _active_company(
        request,
        account,
        organization_id,
    )

    monitoring = _monitoring_service(request)

    if workspace is None:
        response.headers["Cache-Control"] = "no-store"

        return MonitorStatusResponse(
            background_enabled=monitoring.settings.enabled,
            interval_seconds=monitoring.settings.interval_seconds,
            rss_feeds=0,
            subscription_enabled=False,
            active_company=None,
            feed_mode="no-company",
        )

    profile = workspace.profile

    if (
        getattr(
            monitoring.settings,
            "profile_feeds_enabled",
            False,
        )
        and profile.monitoring_keywords
    ):
        feed_count = min(
            len(profile.monitoring_keywords),
            getattr(
                monitoring.settings,
                "profile_feed_limit",
                5,
            ),
        )
        feed_mode = "company-profile"
    else:
        feed_count = len(
            monitoring.settings.eis_rss_urls
        )
        feed_mode = "static"

    response.headers["Cache-Control"] = "no-store"

    return MonitorStatusResponse(
        background_enabled=monitoring.settings.enabled,
        interval_seconds=monitoring.settings.interval_seconds,
        rss_feeds=feed_count,
        subscription_enabled=False,
        active_company=workspace.name,
        feed_mode=feed_mode,
    )


@router.post(
    "/monitoring/scan",
    response_model=list[MonitorNoticeResponse],
)
async def organization_monitoring_scan(
    organization_id: int,
    request: Request,
    response: Response,
):
    require_same_origin_browser_request(request)

    account = await _account(request)

    organization_service = getattr(
        request.app.state.runtime,
        "organization_service",
        None,
    )

    if organization_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Organizations are unavailable.",
        )

    try:
        await asyncio.to_thread(
            organization_service.require_membership,
            account,
            organization_id,
            {"owner", "admin", "member"},
        )
    except OrganizationError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization monitoring access denied.",
        ) from None

    workspace = await _active_company(
        request,
        account,
        organization_id,
    )

    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Create an organization company profile before monitoring.",
        )

    monitoring = _monitoring_service(request)

    owner_user_id = organization_owner_id(
        organization_id
    )

    try:
        matches = await monitoring.scan_new_for_organization(
            account_id=account.id,
            organization_id=organization_id,
            owner_user_id=owner_user_id,
            profile=workspace.profile,
            company_scope=str(workspace.id),
        )
    except MonitoringAuthorizationError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization monitoring access denied.",
        ) from None
    except MonitoringRepositoryError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Monitoring storage is unavailable.",
        ) from None
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="EIS monitoring request failed.",
        ) from None

    response.headers["Cache-Control"] = "no-store"

    return [
        _notice_response(match)
        for match in matches
    ]
