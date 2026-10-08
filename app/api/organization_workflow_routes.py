"""Organization-scoped scoring and on-demand monitoring workflows."""

from __future__ import annotations

import asyncio
import json

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
    SourceHealthItem,
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


class DiscoveryHistorySummaryResponse(BaseModel):
    id: int
    organization_id: int
    company_id: int
    created_by_account_id: int
    result_count: int
    scored_count: int
    attempted_sources: list[str]
    successful_sources: list[str]
    failed_sources: list[str]
    partial_failure: bool
    total_failure: bool
    created_at: str


class DiscoveryHistoryDetailResponse(
    DiscoveryHistorySummaryResponse
):
    discovery: TenderDiscoveryResponse


class SourceHealthResponse(BaseModel):
    organization_id: int
    company_id: int
    company_name: str
    history_id: int | None = None
    last_checked: str | None = None
    sources: list[SourceHealthItem]


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


def _discovery_history_repository(
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
                "Discovery history storage "
                "is unavailable."
            ),
        )

    return repository


def _discovery_history_data_error(
    error: Exception,
):
    if isinstance(
        error,
        DatabaseAuthorizationError,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Discovery history access denied."
            ),
        ) from None

    raise HTTPException(
        status_code=(
            status.HTTP_503_SERVICE_UNAVAILABLE
        ),
        detail=(
            "Discovery history storage "
            "is unavailable."
        ),
    ) from None


def _history_source_list(
    raw: str,
) -> list[str]:
    try:
        values = json.loads(raw)

        if (
            not isinstance(
                values,
                list,
            )
            or not all(
                isinstance(
                    item,
                    str,
                )
                for item in values
            )
        ):
            raise ValueError

        return values
    except Exception:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "Discovery history data "
                "is unavailable."
            ),
        ) from None


def _discovery_history_summary(
    record,
):
    return DiscoveryHistorySummaryResponse(
        id=record.id,
        organization_id=(
            record.organization_id
        ),
        company_id=record.company_id,
        created_by_account_id=(
            record.created_by_account_id
        ),
        result_count=record.result_count,
        scored_count=record.scored_count,
        attempted_sources=(
            _history_source_list(
                record.attempted_sources_json
            )
        ),
        successful_sources=(
            _history_source_list(
                record.successful_sources_json
            )
        ),
        failed_sources=(
            _history_source_list(
                record.failed_sources_json
            )
        ),
        partial_failure=(
            record.partial_failure
        ),
        total_failure=(
            record.total_failure
        ),
        created_at=record.created_at,
    )


def _discovery_history_detail(
    record,
):
    summary = (
        _discovery_history_summary(
            record
        )
    )

    try:
        discovery = (
            TenderDiscoveryResponse
            .model_validate_json(
                record.snapshot_json
            )
            .model_copy(
                update={
                    "history_id": record.id,
                }
            )
        )
    except Exception:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "Discovery history snapshot "
                "is unavailable."
            ),
        ) from None

    return DiscoveryHistoryDetailResponse(
        **summary.model_dump(),
        discovery=discovery,
    )


def _catalog_source_metadata(
    catalog,
):
    registry = getattr(
        catalog,
        "registry",
        None,
    )

    if registry is None:
        return ()

    metadata = getattr(
        registry,
        "metadata",
        None,
    )

    if not callable(metadata):
        return ()

    try:
        return tuple(
            metadata()
        )
    except Exception:
        return ()


_SOURCE_HEALTH_FAILURE_MESSAGE = (
    "Source could not be reached during "
    "the latest Discovery."
)


def _source_health_items(
    catalog,
    *,
    report=None,
    previous=None,
    legacy_attempted=(),
    legacy_successful=(),
    legacy_failed=(),
):
    metadata_values = (
        _catalog_source_metadata(
            catalog
        )
    )

    run_statuses = tuple(
        getattr(
            report,
            "statuses",
            (),
        )
        or ()
    )

    run_by_source = {
        str(item.source):
        item
        for item in run_statuses
    }

    previous_values = list(
        previous
        or []
    )

    previous_by_source = {
        str(item.source):
        item
        for item in previous_values
    }

    attempted = {
        str(item)
        for item in legacy_attempted
    }

    successful = {
        str(item)
        for item in legacy_successful
    }

    failed = {
        str(item)
        for item in legacy_failed
    }

    results: list[
        SourceHealthItem
    ] = []

    seen: set[str] = set()

    for metadata in metadata_values:
        key = str(
            metadata.key
        )

        seen.add(key)

        capabilities = getattr(
            metadata,
            "capabilities",
            None,
        )

        auth_required = bool(
            getattr(
                capabilities,
                "authentication_required",
                False,
            )
        )

        transport = getattr(
            metadata.transport,
            "value",
            str(metadata.transport),
        )

        state = "not_checked"
        notice_count = None
        duration_ms = None
        error_type = None
        message = None

        if not bool(
            metadata.enabled
        ):
            state = "disabled"

            message = (
                "Source requires configuration "
                "before it can be checked."
                if auth_required
                else
                "Source is disabled in configuration."
            )

        elif key in run_by_source:
            run_status = (
                run_by_source[key]
            )

            raw_state = getattr(
                run_status.state,
                "value",
                str(run_status.state),
            )

            state = (
                "healthy"
                if raw_state == "ok"
                else "failed"
            )

            notice_count = int(
                run_status.notice_count
            )

            duration_ms = int(
                run_status.duration_ms
            )

            error_type = (
                run_status.error_type
            )

            message = (
                _SOURCE_HEALTH_FAILURE_MESSAGE
                if state == "failed"
                else None
            )

        elif key in previous_by_source:
            prior = (
                previous_by_source[key]
            )

            if prior.state in {
                "healthy",
                "failed",
            }:
                state = prior.state
                notice_count = (
                    prior.notice_count
                )
                duration_ms = (
                    prior.duration_ms
                )
                error_type = (
                    prior.error_type
                )
                message = (
                    _SOURCE_HEALTH_FAILURE_MESSAGE
                    if state == "failed"
                    else None
                )

        elif key in successful:
            state = "healthy"

        elif key in failed:
            state = "failed"
            message = (
                "Detailed source telemetry "
                "was not recorded for this "
                "historical Discovery run."
            )

        elif key in attempted:
            state = "not_checked"

        results.append(
            SourceHealthItem(
                source=key,
                display_name=str(
                    metadata.display_name
                ),
                transport=str(
                    transport
                ),
                jurisdictions=[
                    str(value)
                    for value
                    in metadata.jurisdictions
                ],
                languages=[
                    str(value)
                    for value
                    in metadata.languages
                ],
                homepage_url=(
                    metadata.homepage_url
                ),
                official=bool(
                    metadata.official
                ),
                enabled=bool(
                    metadata.enabled
                ),
                authentication_required=(
                    auth_required
                ),
                state=state,
                notice_count=(
                    notice_count
                ),
                duration_ms=(
                    duration_ms
                ),
                error_type=(
                    error_type
                ),
                message=message,
            )
        )

    # Test adapters and future connectors may return
    # telemetry before they have public catalog metadata.
    for run_status in run_statuses:
        key = str(
            run_status.source
        )

        if key in seen:
            continue

        raw_state = getattr(
            run_status.state,
            "value",
            str(run_status.state),
        )

        results.append(
            SourceHealthItem(
                source=key,
                display_name=key,
                transport="unknown",
                jurisdictions=[],
                languages=[],
                homepage_url=None,
                official=False,
                enabled=True,
                authentication_required=False,
                state=(
                    "healthy"
                    if raw_state == "ok"
                    else "failed"
                ),
                notice_count=int(
                    run_status.notice_count
                ),
                duration_ms=int(
                    run_status.duration_ms
                ),
                error_type=(
                    run_status.error_type
                ),
                message=(
                    _SOURCE_HEALTH_FAILURE_MESSAGE
                    if raw_state != "ok"
                    else None
                ),
            )
        )

        seen.add(key)

    # Keep a historical source visible even if a future
    # catalog version no longer contains that connector.
    for prior in previous_values:
        key = str(
            prior.source
        )

        if key in seen:
            continue

        results.append(prior)
        seen.add(key)

    return results


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


from app.scoring.preview import score_metadata_preview as _metadata_preview_scoring


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


@router.get(
    "/discovery/history",
    response_model=list[
        DiscoveryHistorySummaryResponse
    ],
)
async def list_discovery_history(
    organization_id: int,
    request: Request,
    response: Response,
    limit: int = 50,
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
                "using discovery history."
            ),
        )

    repository = (
        _discovery_history_repository(
            request
        )
    )

    try:
        records = await asyncio.to_thread(
            repository
            .list_discovery_search_history_for_organization,
            account.id,
            organization_id,
            workspace.id,
            limit,
        )
    except DatabaseError as error:
        _discovery_history_data_error(
            error
        )

    response.headers[
        "Cache-Control"
    ] = "no-store"

    return [
        _discovery_history_summary(
            record
        )
        for record in records
    ]


@router.get(
    "/discovery/history/{history_id}",
    response_model=(
        DiscoveryHistoryDetailResponse
    ),
)
async def get_discovery_history(
    organization_id: int,
    history_id: int,
    request: Request,
    response: Response,
):
    if history_id <= 0:
        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=(
                "history_id must be positive."
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
                "using discovery history."
            ),
        )

    repository = (
        _discovery_history_repository(
            request
        )
    )

    try:
        record = await asyncio.to_thread(
            repository
            .get_discovery_search_history_for_organization,
            account.id,
            organization_id,
            workspace.id,
            history_id,
        )
    except DatabaseError as error:
        _discovery_history_data_error(
            error
        )

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Discovery history entry "
                "not found."
            ),
        )

    response.headers[
        "Cache-Control"
    ] = "no-store"

    return _discovery_history_detail(
        record
    )


@router.get(
    "/discovery/source-health",
    response_model=SourceHealthResponse,
)
async def get_discovery_source_health(
    organization_id: int,
    request: Request,
    response: Response,
):
    """
    Return the most recently recorded source health
    for the active company.

    This endpoint never probes procurement sources.
    """

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
                "using Source Health."
            ),
        )

    catalog = _source_catalog(
        request
    )

    repository = (
        _discovery_history_repository(
            request
        )
    )

    try:
        records = await asyncio.to_thread(
            repository
            .list_discovery_search_history_for_organization,
            account.id,
            organization_id,
            workspace.id,
            1,
        )
    except DatabaseError as error:
        _discovery_history_data_error(
            error
        )

    history_id = None
    last_checked = None
    source_items = (
        _source_health_items(
            catalog
        )
    )

    if records:
        record = records[0]

        history_id = record.id
        last_checked = (
            record.created_at
        )

        snapshot = None

        try:
            snapshot = (
                TenderDiscoveryResponse
                .model_validate_json(
                    record.snapshot_json
                )
            )
        except Exception:
            snapshot = None

        if (
            snapshot is not None
            and snapshot.source_statuses
        ):
            source_items = (
                _source_health_items(
                    catalog,
                    previous=(
                        snapshot
                        .source_statuses
                    ),
                )
            )

        else:
            source_items = (
                _source_health_items(
                    catalog,
                    legacy_attempted=(
                        _history_source_list(
                            record
                            .attempted_sources_json
                        )
                    ),
                    legacy_successful=(
                        _history_source_list(
                            record
                            .successful_sources_json
                        )
                    ),
                    legacy_failed=(
                        _history_source_list(
                            record
                            .failed_sources_json
                        )
                    ),
                )
            )

    response.headers[
        "Cache-Control"
    ] = "no-store"

    return SourceHealthResponse(
        organization_id=(
            organization_id
        ),
        company_id=workspace.id,
        company_name=workspace.name,
        history_id=history_id,
        last_checked=last_checked,
        sources=source_items,
    )


@router.post(
    "/discover/tenders",
    response_model=TenderDiscoveryResponse,
)
async def organization_discover_tenders(
    organization_id: int,
    request: Request,
    response: Response,
    snapshots: bool = False,
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

    if snapshots:
        # Explicit staged adoption; default live profile-aware discovery stays intact.
        from app.sources.opportunities import OpportunityRepository
        from app.sources.snapshots import snapshot_catalog
        database = getattr(request.app.state.runtime, 'database', None)
        if database is None:
            raise HTTPException(status_code=503, detail='Connector snapshots unavailable.')
        catalog = snapshot_catalog(catalog, OpportunityRepository(database))
        response.headers['X-Valyqon-Discovery-Mode'] = 'snapshots'

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

    discovery_response = (
        TenderDiscoveryResponse(
            items=[
                _discovery_item(
                    match,
                    workspace.profile,
                )
                for match in matches
            ],
            source_statuses=(
                _source_health_items(
                    catalog,
                    report=report,
                )
            ),
            attempted_sources=list(
                report.attempted_sources
            ),
            successful_sources=list(
                report.successful_sources
            ),
            failed_sources=[
                failure.source
                for failure
                in report.failures
            ],
            partial_failure=(
                report.partial_failure
            ),
            total_failure=(
                report.total_failure
            ),
        )
    )

    history_record = None

    repository = getattr(
        request.app.state.runtime,
        "tender_repository",
        None,
    )

    if repository is not None:
        try:
            history_record = (
                await asyncio.to_thread(
                    repository
                    .record_discovery_search_for_organization,
                    account_id=account.id,
                    organization_id=organization_id,
                    company_id=workspace.id,
                    result_count=len(
                        discovery_response.items
                    ),
                    scored_count=sum(
                        1
                        for item
                        in discovery_response.items
                        if (
                            item
                            .preliminary_scoring
                            .fit_score
                            is not None
                        )
                    ),
                    attempted_sources_json=(
                        json.dumps(
                            discovery_response
                            .attempted_sources,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    ),
                    successful_sources_json=(
                        json.dumps(
                            discovery_response
                            .successful_sources,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    ),
                    failed_sources_json=(
                        json.dumps(
                            discovery_response
                            .failed_sources,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    ),
                    partial_failure=(
                        discovery_response
                        .partial_failure
                    ),
                    total_failure=(
                        discovery_response
                        .total_failure
                    ),
                    snapshot_json=(
                        discovery_response
                        .model_dump_json()
                    ),
                )
            )
        except DatabaseError:
            # A successful connector run must
            # still reach the user even if
            # history persistence is temporarily
            # unavailable.
            history_record = None

    return discovery_response.model_copy(
        update={
            "history_id": (
                history_record.id
                if history_record
                is not None
                else None
            ),
        }
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
