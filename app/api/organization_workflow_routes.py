"""Organization-scoped scoring and on-demand monitoring workflows."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.companies import (
    CompanyAuthorizationError,
    CompanyRepositoryError,
)
from app.models.tender import TenderAnalysis
from app.tenancy import organization_owner_id
from app.monitoring import (
    MonitoringAuthorizationError,
    MonitoringRepositoryError,
)
from app.organizations import OrganizationError
from app.scoring.engine import score_tender
from app.scoring.models import ScoringResult

from .schemas import (
    MonitorNoticeResponse,
    MonitorStatusResponse,
)
from .security import (
    current_account,
    require_same_origin_browser_request,
)


router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}",
    tags=["organization-workflows"],
)


async def _account(request: Request):
    account = await current_account(request)

    if account is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    return account


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
