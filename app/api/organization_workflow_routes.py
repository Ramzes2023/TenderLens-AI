"""Organization-scoped scoring and on-demand monitoring workflows."""

from __future__ import annotations

from app.jobs import JobScope
from app.quotas.synchronous import admitted_operation

import asyncio
import json
from datetime import datetime, timezone
from app.sources.international import public_diagnostic

from app.analytics.fit import FIT_POLICY_VERSION, PREVIEW_ENGINE_VERSION, PreviewProvenance
from app.scoring.runs import profile_digest

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
                diagnostic=(public_diagnostic(run_by_source[key].message)
                    if key in {'ted', 'uk_fts', 'world_bank'} and key in run_by_source and state == 'failed' else None),
                coverage={
                    'ted': 'Anonymous published ACTIVE notices; literal keyword search; at most 100 notices in one page. Missing deadlines remain unknown.',
                    'uk_fts': 'Recent one-hour update window; tender stage; at most two pages of 100 releases; keyword matching is local. Missing deadlines remain unknown.',
                    'world_bank': 'DS00979/RS00909, recent seven calendar days; at most two pages of 100 records; local keyword matching. Closed, undated and sparse records excluded.',
                }.get(key),
                last_successful_sync=(datetime.now(timezone.utc).isoformat()
                    if key in {'ted', 'uk_fts', 'world_bank'} and key in run_by_source and state == 'healthy'
                    else getattr(previous_by_source.get(key), 'last_successful_sync', None)),
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
    *,
    organization_id=None,
    company_id=None,
):
    notice = match.notice

    metadata_analysis = analysis_from_notice(
        notice
    )

    scoring = _metadata_preview_scoring(metadata_analysis, profile)
    provenance = None
    if organization_id is not None and company_id is not None:
        provenance = PreviewProvenance(
            organization_id=organization_id, company_id=company_id,
            profile_digest=profile_digest(profile), engine_version=PREVIEW_ENGINE_VERSION,
            scoring_policy_version=FIT_POLICY_VERSION, scoring_stage='metadata_preview',
            scored_at=datetime.now(timezone.utc).isoformat(),
        )
    return TenderDiscoveryItem(
        preliminary_provenance=provenance,
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
        enrichment=notice.enrichment,
        analysis_stage="metadata_preview",
        metadata_analysis=metadata_analysis,
        preliminary_scoring=scoring,
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

    provenance = getattr(payload, 'preliminary_provenance', None)
    if provenance is not None and (
        provenance.organization_id != organization_id
        or provenance.company_id != workspace.id
        or provenance.profile_digest != profile_digest(workspace.profile)
    ):
        raise HTTPException(status_code=409, detail="Company context changed. Run discovery again before saving.")

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


@router.get('/companies/{company_id}/discovery/history-snapshots')
async def history_snapshot_batch(organization_id: int, company_id: int, request: Request,
                                 response: Response, population_cursor: str, ids: str,
                                 page_size: int = 20, start: str | None = None, end: str | None = None):
    from app.analytics.paging import CursorError, unseal, utc_filter
    account = await _account(request)
    repository = _discovery_history_repository(request)
    key = request.app.state.api_settings.api_key
    if not key or not key.strip():
        raise HTTPException(503, detail={'storage_state': 'unavailable', 'reason': 'Existing app signing key unavailable.'})
    try:
        start, end = utc_filter(start), utc_filter(end)
        binding = ['history-v1', account.id, organization_id, company_id, start, end, page_size]
        state = unseal(population_cursor, key, binding)
        if len(ids) > 500:
            raise CursorError('Snapshot ID query is too large.')
        identities = [int(value) for value in ids.split(',')]
        if not 1 <= len(identities) <= 20 or any(value <= 0 for value in identities):
            raise CursorError('Snapshot batch must contain 1..20 positive IDs.')
        # Reauthorize even when every requested ID is missing or outside the watermark.
        await asyncio.to_thread(repository.page_discovery_history, account.id, organization_id,
                                company_id, state=state, page_size=1, start=start, end=end)
        items, seen = [], set()
        for identity in identities:
            if identity in seen:
                items.append({'id': identity, 'state': 'duplicate_request'})
                continue
            seen.add(identity)
            record = await asyncio.to_thread(repository.get_discovery_search_history_for_organization,
                                             account.id, organization_id, company_id, identity)
            if record is None:
                items.append({'id': identity, 'state': 'missing_in_authorized_scope'})
                continue
            timestamp = utc_filter(record.created_at)
            if (record.id > state['fence'] or record.created_at > state['as_of'] or
                    (start and timestamp < start) or (end and timestamp >= end)):
                items.append({'id': identity, 'state': 'out_of_watermark_or_query'})
                continue
            try:
                snapshot = _discovery_history_detail(record).discovery
                items.append({'id': identity, 'state': 'available' if len(snapshot.items) == record.result_count
                              else 'incomplete_count_mismatch', 'snapshot': snapshot.model_dump(mode='json')})
            except HTTPException:
                items.append({'id': identity, 'state': 'missing' if not record.snapshot_json.strip() else 'corrupt'})
    except (CursorError, ValueError):
        raise HTTPException(422, 'Invalid snapshot query or population cursor.') from None
    except DatabaseError as error:
        if isinstance(error, DatabaseAuthorizationError):
            _discovery_history_data_error(error)
        raise HTTPException(503, detail={'storage_state': 'error', 'completeness': 'unavailable'}) from None
    response.headers['Cache-Control'] = 'no-store'
    return {'items': items, 'storage_state': 'available', 'lifetime_total': None}


@router.get('/companies/{company_id}/discovery/history-page')
async def page_company_history(organization_id: int, company_id: int, request: Request,
                               response: Response, page_size: int = 20, cursor: str | None = None,
                               start: str | None = None, end: str | None = None):
    from app.analytics.paging import CursorError, seal, unseal, utc_filter
    import time
    account = await _account(request)
    repository = _discovery_history_repository(request)
    key = request.app.state.api_settings.api_key
    if not key or not key.strip():
        raise HTTPException(503, detail={'storage_state': 'unavailable', 'reason': 'Existing app signing key unavailable.'})
    try:
        start, end = utc_filter(start), utc_filter(end)
        if not 1 <= page_size <= 20 or (start and end and start >= end):
            raise CursorError('Invalid page size or time interval.')
        binding = ['history-v1', account.id, organization_id, company_id, start, end, page_size]
        state = unseal(cursor, key, binding) if cursor else None
        page = await asyncio.to_thread(repository.page_discovery_history, account.id, organization_id,
                                      company_id, page_size=page_size, state=state, start=start, end=end)
    except CursorError as error:
        raise HTTPException(422, str(error)) from None
    except DatabaseError as error:
        if isinstance(error, DatabaseAuthorizationError):
            _discovery_history_data_error(error)
        raise HTTPException(503, detail={'storage_state': 'error', 'completeness': 'unavailable'}) from None
    state = page.pop('state')
    state.update(binding=binding, expires=state.get('expires', time.time() + 3600))
    items = []
    for record in page.pop('records'):
        item = {'event': _discovery_history_summary(record).model_dump(), 'snapshot_state': 'available'}
        try:
            detail = _discovery_history_detail(record)
            item['snapshot'] = detail.discovery.model_dump(mode='json')
            if len(detail.discovery.items) != record.result_count:
                item['snapshot_state'] = 'incomplete_count_mismatch'
            identities = [(entry.source, entry.external_id) for entry in detail.discovery.items]
            item['duplicate_identity_count'] = len(identities) - len(set(identities))
        except HTTPException:
            item['snapshot_state'] = 'missing' if not record.snapshot_json.strip() else 'corrupt'
        items.append(item)
    response.headers['Cache-Control'] = 'no-store'
    return dict(page, items=items, next_cursor=seal(state, key) if page['has_more'] else None,
                population_cursor=seal(state, key), as_of=state['as_of'], id_watermark=state['fence'],
                read_count=state['read_count'], lifetime_total=None,
                snapshot_completeness='partial' if any(i['snapshot_state'] != 'available' or i.get('duplicate_identity_count') for i in items) else 'complete_page',
                time_field='search_created_at', interval='[start,end)', timezone='UTC')


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

    async with admitted_operation(request, JobScope(account.id, organization_id, workspace.id), 'discovery'):
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

    current_workspace = await _active_company(request, account, organization_id)
    if (current_workspace is None or current_workspace.id != workspace.id
            or profile_digest(current_workspace.profile) != profile_digest(workspace.profile)):
        raise HTTPException(status_code=409, detail="Company context changed during discovery. Run discovery again.")

    discovery_response = (
        TenderDiscoveryResponse(
            items=[
                _discovery_item(
                    match,
                    workspace.profile,
                    organization_id=organization_id,
                    company_id=workspace.id,
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

    async with admitted_operation(request, JobScope(account.id, organization_id, workspace.id), 'monitoring'):
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
