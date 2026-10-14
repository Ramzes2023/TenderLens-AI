"""Bounded optimistic immutable H reads; signed commitments, no cache or writes."""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import re
import sqlite3
import time
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path, Request, Response
from app.analytics.deadlines import DeadlineWindow
from app.analytics.paging import CursorError, seal, unseal, utc_filter
from app.analytics.service import POLICY, SOURCES, _json, aggregate_history, load_history
from app.analytics.fit import FIT_POLICY_VERSION, PREVIEW_ENGINE_VERSION
from app.analytics.dates import DATE_POLICY
from app.analytics.deadlines import DEADLINE_POLICY
from app.analytics.normalization import COUNTRY_VERSION
from app.analytics.taxonomies import TAXONOMY_VERSION, LEGACY_TAXONOMY_VERSION
from app.companies import CompanyAuthorizationError, CompanyRepositoryError
from app.database import DatabaseAuthorizationError, DatabaseError
from app.database.backend import StorageError
from app.organizations import OrganizationError
from app.scoring.runs import profile_digest
from .security import current_account
from app.analytics.admission import HistoryRoute, dispatch
from .analytics_schemas import (AnalyticsResponse, AnalyticsRow, Capability,
    CapabilityResponse, Distribution, Measure, PopulationContract)

VERSION = 'company-analytics-v1'
VERSIONS = [VERSION, POLICY, FIT_POLICY_VERSION, PREVIEW_ENGINE_VERSION, DATE_POLICY,
            DEADLINE_POLICY, COUNTRY_VERSION, TAXONOMY_VERSION, LEGACY_TAXONOMY_VERSION]
MAX_EVENTS, MAX_ROWS, MAX_BYTES, MAX_RESPONSE = 500, 5000, 16 * 1024 * 1024, 2 * 1024 * 1024
MAX_SECONDS = 10
ScopeId = Annotated[int, Path(ge=1, le=9223372036854775807)]
router = APIRouter(prefix='/api/v1/organizations/{organization_id}/companies/{company_id}/analytics', tags=['company-analytics'], route_class=HistoryRoute)
UNAVAILABLE = {
    'D': 'no_authorized_immutable_current_discover_snapshot',
    'R': 'run_analytics_not_supported_account_private_provenance_required',
    'P': 'no_verified_immutable_company_profile_document_binding',
}


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


async def _authorize(request, organization_id, company_id):
    # touch=False is essential: even the session last-used timestamp is not written.
    account = await current_account(request, touch=False)
    if account is None:
        raise HTTPException(401, 'Authentication required.')
    runtime = request.app.state.runtime
    organizations = getattr(runtime, 'organization_service', None)
    companies = getattr(runtime, 'company_service', None)
    if organizations is None or companies is None:
        raise HTTPException(503, 'Authorization storage unavailable.')
    try:
        await dispatch(organizations.require_membership, account, organization_id,
                               {'owner', 'admin', 'member', 'viewer'})
        company = await dispatch(companies.get_for_organization, account.id, organization_id, company_id)
    except OrganizationError as error:
        if str(error) == 'Organization storage operation failed.':
            raise HTTPException(503, 'Authorization storage unavailable.') from None
        raise HTTPException(403, 'Company analytics access denied.') from None
    except CompanyAuthorizationError:
        raise HTTPException(403, 'Company analytics access denied.') from None
    except (CompanyRepositoryError, StorageError, sqlite3.Error, OSError, ValueError):
        raise HTTPException(503, 'Authorization storage unavailable.') from None
    if company is None:
        raise HTTPException(404, 'Company not found in authorized organization.')
    return account, company


class BoundedHistory:
    """Reuse P3.5/7; inject only a verified server cursor fence on the first call.

    At most 51 batches per load for 500 events, including verification and final
    check. No per-event lookups. Limits are checked before retaining/aggregating.
    """
    def __init__(self, repository, state, deadline):
        self.repository, self.seed, self.deadline = repository, state, deadline
        self.first, self.calls, self.bytes = True, 0, 0

    def page_discovery_history(self, *args, **kwargs):
        self.calls += 1
        if self.calls > 51 or time.monotonic() >= self.deadline:
            raise HTTPException(503, 'Analytics bounded read budget exceeded; narrow search interval.')
        if self.first and self.seed is not None:
            kwargs['state'] = dict(self.seed, after=None, read_count=0)
        self.first = False
        from app.database.analytics_read import AnalyticsReadLimits
        kwargs['read_limits'] = AnalyticsReadLimits(self.deadline, MAX_EVENTS, MAX_BYTES, 8 * 1024 * 1024)
        page = self.repository.page_discovery_history(*args, **kwargs)
        if time.monotonic() >= self.deadline:
            raise HTTPException(503, 'Analytics bounded read budget exceeded; narrow search interval.')
        if page['observed_count'] > MAX_EVENTS:
            raise HTTPException(503, 'Analytics event limit exceeded; narrow search interval.')
        for record in page['records']:
            self.bytes += sum(len(getattr(record, field).encode()) for field in
                              ('snapshot_json', 'attempted_sources_json', 'successful_sources_json', 'failed_sources_json'))
            if self.bytes > 2 * MAX_BYTES or len(record.snapshot_json.encode()) > 8 * 1024 * 1024:
                raise HTTPException(503, 'Analytics snapshot byte limit exceeded.')
        return page


def _load(repository, account, org, company, start, end, seed, deadline):
    population = load_history(BoundedHistory(repository, seed, deadline), account_id=account,
                             organization_id=org, company_id=company, start=start, end=end)
    if population.coverage != 'complete_observed_storage':
        raise HTTPException(409, 'Historical population changed during read; reload required.')
    if sum(len(getattr(event, field).encode()) for event in population.events for field in
           ('snapshot_json', 'attempted_sources_json', 'successful_sources_json', 'failed_sources_json')) > MAX_BYTES:
        raise HTTPException(503, 'Analytics population byte limit exceeded.')
    # Bind ALL stored observation bytes, not merely the tender snapshot hash.
    _check_budget(deadline)
    fingerprint = _hash([asdict(event) for event in population.events])
    _check_budget(deadline)
    return population, fingerprint


def _validate_snapshots(population, budget=None):
    occurrences = 0
    from app.analytics.resource_limits import json_cost
    remaining_cost = 200000
    for event in population.events:
        if budget is not None:
            _check_budget(budget)
        try:
            for field in ('snapshot_json', 'attempted_sources_json', 'successful_sources_json', 'failed_sources_json'):
                remaining_cost -= json_cost(getattr(event, field), maximum=remaining_cost)
            body = _json(event.snapshot_json)
            if not isinstance(body, dict) or not isinstance(body.get('items'), list):
                raise ValueError()
            # Bound nested legacy/future extras as well as the public row list.
            # An iterative walk avoids recursively validating hostile JSON.
            pending, nodes = [(body, 0)], 0
            while pending:
                value, depth = pending.pop()
                nodes += 1
                if depth > 64 or nodes > 100000:
                    raise ValueError()
                children = value.values() if isinstance(value, dict) else value if isinstance(value, list) else ()
                pending.extend((child, depth + 1) for child in children)
            occurrences += len(body['items'])
        except (ValueError, TypeError, RecursionError):
            raise HTTPException(503, 'Historical snapshot missing or corrupt; analytics unavailable.') from None
        if occurrences > MAX_ROWS:
            raise HTTPException(503, 'Analytics row limit exceeded; narrow search interval.')


def _measure(metric):
    return Measure(**{key: getattr(metric, key) for key in Measure.model_fields})


def _row(row):
    fit, current = row['historical_fit'], row['current_fit']
    return AnalyticsRow(row_id=_hash(row['identity']), identity=row['identity'], event_id=row['event_id'],
        ordinal=row['ordinal'], snapshot_sha256=row['snapshot_sha256'], historical_fit_band=fit.band,
        historical_fit_score=fit.raw_score if fit.eligible else None, historical_fit_reason=fit.reason,
        current_fit_band=current.band, current_fit_reason=current.reason)


def _check_budget(budget):
    if time.monotonic() >= budget:
        raise HTTPException(503, "Analytics time budget exceeded; narrow search interval.")


def _calculate(population, fingerprint, state, digest, timezone_name, deadline_days,
               source, country, category, fit_band, date_day, date_semantics, deadline,
               kpi, order, binding, organization_id, company_id, start, end, filters,
               cursor, page_size, key, budget):
    _check_budget(budget)
    if state and fingerprint != state['fingerprint']:
        raise HTTPException(409, 'Historical snapshots changed; reload required.')
    _validate_snapshots(population, budget)
    anchor = datetime.fromisoformat(state['as_of']) if state else datetime.now(timezone.utc)
    window = DeadlineWindow(anchor, timezone_name, deadline_days, timezone_name)
    result = aggregate_history(population, window=window, current_profile_digest=digest, checkpoint=lambda: _check_budget(budget))
    if any(semantics not in {'published_at', 'source_publication', 'release_date', 'source_update', 'deadline'}
           for semantics, _, _ in result['date_distributions']):
        raise HTTPException(503, 'Unsupported historical date semantics.')
    if result['snapshot_errors']:
        raise HTTPException(503, 'Historical snapshot missing or corrupt; analytics unavailable.')
    if len(result['U']) > MAX_ROWS or sum(e.result_count for e in population.events) > MAX_ROWS:
        raise HTTPException(503, 'Analytics row limit exceeded; narrow search interval.')
    # Never expose arbitrary persisted bodies, error strings or malformed identities.
    if any(not re.fullmatch(r'[A-Za-z0-9_.:-]{1,256}', identity[1]) or key in identity[1] for identity in result['U']):
        raise HTTPException(503, 'Historical identity cannot be safely exposed.')
    selected = set(result['U'])
    if source:
        selected &= {i for i in result['U'] if i[0] == source}
    for value, field in [(country, 'countries'), (tuple(category.split('/')) if category else None, 'categories')]:
        if value:
            selected &= set(result[field][value].identities) if value in result[field] else set()
    if fit_band:
        selected &= {r['identity'] for r in result['rows'] if r['historical_fit'].band == fit_band}
    if date_day:
        selected &= {i for (semantics, _, day), metric in result['date_distributions'].items()
                     if semantics == date_semantics and day == date_day for i in metric.identities}
    if deadline:
        selected &= set(result['kpis']['Closing Soon'].identities if deadline == 'instant_closing_soon'
                        else result['closing_soon_date_only'].identities)
    union_count = len(result['U'])
    if selected != set(result['U']):
        result = aggregate_history(population, window=window, current_profile_digest=digest,
                                   selected_identities=frozenset(selected), checkpoint=lambda: _check_budget(budget))
    # KPI is a drilldown selector over the already filtered aggregate.
    rows = list(result['rows'])
    if kpi:
        rows = [r for r in rows if r['identity'] in result['kpi_drilldown_identities'][kpi]]
    if order == 'top':
        rows = sorted((r for r in rows if r['historical_fit'].eligible),
                      key=lambda r: (-r['historical_fit'].raw_score, r['identity']))
    population_id = _hash([VERSION, result['population_id'], fingerprint, binding, digest, anchor.isoformat()])
    if state and population_id != state['population_id']:
        raise HTTPException(409, 'Population commitment changed; reload required.')
    fence = dict(fence=population.watermark, as_of=population.retrieval_as_of, observed_count=population.observed_count)
    base_state = dict(binding=binding, expires=state['expires'] if state else time.time() + 3600,
        fence_state=fence, fingerprint=fingerprint, profile_digest=digest,
        as_of=anchor.isoformat(), population_id=population_id, offset=0)
    offset = state['offset'] if cursor else 0
    page = rows[offset:offset + page_size]
    contract = PopulationContract(population_id=population_id, organization_id=organization_id, company_id=company_id,
        selected_event_ids=[e.id for e in population.events], start=start, end=end, as_of=anchor.isoformat(),
        retrieval_as_of=population.retrieval_as_of, watermark=population.watermark,
        versions=dict(analytics=POLICY, parser=DATE_POLICY, preview_engine=PREVIEW_ENGINE_VERSION,
                      **result['policies']), current_profile_digest=digest,
        timezone=timezone_name, timezone_available=window.zone is not None, deadline_days=deadline_days,
        filters=filters, coverage=result['coverage'], source_search_coverage=result['source_search_coverage'],
        observed_events=population.observed_count, union_count=union_count, filtered_count=len(result['U']),
        unknown_fit_count=sum(map(len, result['unknown_fit'].values())),
        unknowns={key: len(ids) for key, ids in result['unresolved_evidence'].items()}, exclusions=result['diagnostics'],
        capabilities={origin: Capability(state='unavailable', reason=reason) for origin, reason in UNAVAILABLE.items()})
    output = AnalyticsResponse(population=contract, population_token=seal(base_state, key),
        kpis={name: _measure(metric) for name, metric in result['kpis'].items()},
        drilldowns=result['kpi_drilldown_identities'],
        distributions={field: [Distribution(key=list(code) if isinstance(code, tuple) else [code], measure=_measure(metric))
            for code, metric in result[field].items()] for field in ('countries', 'categories', 'sources', 'fit_bands', 'date_distributions')},
        deadline_buckets=[Distribution(key=[kind, day.isoformat()], measure=Measure(value=len(ids),
            numerator=len(ids), denominator=len(result['U']), identities=list(ids), coverage=result['coverage'],
            reason=None, time_field='deadline_' + kind, unit='unique_tender_identity'))
            for kind, day, ids in result['deadline_grouping'].buckets],
        search_activity={day: [i for i in activity['identities'] if i in result['U']]
                         for day, activity in result['search_activity'].items()},
        metadata_counts={field: result['metadata_completeness'][field] for field in
            ('known_analyzed_U', 'all_U', 'present_groups', 'known_required_groups', 'all_required_groups', 'known_percent', 'all_U_percent')},
        source_observations={source_id: {field: health[field] for field in
            ('attempted', 'successful', 'failed', 'unknown', 'successful_zero', 'missing_duration',
             'duration_sample_count', 'mean_recorded_duration_ms')} for source_id, health in result['source_health'].items()},
        rows=[_row(row) for row in page], total=len(rows), order=order,
        next_cursor=seal(dict(base_state, offset=offset + page_size), key) if offset + page_size < len(rows) else None)
    encoded = output.model_dump_json().encode()
    if len(encoded) > MAX_RESPONSE or time.monotonic() >= budget:
        raise HTTPException(503, 'Analytics response or time budget exceeded; narrow search interval.')
    return encoded, fence


@router.get('/v1/capabilities/{origin}', response_model=CapabilityResponse)
async def capability(organization_id: ScopeId, company_id: ScopeId, origin: Literal['D', 'R', 'P'], request: Request, response: Response):
    await _authorize(request, organization_id, company_id)
    response.headers['Cache-Control'] = 'no-store'
    return CapabilityResponse(organization_id=organization_id, company_id=company_id, origin=origin,
                              capability=Capability(state='unavailable', reason=UNAVAILABLE[origin]))


@router.get('/v1/history/aggregate', response_model=AnalyticsResponse)
@router.get('/v1/history/rows', response_model=AnalyticsResponse)
@router.get('/v1/history/replay', response_model=AnalyticsResponse)
async def history(organization_id: ScopeId, company_id: ScopeId, request: Request, response: Response,
                  timezone_name: str, start: str | None = None, end: str | None = None,
                  source: str | None = None, country: str | None = None, category: str | None = None,
                  fit_band: Literal['low', 'medium', 'high', 'unknown'] | None = None,
                  date_semantics: str | None = None, date_day: str | None = None,
                  deadline: Literal['instant_closing_soon', 'local_date_closing_soon'] | None = None,
                  deadline_days: int = 7, page_size: int = 20, order: Literal['identity', 'top'] = 'identity',
                  kpi: Literal['Discovered', 'Matched', 'High Fit', 'Active Sources', 'Countries', 'Closing Soon'] | None = None,
                  population_token: str | None = None, cursor: str | None = None):
    if len(request.scope.get('query_string', b'')) > 16384:
        raise HTTPException(422, 'Analytics query byte limit exceeded.')
    budget = time.monotonic() + MAX_SECONDS
    account, company = await _authorize(request, organization_id, company_id)
    _check_budget(budget)
    # Reject unsupported controls instead of silently dropping AsOf/policy/forged IDs.
    allowed = set(history.__annotations__) - {'return', 'organization_id', 'company_id', 'request', 'response'}
    if set(request.query_params) - allowed or any(len(request.query_params.getlist(key)) != 1 for key in request.query_params):
        raise HTTPException(422, 'Unsupported or repeated analytics query parameter.')
    if request.url.path.endswith('/replay') and not (population_token or cursor):
        raise HTTPException(422, 'Replay requires a signed population token.')
    if cursor and population_token:
        raise HTTPException(422, 'Supply one signed token.')
    try:
        start, end = utc_filter(start), utc_filter(end)
        if (not 1 <= page_size <= 100 or not 1 <= deadline_days <= 366 or start and end and start >= end
                or not re.fullmatch(r'[A-Za-z0-9_+/-]{1,64}', timezone_name)
                or source is not None and source not in SOURCES
                or country is not None and not re.fullmatch('[A-Z]{2}', country)
                or category is not None and not re.fullmatch(r'[a-z0-9-]+/[0-9A-Za-z-]{1,32}', category)
                or (date_day is None) != (date_semantics is None)
                or date_semantics is not None and date_semantics not in {'published_at', 'source_publication', 'release_date', 'source_update', 'deadline'}):
            raise ValueError()
        if date_day:
            from datetime import date
            if date.fromisoformat(date_day).isoformat() != date_day:
                raise ValueError()
    except ValueError:
        raise HTTPException(422, 'Invalid analytics filters, interval or bounds.') from None
    key = request.app.state.api_settings.api_key
    if not key or not key.strip():
        raise HTTPException(503, 'Application signing unavailable.')
    filters = dict(source=source, country=country, category=category, fit_band=fit_band,
                   date_semantics=date_semantics, date_day=date_day, deadline=deadline, kpi=kpi)
    binding = [VERSIONS, account.id, organization_id, company_id, start, end,
               timezone_name, deadline_days, filters, page_size, order]
    try:
        state = unseal(cursor or population_token, key, binding) if cursor or population_token else None
    except CursorError:
        raise HTTPException(422, 'Invalid, expired or differently scoped analytics token.') from None
    digest = await dispatch(profile_digest, company.profile)
    if state and state['profile_digest'] != digest:
        raise HTTPException(409, 'Company profile changed; reload required.')
    repository = getattr(request.app.state.runtime, 'tender_repository', None)
    if repository is None:
        raise HTTPException(503, 'Analytics storage unavailable.')
    try:
        population, fingerprint = await dispatch(_load, repository, account.id, organization_id,
            company_id, start, end, state['fence_state'] if state else None, budget)
        encoded, fence = await dispatch(_calculate, population, fingerprint, state, digest,
            timezone_name, deadline_days, source, country, category, fit_band, date_day,
            date_semantics, deadline, kpi, order, binding, organization_id, company_id,
            start, end, filters, cursor, page_size, key, budget)
        # Final same-fence byte verification plus current session/membership/profile check.
        _, final_fingerprint = await dispatch(_load, repository, account.id, organization_id,
            company_id, start, end, fence, budget)
        if final_fingerprint != fingerprint:
            raise HTTPException(409, 'Historical snapshots changed during calculation; reload required.')
        _, final_company = await _authorize(request, organization_id, company_id)
        if await dispatch(profile_digest, final_company.profile) != digest:
            raise HTTPException(409, 'Company profile changed during read; reload required.')
        if time.monotonic() >= budget:
            raise HTTPException(503, 'Analytics time budget exceeded; narrow search interval.')
    except DatabaseAuthorizationError:
        raise HTTPException(403, 'Company analytics access denied.') from None
    except DatabaseError:
        raise HTTPException(503, 'Analytics storage unavailable.') from None
    except (ValueError, TypeError, OverflowError):
        raise HTTPException(503, 'Historical evidence invalid; analytics unavailable.') from None
    response.headers['Cache-Control'] = 'no-store'
    return Response(content=encoded, media_type="application/json", headers={"Cache-Control": "no-store"})
