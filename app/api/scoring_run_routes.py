"""Opt-in asynchronous scoring. Existing synchronous Discover remains the default."""
import asyncio
import sqlite3
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.database.backend import StorageError
from app.companies import CompanyAuthorizationError, CompanyRepositoryError
from app.organizations import OrganizationError
from app.quotas import QuotaExceeded
from app.jobs.models import JobScope, JobValueError
from app.scoring.runs import ScoringAccessError, ScoringInputError
from .security import current_account, require_same_origin_browser_request

router = APIRouter(prefix='/api/v1/organizations/{organization_id}/companies/{company_id}/scoring/runs',
                   tags=['organization-scoring'])
ScopeID = Annotated[int, Path(ge=1, le=2**63 - 1)]


class ScoringRunRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sources: Annotated[list[Annotated[str, Field(min_length=1, max_length=64)]], Field(min_length=1, max_length=5)] = ['ted']
    limit_per_source: int = Field(default=20, strict=True, ge=1, le=100)


async def execute(request, response, organization_id, company_id, operation):
    account = await current_account(request)
    if account is None:
        raise HTTPException(401, 'Authentication required.')
    service = getattr(request.app.state.runtime, 'scoring_run_service', None)
    if service is None:
        raise HTTPException(503, 'Background scoring is unavailable.')
    scope = JobScope(account.id, organization_id, company_id)
    try:
        runtime = request.app.state.runtime
        if runtime.organization_service is None or runtime.company_service is None:
            raise HTTPException(503, 'Company workspaces are unavailable.')
        await asyncio.to_thread(runtime.organization_service.require_membership, account, organization_id)
        workspace = await asyncio.to_thread(runtime.company_service.get_for_organization,
                                            account.id, organization_id, company_id)
        if workspace is None:
            raise ScoringAccessError('Scoring access denied.')
        value = await asyncio.to_thread(operation, service, scope)
    except QuotaExceeded as exc:
        raise HTTPException(429, 'Tenant job quota exceeded.', headers={'Retry-After': str(exc.retry_after), 'Cache-Control': 'no-store'}) from None
    except (ScoringAccessError, CompanyAuthorizationError, OrganizationError):
        raise HTTPException(403, 'Scoring access denied.') from None
    except ScoringInputError:
        raise HTTPException(409, 'Scoring input changed or is invalid; request a new run.') from None
    except (sqlite3.Error, StorageError, JobValueError, CompanyRepositoryError):
        raise HTTPException(503, 'Background scoring is unavailable.') from None
    response.headers['Cache-Control'] = 'no-store'
    return value


@router.post('', status_code=202)
async def enqueue_run(organization_id: ScopeID, company_id: ScopeID, payload: ScoringRunRequest,
                      request: Request, response: Response):
    require_same_origin_browser_request(request)

    def operation(service, scope):
        job = service.enqueue(scope=scope, sources=payload.sources, limit_per_source=payload.limit_per_source)
        return {'job_id': job.id, 'status': job.state, 'engine_version': job.payload['engine_version'],
                'profile_digest': job.payload['profile_digest'], 'snapshot_id': job.payload['snapshot_id']}

    return await execute(request, response, organization_id, company_id, operation)


@router.get('/{job_id}')
async def read_run(organization_id: ScopeID, company_id: ScopeID, job_id: Annotated[str, Path(min_length=1, max_length=64)],
                   request: Request, response: Response,
                   limit: Annotated[int, Query(ge=1, le=100)] = 50,
                   offset: Annotated[int, Query(ge=0, le=500)] = 0):
    return await execute(request, response, organization_id, company_id,
                         lambda service, scope: service.view(job_id, scope=scope, limit=limit, offset=offset))
