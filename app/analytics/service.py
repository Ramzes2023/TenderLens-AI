"""Observed company-search analytics. No routes, source calls, scoring or writes.

Only load_history performs repository reads. Pure aggregate_history accepts its
server-owned result, never a browser population token. D and R are deliberately
distinct origins and cannot be supplied to this H implementation.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json

from pydantic import ValidationError

from app.models.tender import TenderAnalysis
from app.sources.enrichment import validate_enrichment
from .dates import DATE_POLICY, UTCInstant, stored_date
from .deadlines import DEADLINE_POLICY, DeadlinePopulation, DeadlineRow, DeadlineWindow, group_deadlines
from .fit import FIT_POLICY_VERSION, PreviewProvenance, VerifiedFitContext, classify_preliminary_fit
from .normalization import COUNTRY_VERSION
from .taxonomies import TAXONOMY_VERSION, LEGACY_TAXONOMY_VERSION
from .paging import utc_filter

POLICY = 'observed-search-analytics-v1'
# Exact persisted source IDs, not case-folded labels or adapter jurisdictions.
SOURCES = frozenset(('ted', 'eis', 'sam_gov', 'uk_fts', 'austender',
                     'za_etenders', 'canada_buys', 'nz_gets', 'india_cppp', 'kz_goszakup'))
GROUPS = ('identity', 'price', 'submission_deadline', 'contract_term', 'delivery',
          'security', 'object_quantity', 'participants', 'documents', 'technical')


def _json(raw):
    def reject(value):
        raise ValueError('Nonfinite JSON')
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(raw, parse_constant=reject, object_pairs_hook=pairs)


def _instant(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('Aware event timestamp required')
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class HistoryEvent:
    id: int
    organization_id: int
    company_id: int
    created_at: str
    result_count: int
    snapshot_json: str
    attempted_sources_json: str
    successful_sources_json: str
    failed_sources_json: str
    partial_failure: bool
    total_failure: bool


@dataclass(frozen=True)
class HistoryPopulation:
    organization_id: int
    company_id: int
    events: tuple[HistoryEvent, ...]
    watermark: int
    retrieval_as_of: str
    observed_count: int
    coverage: str
    start: str | None = None
    end: str | None = None
    origin: str = 'H'
    read_conflicts: tuple[int, ...] = ()

    def __post_init__(self):
        if self.origin != 'H' or type(self.events) is not tuple:
            raise ValueError('Immutable H population required; D/R cannot be joined')
        if (type(self.watermark) is not int or self.watermark < 0
                or type(self.observed_count) is not int or self.observed_count < 0
                or self.coverage not in {'complete_observed_storage', 'partial'}):
            raise ValueError('Explicit watermark/count/coverage required')
        if any(type(v) is not int or v <= 0 for v in (self.organization_id, self.company_id)):
            raise ValueError('Explicit scope required')
        ids = set()
        anchor = _instant(self.retrieval_as_of)
        for event in self.events:
            if not isinstance(event, HistoryEvent) or (event.organization_id, event.company_id) != (
                    self.organization_id, self.company_id):
                raise ValueError('Cross-scope event')
            if type(event.id) is not int or not 0 < event.id <= self.watermark or event.id in ids:
                raise ValueError('Invalid or duplicate fenced event')
            if type(event.result_count) is not int or event.result_count < 0:
                raise ValueError('Invalid persisted row count')
            stamp = _instant(event.created_at)
            if stamp > anchor or self.start and stamp < _instant(self.start) or self.end and stamp >= _instant(self.end):
                raise ValueError('Out-of-window event')
            ids.add(event.id)


def load_history(repository, *, account_id, organization_id, company_id,
                 start=None, end=None, batch_size=20):
    """Internal complete iterative read; no client cursor/state parameter.

    Repository reauthorizes each batch AND final count recheck. Errors (including
    revoked membership and missing storage) propagate, never turn into empty U.
    Concurrent IDs above the first fence are excluded even if backdated.
    """
    start, end = utc_filter(start), utc_filter(end)
    if start and end and start >= end:
        raise ValueError('Empty or reversed query interval')
    events, state, complete = [], None, True
    while True:
        page = repository.page_discovery_history(account_id, organization_id, company_id,
            page_size=batch_size, state=state, start=start, end=end)
        state = page['state']
        complete &= page['completeness'] == 'complete_observed_storage'
        for record in page['records']:
            events.append(HistoryEvent(**{key: getattr(record, key) for key in HistoryEvent.__dataclass_fields__}))
        if not page['has_more']:
            break
        if not page['records']:
            raise ValueError('History cursor failed to advance')
    # P3.5's count check alone misses body deletion/modification at constant count.
    # Re-read the same fence in bounded batches; compare retained observed bodies.
    # This detects drift during these reads, not storage immutability after return.
    verify_state = dict(state, after=None, read_count=0)
    verification = {}
    while True:
        checked = repository.page_discovery_history(account_id, organization_id, company_id,
            page_size=batch_size, state=verify_state, start=start, end=end)
        verify_state = checked['state']
        complete &= checked['completeness'] == 'complete_observed_storage'
        for record in checked['records']:
            verification[record.id] = HistoryEvent(**{key: getattr(record, key) for key in HistoryEvent.__dataclass_fields__})
        if not checked['has_more']:
            break
        if not checked['records']:
            raise ValueError('Verification cursor failed to advance')
    originals = {event.id: event for event in events}
    conflicts = tuple(sorted(i for i in set(originals) | set(verification)
                             if originals.get(i) != verification.get(i)))
    complete &= not conflicts
    final = repository.page_discovery_history(account_id, organization_id, company_id,
        page_size=batch_size, state=state, start=start, end=end)
    complete &= final['completeness'] == 'complete_observed_storage'
    complete &= len(events) == state['observed_count'] and not final['records']
    return HistoryPopulation(organization_id, company_id, tuple(events), state['fence'],
        state['as_of'], state['observed_count'], 'complete_observed_storage' if complete else 'partial', start, end,
        read_conflicts=conflicts)


@dataclass(frozen=True)
class Metric:
    value: int | None
    numerator: int
    denominator: int
    identities: tuple
    coverage: str
    reason: str | None
    time_field: str
    source_ids: tuple[str, ...]
    unit: str = 'unique_tender_identity'

    @property
    def share(self):
        return (self.numerator / self.denominator
                if self.denominator and self.unit == 'unique_tender_identity' else None)


def metadata_groups(analysis):
    """Exact engine.py ten-group contract, independently of fit/full scoring."""
    a = analysis
    return (bool(a.title or a.tender_number or a.customer), a.initial_price is not None,
        bool(a.submission_deadline), bool(a.contract_term), bool(a.delivery_region or a.delivery_address),
        any(v is not None for v in (a.bid_security_amount, a.bid_security_percent,
            a.contract_security_amount, a.contract_security_percent)),
        bool(a.procurement_object or a.quantity), bool(a.participant_requirements),
        bool(a.required_documents), bool(a.technical_requirements))


def aggregate_history(population: HistoryPopulation, *, window: DeadlineWindow,
                      current_profile_digest: str, top_limit=20, selected_identities=None, checkpoint=None):
    """Pure deterministic H union. Latest timestamp/ID then first ordinal wins.

    Duplicate identities in the latest event with differing bodies are excluded;
    changes between events are retained as revision/conflict diagnostics. Counts
    describe observed company searches, never market/lifetime completeness.
    """
    if not isinstance(population, HistoryPopulation) or not isinstance(window, DeadlineWindow):
        raise ValueError('Typed server-selected H and anchored window required')
    if type(top_limit) is not int or not 1 <= top_limit <= 500:
        raise ValueError('Top limit must be 1..500')
    context = VerifiedFitContext(population.organization_id, population.company_id,
                                 current_profile_digest, True)
    diagnostics = Counter()
    errors, versions, candidates, conflicted = [], defaultdict(list), {}, set()
    search, health = defaultdict(lambda: {'events': [], 'occurrences': 0,
        'returned_rows': 0, 'persisted_rows': 0, 'identities': set()}), defaultdict(list)
    complete = (population.coverage == 'complete_observed_storage'
                and len(population.events) == population.observed_count)
    source_search_complete = True
    event_manifest = []
    for event in sorted(population.events, key=lambda e: (_instant(e.created_at), e.id), reverse=True):
        if checkpoint is not None:
            checkpoint()
        event_manifest.append((event.id, event.created_at, hashlib.sha256(event.snapshot_json.encode()).hexdigest()))
        bucket = search[_instant(event.created_at).date().isoformat()]
        bucket['events'].append(event.id)
        bucket['persisted_rows'] += event.result_count
        try:
            attempted, successful, failed = [_json(getattr(event, f'{kind}_sources_json'))
                                            for kind in ('attempted', 'successful', 'failed')]
            if any(not isinstance(v, list) or any(not isinstance(s, str) or s not in SOURCES for s in v) or len(v) != len(set(v))
                   for v in (attempted, successful, failed)):
                raise ValueError('Invalid source observation lists')
            if set(successful) & set(failed) or not (set(successful) | set(failed)) <= set(attempted):
                raise ValueError('Conflicting source observations')
            if (type(event.partial_failure) is not bool or type(event.total_failure) is not bool
                    or event.partial_failure != bool(successful and failed)
                    or event.total_failure != bool(failed and not successful)):
                raise ValueError('Conflicting failure flags')
            observation_ok = True
        except (ValueError, TypeError, KeyError):
            attempted, successful, failed, observation_ok = [], [], [], False
            diagnostics['invalid_source_observation_events'] += 1
            complete = False
        if failed or set(attempted) != set(successful):
            source_search_complete = False
        try:
            if len(event.snapshot_json.encode()) > 8 * 1024 * 1024:
                raise ValueError('Snapshot exceeds explicit 8 MiB analytics read bound')
            snapshot = _json(event.snapshot_json)
            if not isinstance(snapshot, dict) or not isinstance(snapshot.get('items'), list):
                raise ValueError('Missing items')
            items = snapshot['items']
            if len(items) != event.result_count:
                diagnostics['snapshot_count_mismatch'] += 1
                complete = False
            for key, observed in [('attempted_sources', attempted), ('successful_sources', successful), ('failed_sources', failed)]:
                if key in snapshot and snapshot[key] != observed:
                    diagnostics['source_snapshot_conflict'] += 1
                    observation_ok = False
                    complete = False
        except (ValueError, TypeError, KeyError, RecursionError):
            items, snapshot = [], {}
            errors.append((event.id, 'missing_snapshot' if not event.snapshot_json.strip() else 'corrupt_snapshot'))
            complete = False
        statuses = snapshot.get('source_statuses', [])
        if not isinstance(statuses, list):
            statuses = []
        for source in attempted if observation_ok else []:
            detail = [s for s in statuses if isinstance(s, dict) and s.get('source') == source]
            status = 'success' if source in successful else 'failed' if source in failed else 'unknown'
            duration, count = None, None
            if len(detail) == 1:
                d = detail[0]
                expected = 'healthy' if status == 'success' else 'failed' if status == 'failed' else None
                if d.get('state') == expected:
                    duration = d.get('duration_ms')
                    if type(duration) is not int or duration < 0:
                        duration = None
                    count = d.get('notice_count')
                    if type(count) is not int or count < 0:
                        count = None
                else:
                    diagnostics['source_status_conflict'] += 1
            health[source].append((event.id, event.created_at, status, duration, count,
                                   event.partial_failure, event.total_failure))
        local = {}
        for ordinal, item in enumerate(items):
            if checkpoint is not None:
                checkpoint()
            diagnostics['row_occurrences'] += 1
            bucket['returned_rows'] += 1
            if not isinstance(item, dict):
                diagnostics['invalid_identity'] += 1
                complete = False
                continue
            source, external = item.get('source'), item.get('external_id')
            if not isinstance(source, str) or source not in SOURCES or not isinstance(external, str) or not external.strip() or external != external.strip():
                diagnostics['missing_identity' if source is None or external is None else 'invalid_identity'] += 1
                complete = False
                continue
            identity = (source, external)
            bucket['occurrences'] += 1
            bucket['identities'].add(identity)
            encoded = json.dumps(item, sort_keys=True, allow_nan=False)
            versions[identity].append((event.id, ordinal, encoded))
            if identity in local:
                diagnostics['duplicate_within_event'] += 1
                if local[identity][0] != encoded:
                    diagnostics['conflicting_within_event'] += 1
                    if identity not in candidates:
                        conflicted.add(identity)
            else:
                local[identity] = (encoded, ordinal, item)
        for identity, (_, ordinal, item) in local.items():
            if identity in candidates:
                diagnostics['duplicate_revisions'] += 1
            else:
                candidates[identity] = (event, ordinal, item)
    for identity in conflicted:
        candidates.pop(identity, None)
    if conflicted:
        complete = False
    # Internal server-selected predicate manifest; never deserialize client IDs.
    # Event/source observations continue to describe the selected search sample.
    if selected_identities is not None:
        if not isinstance(selected_identities, frozenset):
            raise ValueError('Immutable server-selected identity manifest required')
        candidates = {key: value for key, value in candidates.items() if key in selected_identities}
    identities = tuple(sorted(candidates))
    n = len(identities)
    coverage = 'complete_observed_storage' if complete else 'partial_observed_storage'
    population_id = hashlib.sha256(json.dumps([population.organization_id, population.company_id,
        population.watermark, population.retrieval_as_of, population.start, population.end, event_manifest],
        sort_keys=True).encode()).hexdigest()
    bands, unknown, current_unknown = defaultdict(list), defaultdict(list), defaultdict(list)
    countries, categories, sources = defaultdict(list), defaultdict(list), defaultdict(list)
    unresolved, analysis_unknown, analyses, rows, deadlines = defaultdict(list), [], {}, [], []
    metadata_conflicts = []
    date_series = defaultdict(list)
    for identity in identities:
        event, ordinal, item = candidates[identity]
        source = identity[0]
        sources[source].append(identity)
        provenance = item.get('preliminary_provenance')
        try:
            provenance = PreviewProvenance.model_validate(provenance) if provenance is not None else None
        except (ValidationError, TypeError):
            # Policy explicitly classifies malformed provenance as unknown.
            provenance = {}
        score = item.get('preliminary_scoring')
        raw_score = score.get('fit_score') if isinstance(score, dict) else None
        fit = classify_preliminary_fit(raw_score, stage=item.get('analysis_stage'), provenance=provenance,
                                       context=context, historical=True)
        current = classify_preliminary_fit(raw_score, stage=item.get('analysis_stage'), provenance=provenance,
                                           context=context)
        (bands[fit.band] if fit.eligible else unknown[fit.reason]).append(identity)
        if not current.eligible:
            current_unknown[current.reason].append(identity)
        try:
            analysis = TenderAnalysis.model_validate(item['metadata_analysis'])
            analyses[identity] = metadata_groups(analysis)
            for field in ('title', 'tender_number', 'customer', 'initial_price', 'currency'):
                direct, analyzed = item.get(field), getattr(analysis, field)
                if direct is not None and analyzed is not None and direct != analyzed:
                    metadata_conflicts.append((identity, field, direct, analyzed))
        except (KeyError, ValidationError, TypeError):
            analysis_unknown.append(identity)
        try:
            enrichment = validate_enrichment(item.get('enrichment'), *identity)
        except (ValueError, TypeError):
            enrichment = None
        country = enrichment.country if enrichment else {'codes': [], 'status': 'unavailable'}
        category = enrichment.classification if enrichment else {'memberships': [], 'status': 'unavailable'}
        for code in country['codes']:
            countries[code].append(identity)
        for membership in category['memberships']:
            categories[tuple(membership)].append(identity)
        if country['status'] not in ('verified', 'multi_country'):
            unresolved['country:' + country['status']].append(identity)
        if category['status'] != 'verified':
            unresolved['category:' + category['status']].append(identity)
        dates = enrichment.dates if enrichment else {}
        for key, field in [('publication', 'published_at'), ('deadline', 'deadline')]:
            entry = dates.get(key)
            value = stored_date(entry, source=source, path=entry.get('path', '') if isinstance(entry, dict) else '', field=field)
            if value.status == 'valid':
                day = value.parsed.utc.date() if isinstance(value.parsed, UTCInstant) else value.parsed.day
                kind = 'instant_UTC' if isinstance(value.parsed, UTCInstant) else 'date_only_source_calendar'
                date_series[(value.semantics, kind, day.isoformat())].append(identity)
            else:
                unresolved[field + ':' + value.status].append(identity)
            if field == 'deadline':
                deadlines.append(DeadlineRow(population.organization_id, population.company_id, identity, value))
        rows.append({'identity': identity, 'event_id': event.id, 'ordinal': ordinal,
            'search_created_at': event.created_at, 'snapshot_sha256': hashlib.sha256(event.snapshot_json.encode()).hexdigest(),
            'preliminary_provenance': item.get('preliminary_provenance'), 'historical_fit': fit,
            'current_fit': current, 'item': item})
    grouped = group_deadlines(DeadlinePopulation(population.organization_id, population.company_id,
                              population_id, tuple(deadlines)), window)
    eligible = sum(len(bands[b]) for b in ('low', 'medium', 'high'))
    def metric(ids, denominator=n, reason=None, time_field='discovery_search_event', unit='unique_tender_identity'):
        ids = tuple(sorted(ids))
        return Metric(None if reason else len(ids), len(ids), denominator, ids, coverage,
                      reason, time_field, tuple(sorted(sources)), unit)
    partial_reason = (None if complete else 'history_incomplete_observed_lower_bound_only')
    if not source_search_complete and partial_reason is None:
        partial_reason = 'partially_failed_observed_searches_only'
    known_countries = tuple(sorted(countries))
    succeeded = tuple(sorted(s for s, samples in health.items() if any(x[2] == 'success' for x in samples)))
    country_reason = partial_reason or ('no_supported_country_evidence' if n and not countries else None)
    # Membership is valid even when display buckets are unavailable.
    instant_ids = tuple(i for kind, state, ids in grouped.states if kind == 'instant' and state == 'closing_soon' for i in ids)
    calendar_ids = tuple(i for kind, state, ids in grouped.states if kind == 'date_only' and state == 'closing_soon' for i in ids)
    deadline_known = sum(len(ids) for kind, _, ids in grouped.states if kind == 'instant')
    deadline_reason = partial_reason or ('no_supported_instant_deadline_evidence' if n and not deadline_known else None)
    kpis = {'Discovered': metric(identities, reason=partial_reason),
        'Matched': metric(bands['medium'] + bands['high'], eligible, partial_reason or ('no_eligible_preview_scores' if n and not eligible else None)),
        'High Fit': metric(bands['high'], eligible, partial_reason or ('no_eligible_preview_scores' if n and not eligible else None)),
        'Active Sources': metric(succeeded, len(health), partial_reason or ('no_persisted_source_observations' if not any(health.values()) else None), unit='distinct_successfully_reached_source'),
        'Countries': metric(known_countries, n, country_reason, unit='distinct_supported_country'),
        'Closing Soon': metric(instant_ids, n, deadline_reason, 'deadline_UTC_instant')}
    health_output = {}
    for source in sorted(SOURCES):
        samples = health[source]
        durations = [x[3] for x in samples if x[3] is not None]
        health_output[source] = {'state': 'observed' if samples else 'unobserved', 'samples': tuple(samples),
            'attempted': len(samples), 'successful': sum(x[2] == 'success' for x in samples),
            'failed': sum(x[2] == 'failed' for x in samples), 'unknown': sum(x[2] == 'unknown' for x in samples),
            'successful_zero': sum(x[2] == 'success' and x[4] == 0 for x in samples),
            'missing_duration': len(samples) - len(durations), 'duration_sample_count': len(durations),
            'mean_recorded_duration_ms': sum(durations) / len(durations) if durations else None,
            'duration_reason': None if durations else 'no_recorded_durations',
            'interval': (min(x[1] for x in samples), max(x[1] for x in samples)) if samples else None}
    present = sum(sum(v) for v in analyses.values())
    groups = {name: {'present': sum(v[index] for v in analyses.values()),
        'denominator': len(analyses), 'missing': tuple(i for i, v in sorted(analyses.items()) if not v[index]),
        'unknown': tuple(analysis_unknown)} for index, name in enumerate(GROUPS)}
    revision_conflicts = tuple(sorted(i for i, vs in versions.items() if len({v[2] for v in vs}) > 1))
    known_value_conflicts = []
    for identity, vs in sorted(versions.items()):
        bodies = [_json(v[2]) for v in vs]
        for field in ('title', 'tender_number', 'customer', 'initial_price', 'currency',
                      'deadline', 'published_at', 'region', 'metadata_analysis'):
            values = {json.dumps(body[field], sort_keys=True) for body in bodies
                      if body.get(field) is not None}
            if len(values) > 1:
                known_value_conflicts.append((identity, field, tuple(sorted(values))))
    ranked = sorted((row for row in rows if row['historical_fit'].eligible),
                    key=lambda row: (-row['historical_fit'].raw_score, row['identity']))
    return {'policy': POLICY, 'policies': {'fit': FIT_POLICY_VERSION, 'country': COUNTRY_VERSION,
        'taxonomy_supported': (LEGACY_TAXONOMY_VERSION, TAXONOMY_VERSION), 'dates': DATE_POLICY,
        'deadline': DEADLINE_POLICY}, 'current_profile_digest': current_profile_digest,
        'origin': 'H', 'claim': 'observed company searches',
        'scope': (population.organization_id, population.company_id), 'population_id': population_id,
        'as_of': window.as_of, 'window': window, 'watermark': population.watermark,
        'retrieval_as_of': population.retrieval_as_of, 'sample_window': (population.start, population.end),
        'observed_interval': (min(_instant(e.created_at) for e in population.events),
            max(_instant(e.created_at) for e in population.events)) if population.events else None,
        'coverage': coverage, 'source_search_coverage': 'complete_attempted_samples' if source_search_complete else 'partial_failed_searches',
        'selected_events': tuple(event_manifest), 'observed_events': population.observed_count,
        'read_events': len(population.events), 'lifetime_total': None, 'U': identities, 'kpis': kpis,
        'storage_changed_event_ids': population.read_conflicts,
        'diagnostics': dict(diagnostics), 'snapshot_errors': tuple(errors), 'conflicting_identities': tuple(sorted(conflicted)),
        'revision_conflicts': revision_conflicts, 'revision_known_value_conflicts': tuple(known_value_conflicts),
        'revisions': {i: tuple(v) for i, v in sorted(versions.items())},
        'fit_bands': {b: metric(bands[b], eligible) for b in ('low', 'medium', 'high')},
        'unknown_fit': {reason: tuple(ids) for reason, ids in sorted(unknown.items())},
        'current_fit_unknown': {reason: tuple(ids) for reason, ids in sorted(current_unknown.items())},
        'countries': {code: metric(ids) for code, ids in sorted(countries.items())},
        'categories': {code: metric(ids) for code, ids in sorted(categories.items())},
        'sources': {source: metric(ids) for source, ids in sorted(sources.items())},
        'membership_overlap': {'country': sum(map(len, countries.values())) - len({i for ids in countries.values() for i in ids}),
            'category': sum(map(len, categories.values())) - len({i for ids in categories.values() for i in ids})},
        'unresolved_evidence': {key: tuple(ids) for key, ids in sorted(unresolved.items())},
        'industry': {'value': None, 'reason': 'no_supported_industry_crosswalk', 'denominator': n},
        'deadline_grouping': grouped, 'closing_soon_date_only': metric(calendar_ids, n,
            partial_reason or ('display_timezone_unavailable' if grouped.timezone_status != 'available' else None), 'deadline_local_calendar'),
        'date_distributions': {key: metric(ids, n, time_field=key[0]) for key, ids in sorted(date_series.items())},
        'search_activity': {day: {'event_ids': tuple(sorted(v['events'])), 'row_occurrences': v['returned_rows'],
            'valid_identity_occurrences': v['occurrences'], 'persisted_result_count': v['persisted_rows'],
            'identities': tuple(sorted(v['identities'])), 'coverage': coverage, 'timezone': 'UTC'} for day, v in sorted(search.items())},
        'metadata_conflicts': tuple(metadata_conflicts),
        'enrichment_coverage': {'country_known_U': len({i for ids in countries.values() for i in ids}),
            'category_known_U': len({i for ids in categories.values() for i in ids}),
            'publication_known_U': len({i for key, ids in date_series.items() if key[0] == 'published_at' for i in ids}),
            'deadline_known_U': sum(len(ids) for kind, state, ids in grouped.states if kind != 'unknown' and state != 'unavailable'),
            'denominator': n},
        'metadata_completeness': {'known_analyzed_U': len(analyses), 'all_U': n,
            'present_groups': present, 'known_required_groups': 10 * len(analyses), 'all_required_groups': 10 * n,
            'known_percent': 100 * present / (10 * len(analyses)) if analyses else None,
            'all_U_percent': 100 * present / (10 * n) if n and len(analyses) == n else None,
            'coverage': 'known' if len(analyses) == n else 'partial_unknown', 'unknown': tuple(analysis_unknown),
            'groups': groups, 'stage': 'metadata_analysis', 'full_document_completeness': None},
        'source_health': health_output,
        'kpi_drilldown_identities': {'Discovered': identities,
            'Matched': tuple(sorted(bands['medium'] + bands['high'])), 'High Fit': tuple(bands['high']),
            'Active Sources': tuple(i for i in identities if i[0] in succeeded),
            'Countries': tuple(sorted({i for ids in countries.values() for i in ids})),
            'Closing Soon': tuple(sorted(instant_ids))},
        'top_opportunities': tuple(ranked[:top_limit]),
        'top_total': len(ranked), 'rows': tuple(rows), 'monetary_aggregate': {'value': None,
            'reason': 'no_cross_currency_or_incomplete_value_aggregate'},
        'drilldown_capability': 'pure_identity_manifest_only_P3.8_required'}
