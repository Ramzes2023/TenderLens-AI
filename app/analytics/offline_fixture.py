"""Fixed P39D fixture adapter, NOT an authorization or general request adapter.

Only repository-pinned test bytes are accepted. No membership/trusted-origin flag
is accepted from a caller. Deliberately unusable for live history or HTTP input.
"""
import hashlib
import json
from pathlib import Path

INPUT_LIMIT = 48 * 1024
OUTPUT_LIMIT = 24 * 1024
FIXTURE_SHA256 = '6d7ff62145ca4c05388d988419ccd4343c269e842c0614bab0ea3edbdbbccfaf'
FIXTURE = Path(__file__).resolve().parents[2] / 'tests/fixtures/p39d_offline_history.json'
CASES = ('normal', 'empty', 'unknown', 'legacy', 'foreign', 'future', 'filtered')


class FixtureError(RuntimeError):
    pass


def stable(value):
    from datetime import date, datetime
    def dates(obj):
        if type(obj) in (date, datetime):
            return obj.isoformat()
        raise TypeError('unsupported_output_type')
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False,
                      default=dates).encode()


def strict(raw):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError()
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))


def fixture_payload(case):
    if type(case) is not str or case not in CASES:
        raise FixtureError('fixture_only')
    with FIXTURE.open('rb') as stream:
        raw = stream.read(INPUT_LIMIT + 1)
    if len(raw) > INPUT_LIMIT or hashlib.sha256(raw).hexdigest() != FIXTURE_SHA256:
        raise FixtureError('fixture_commitment')
    data = strict(raw)
    # Scope checks precede constructing the server-only HistoryPopulation.
    event = data['cases']['normal' if case == 'filtered' else case]
    if (data['organization_id'], data['company_id']) != (7, 33) or (
            event['organization_id'], event['company_id']) != (7, 33):
        raise FixtureError('fixture_scope')
    return {'v': 1, 'fixture_sha256': FIXTURE_SHA256, 'case': case,
            'context': {k: data[k] for k in ('organization_id', 'company_id',
                'profile_digest', 'as_of', 'timezone', 'days', 'start', 'end')},
            'events': [event],
            'selected_identities': [['ted', 'zero']] if case == 'filtered' else None}


def validate_payload(raw):
    try:
        if type(raw) is not bytes or len(raw) > INPUT_LIMIT:
            raise ValueError()
        value = strict(raw)
        if type(value) is not dict or type(value.get('v')) is not int or value['v'] != 1:
            raise ValueError()
        expected = fixture_payload(value.get('case'))
        # Exact bytes after strict canonicalization reject extra fields, booleans
        # for integers, overflow, duplicates, foreign scope, altered provenance,
        # filters and scoring. This is a fixed fixture allowlist, not trust in JSON.
        if stable(value) != stable(expected):
            raise ValueError()
        return value
    except (ValueError, TypeError, KeyError, RecursionError, UnicodeError, FixtureError):
        raise FixtureError('invalid_fixture_input') from None


def calculate(payload):
    """Reuse existing H policy; no HTTP imports, DB reads or rescoring in worker."""
    from dataclasses import asdict
    from datetime import datetime
    from .service import HistoryEvent, HistoryPopulation, aggregate_history
    from .deadlines import DeadlineWindow
    data = validate_payload(stable(payload))
    c = data['context']
    events = tuple(HistoryEvent(**event) for event in data['events'])
    population = HistoryPopulation(c['organization_id'], c['company_id'], events,
        1, c['as_of'], len(events), 'complete_observed_storage', c['start'], c['end'])
    window = DeadlineWindow(datetime.fromisoformat(c['as_of']), c['timezone'], c['days'], c['timezone'])
    result = aggregate_history(population, window=window,
        current_profile_digest=c['profile_digest'],
        selected_identities=None if data['selected_identities'] is None else
            frozenset(tuple(i) for i in data['selected_identities']))
    # Explicit output allowlist excludes stored items, source errors, URLs/titles,
    # API tokens and any raw unknown scores. JSON conversion is deterministic.
    output = {k: result[k] for k in ('population_id', 'scope', 'origin', 'coverage',
        'source_search_coverage', 'selected_events', 'U', 'unknown_fit',
        'current_fit_unknown', 'current_profile_digest', 'sample_window',
        'retrieval_as_of', 'observed_events', 'policies')}
    output['context'] = c
    output['selected_identities'] = data['selected_identities']
    output['kpis'] = {k: asdict(v) for k, v in result['kpis'].items()}
    output['fit_bands'] = {k: asdict(v) for k, v in result['fit_bands'].items()}
    output['closing_soon_date_only'] = asdict(result['closing_soon_date_only'])
    output['deadline_grouping'] = asdict(result['deadline_grouping'])
    output['fits'] = [{'identity': row['identity'],
        'historical_band': row['historical_fit'].band,
        'current_band': row['current_fit'].band,
        'current_reason': row['current_fit'].reason} for row in result['rows']]
    raw = stable(output)
    if len(raw) > OUTPUT_LIMIT:
        raise FixtureError('fixture_output_limit')
    return strict(raw)
