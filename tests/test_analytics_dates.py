"""Offline boundary/evidence/identity acceptance; no source requests."""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import importlib
import json

import pytest

from app.analytics.dates import CalendarDate, UTCInstant, NormalizedDate, normalize_date, stored_date
from app.analytics.deadlines import (DeadlineWindow, DeadlineRow, DeadlinePopulation,
                                    deadline_decision, filter_deadlines, group_deadlines)
from app.sources.enrichment import NoticeEnrichment, validate_enrichment

UTC = timezone.utc
AS_OF = datetime(2026, 10, 11, 12, tzinfo=UTC)


def normalized(raw, source='sam_gov', path='responseDeadLine', field='deadline'):
    return normalize_date(raw, source=source, path=path, field=field)


@pytest.mark.parametrize('raw,status,kind', [
    (None, 'missing', None), ('', 'missing', None), ('  ', 'missing', None),
    (0, 'invalid', None), (False, 'invalid', None), ({}, 'invalid', None),
    ('2024-02-29', 'valid', CalendarDate), ('2023-02-29', 'invalid', None),
    ('2026-13-01', 'invalid', None), ('2026-04-31', 'invalid', None),
    ('2026-10-11T12:00:00Z', 'valid', UTCInstant),
    ('2026-10-11T12:00:00.123456+05:30', 'valid', UTCInstant),
    ('2026-10-11T12:00:00.1-05:00', 'valid', UTCInstant),
    ('2026-10-11 12:00:00', 'ambiguous', None),
    ('2026-10-11T12:00', 'ambiguous', None),
    ('2026-10-11T25:00:00Z', 'invalid', None),
    ('2026-10-11T12:00:60Z', 'invalid', None),
    ('2026-10-11T12:00:00+01:60', 'invalid', None),
    ('2026-10-11T12:00:00+24:00', 'invalid', None),
    ('2026-10-11T12:00:00-00:00', 'ambiguous', None),
    ('2026-10-11T12:00:00.1234567Z', 'unsupported', None),
    ('11.10.2026', 'unsupported', None), ('10/11/2026', 'unsupported', None),
    ('tomorrow', 'unsupported', None), ('20261011', 'unsupported', None),
    ('2026-1-01', 'invalid', None), ('2026-10-11T12:00Z trailing', 'invalid', None),
])
def test_parse_contract(raw, status, kind):
    result = normalized(raw)
    assert result.raw == raw
    assert result.status == status
    assert type(result.parsed) is kind if kind else result.parsed is None
    assert normalized(raw) == result
    if kind is CalendarDate:
        assert result.offset_seconds is None and result.timezone_evidence is None


@pytest.mark.parametrize('offset,hours', [('Z', 0), ('+02:00', -2), ('-05:00', 5)])
def test_fractional_exact_utc(offset, hours):
    result = normalized('2026-10-11T12:00:00.123456' + offset)
    assert result.parsed.utc == AS_OF + timedelta(hours=hours, microseconds=123456)
    assert result.precision == 'fraction_6'
    assert result.offset_seconds == -hours * 3600


@pytest.mark.parametrize('source,path,status', [('eis', 'description.deadline', 'valid'),
    ('eis', 'pubDate', 'invalid'), ('sam_gov', 'responseDeadLine', 'unsupported'),
    ('eis', 'other', 'unsupported'), ('ted', 'deadline', 'unsupported')])
def test_dd_mm_only_evidenced_path(source, path, status):
    assert normalized('29.02.2024', source, path).status == status


def test_eis_naive_leap_and_invalid():
    assert normalized('29.02.2024 18:00', 'eis', 'description.deadline').status == 'ambiguous'
    assert normalized('29.02.2023', 'eis', 'description.deadline').status == 'invalid'


@pytest.mark.parametrize('source,path,raw,status', [
    ('india_cppp', 'listing.Bid Submission End Date', '05-Oct-2026 09:00 AM', 'valid'),
    ('india_cppp', 'other', '05-Oct-2026 09:00 AM', 'unsupported'),
    ('za_etenders', 'closing_Date', '2026-10-11T12:00:00', 'valid'),
    ('za_etenders', 'other', '2026-10-11T12:00:00', 'ambiguous'),
    ('austender', 'detail.TimeZone.CloseDateTime', '10/05/2026 12:00:00', 'ambiguous'),
    ('austender', 'detail.Close Date & Time', '5-Oct-2026 12:00 pm (ACT Local Time)', 'ambiguous'),
    ('austender', 'detail.Publish Date', '24-Sep-2026', 'valid'),
    ('nz_gets', 'item.description.Close date', 'Tuesday, 20 October 2026 12:00 PM +1300', 'valid'),
    ('nz_gets', 'item.pubDate', 'Thu, 24 Sep 2026 00:00:00 GMT', 'valid'),
    ('nz_gets', 'item.pubDate', 'Thu, 24 Sep 2026 00:00:00 +0060', 'invalid'),
    ('nz_gets', 'item.pubDate', 'Thu, 24 Sep 2026 00:00:00 -0000', 'ambiguous'),
    ('india_cppp', 'listing.Bid Submission End Date', '05-Oct-2026 09:00', 'invalid'),
    ('kz_goszakup', 'end_date', '2026-10-20 18:00:00', 'ambiguous'),
    ('canada_buys', 'tenderClosingDate-appelOffresDateCloture', '2029-03-31T13:00:00', 'ambiguous'),
])
def test_documented_contexts(source, path, raw, status):
    assert normalized(raw, source, path).status == status


def test_arrays_preserve_evidence_without_selecting_multiple_deadlines():
    raw = ['2026-10-12', '2026-10-13']
    assert normalized(raw, 'ted', 'deadline').status == 'ambiguous'
    one = normalized(raw[:1], 'ted', 'deadline')
    assert one.raw == raw[:1] and one.parsed.day == date(2026, 10, 12)
    assert normalized(raw[:1]).status == 'ambiguous'


@pytest.mark.parametrize('delta,status,included', [(-1, 'expired', False),
    (0, 'closing_soon', True), (1, 'closing_soon', True),
    (7 * 86400 * 1000000 - 1, 'closing_soon', True),
    (7 * 86400 * 1000000, 'future', False), (8 * 86400 * 1000000, 'future', False)])
def test_half_open_boundaries(delta, status, included):
    value = normalized((AS_OF + timedelta(microseconds=delta)).isoformat())
    result = deadline_decision(value, DeadlineWindow(AS_OF, 'UTC'))
    assert (result.kind, result.status, result.included) == ('instant', status, included)


@pytest.mark.parametrize('days', [0, -1, 367, True, 7.0, '7', None])
def test_window_validation(days):
    with pytest.raises(ValueError):
        DeadlineWindow(AS_OF, 'UTC', days)


def test_no_implicit_clock_or_timezone():
    with pytest.raises(ValueError):
        DeadlineWindow(AS_OF.replace(tzinfo=None), 'UTC')
    with pytest.raises(ValueError):
        DeadlineWindow(datetime.max.replace(tzinfo=UTC), 'UTC')
    with pytest.raises(ValueError):
        deadline_decision(normalized('2026-10-11', field='published_at'), DeadlineWindow(AS_OF, 'UTC'))
    assert DeadlineWindow(AS_OF.astimezone(timezone(timedelta(hours=2))), 'UTC').as_of == AS_OF


@pytest.mark.parametrize('zone', ['not/a/zone', '+02:00', 'CET invented', '../UTC'])
def test_timezone_unavailable(zone):
    window = DeadlineWindow(AS_OF, zone, request_timezone='Europe/Rome')
    assert window.request_timezone == 'Europe/Rome' and window.display_timezone == zone
    assert deadline_decision(normalized('2026-10-12'), window).status == 'unavailable'
    decision = deadline_decision(normalized('2026-10-12T00:00:00Z'), window)
    assert decision.included and decision.bucket is None
    assert decision.reason == 'display_timezone_unavailable'


def test_missing_zoneinfo_data(monkeypatch):
    from zoneinfo import ZoneInfoNotFoundError
    import app.analytics.deadlines as policy
    def unavailable(_):
        raise ZoneInfoNotFoundError('offline Windows')
    monkeypatch.setattr(policy, 'ZoneInfo', unavailable)
    assert deadline_decision(normalized('2026-10-12'), DeadlineWindow(AS_OF, 'Europe/Rome')).status == 'unavailable'


@pytest.mark.parametrize('anchor,local_day,offset', [
    ('2026-03-29T00:30:00Z', '2026-03-29', 1),
    ('2026-03-29T01:30:00Z', '2026-03-29', 2),
    ('2026-10-25T00:30:00Z', '2026-10-25', 2),
    ('2026-10-25T01:30:00Z', '2026-10-25', 1),
    ('2026-10-24T22:30:00Z', '2026-10-25', 2),
    ('2026-03-28T23:30:00Z', '2026-03-29', 1),
])
def test_dst_and_local_day(anchor, local_day, offset):
    window = DeadlineWindow(datetime.fromisoformat(anchor), 'Europe/Rome', 1)
    if window.zone is None:
        # Test explicit unavailable capability, not a skip or fictitious DST offset.
        assert deadline_decision(normalized(local_day), window).status == 'unavailable'
        return
    assert window.as_of.astimezone(window.zone).utcoffset() == timedelta(hours=offset)
    day = date.fromisoformat(local_day)
    for delta, expected in [(-1, 'expired'), (0, 'closing_soon'), (1, 'future')]:
        decision = deadline_decision(normalized((day + timedelta(days=delta)).isoformat()), window)
        assert decision.kind == 'date_only' and decision.status == expected
        assert decision.included == (delta == 0)
    # Timestamp W is elapsed UTC time, independent of DST calendar-day length.
    assert not deadline_decision(normalized((window.as_of + timedelta(days=1)).isoformat()), window).included


def population(values):
    return DeadlinePopulation(1, 2, 'selected-fixture', tuple(
        DeadlineRow(1, 2, ('sam_gov', str(i)), normalized(value)) for i, value in enumerate(values)))


def test_group_filter_cells_and_double_count():
    pop = population(['2026-10-12', '2026-10-12T16:00:00Z', None, 'bad',
                      '2026-10-01', '2026-10-20', '2026-10-12T16:00:00'])
    pop = replace(pop, rows=pop.rows + (pop.rows[0], pop.rows[1]))
    window = DeadlineWindow(AS_OF, 'UTC')
    grouped = group_deadlines(pop, window)
    assert grouped.selected == filter_deadlines(pop, window)
    assert grouped.duplicate_count == 2
    assert sum(len(ids) for _, _, ids in grouped.states) == 7
    if window.zone:
        assert len(grouped.selected) == 2
        assert sum(len(ids) for _, _, ids in grouped.buckets) == 2
        for kind, day, identities in grouped.buckets:
            assert filter_deadlines(pop, window, bucket=day, kind=kind) == identities
    conflict = replace(pop.rows[0], deadline=normalized('2026-10-13'))
    changed = replace(pop, rows=pop.rows + (conflict,))
    assert group_deadlines(changed, window).conflicting == (('sam_gov', '0'),)
    assert ('sam_gov', '0') not in filter_deadlines(changed, window)


def test_unavailable_heatmap_is_not_an_empty_verified_population():
    pop = population(['2026-10-12T16:00:00Z', '2026-10-12'])
    window = DeadlineWindow(AS_OF, 'not/a/zone')
    grouped = group_deadlines(pop, window)
    assert grouped.selected == (('sam_gov', '0'),)
    assert grouped.unbucketed == ((('sam_gov', '0'), 'display_timezone_unavailable'),)
    assert grouped.timezone_status == 'unavailable'
    assert ('date_only', 'unavailable', (('sam_gov', '1'),)) in grouped.states
    with pytest.raises(ValueError):
        filter_deadlines(pop, window, bucket=date(2026, 10, 12))


def test_display_overflow_preserves_instant_membership():
    # Real fixed-offset IANA data, no invented timezone fallback.
    window = DeadlineWindow(datetime(9999, 12, 30, 12, tzinfo=UTC), 'Etc/GMT-14', 1)
    if window.zone is None:
        assert window.zone is None
        return
    value = normalized('9999-12-31T00:00:00Z')
    assert deadline_decision(value, window).included
    assert deadline_decision(normalized('9999-12-31'), window).status == 'unavailable'


@pytest.mark.parametrize('org,company', [(3, 2), (1, 4), (3, 4)])
def test_scope_integrity_fails_before_filtering(org, company):
    pop = population(['2026-10-12'])
    with pytest.raises(ValueError):
        replace(pop, rows=(replace(pop.rows[0], organization_id=org, company_id=company),))


def test_legacy_and_future_policy_no_upgrade():
    entry = {'path': 'responseDeadLine', 'value': '2026-10-12T16:00:00Z'}
    args = dict(source='sam_gov', path=entry['path'], field='deadline')
    assert stored_date(entry, **args).status == 'unsupported'
    entry['normalized'] = normalized(entry['value']).model_dump(mode='json')
    assert stored_date(entry, **args).status == 'valid'
    entry['normalized']['version'] = 'future-policy'
    assert stored_date(entry, **args).status == 'unsupported'
    entry['normalized'] = normalized('2026-10-13').model_dump(mode='json')
    assert stored_date(entry, **args).reason == 'stored_evidence_mismatch'


def test_typed_contract_rejects_fictional_instant():
    with pytest.raises(ValueError):
        UTCInstant(utc=AS_OF.replace(tzinfo=None))
    with pytest.raises(ValueError):
        NormalizedDate.model_validate({
            **normalized('2026-10-12').model_dump(), 'offset_seconds': 0})
    with pytest.raises(ValueError):
        CalendarDate(day='2026-10-11T00:00:00Z')


def test_local_midnight_and_calendar_window_end():
    before = DeadlineWindow(datetime(2026, 10, 10, 21, 59, 59, tzinfo=UTC), 'Europe/Rome')
    after = replace(before, as_of=before.as_of + timedelta(seconds=1))
    if before.zone is None:
        assert deadline_decision(normalized('2026-10-10'), before).status == 'unavailable'
        return
    assert deadline_decision(normalized('2026-10-10'), before).included
    assert deadline_decision(normalized('2026-10-10'), after).status == 'expired'
    assert deadline_decision(normalized('2026-10-17'), before).status == 'future'
    assert deadline_decision(normalized('2026-10-17'), after).included
    assert deadline_decision(normalized('2026-10-18'), after).status == 'future'


def test_dst_fold_distinct_instants_one_bucket():
    pop = population(['2026-10-25T02:30:00+02:00', '2026-10-25T02:30:00+01:00'])
    window = DeadlineWindow(datetime(2026, 10, 24, 12, tzinfo=UTC), 'Europe/Rome')
    grouped = group_deadlines(pop, window)
    assert len(grouped.selected) == 2
    if window.zone:
        assert grouped.buckets == (('instant', date(2026, 10, 25), (('sam_gov', '0'), ('sam_gov', '1'))),)
        assert filter_deadlines(pop, window, bucket=date(2026, 10, 25)) == grouped.selected


def test_pure_runtime_has_no_io_scoring_or_mutation(monkeypatch):
    import socket
    import app.scoring.preview as scoring
    def forbidden(*args, **kwargs):
        raise AssertionError('Pure predicates must not perform IO or scoring')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(scoring, 'score_metadata_preview', forbidden)
    pop = population(['2026-10-12', '2026-10-12T12:00:00Z', None])
    original = tuple(row.deadline.model_dump(mode='json') for row in pop.rows)
    window = DeadlineWindow(AS_OF, 'UTC')
    first = group_deadlines(pop, window)
    assert group_deadlines(pop, window) == first
    assert filter_deadlines(pop, window) == first.selected
    assert tuple(row.deadline.model_dump(mode='json') for row in pop.rows) == original


@pytest.mark.parametrize('field', ['published_at', 'discovery_search_event', 'scoring_calculation', 'source_sync_observation'])
def test_time_semantics_never_used_as_deadline(field):
    raw = ' 2026-10-11T12:00:00Z '
    value = normalized(raw, field=field)
    assert value.field == field and value.raw == raw
    with pytest.raises(ValueError):
        deadline_decision(value, DeadlineWindow(AS_OF, 'UTC'))


_SOURCE_TESTS = [
    ('sam_gov', 'test_sam_gov_source', 'parse_sam_gov_response', 'test_parse_sam_gov_response_normalizes_opportunity', 'valid'),
    ('ted', 'test_ted_source', 'parse_ted_search_response', 'test_parse_ted_search_response_normalizes_notice', 'valid'),
    ('uk_fts', 'test_uk_fts_source', 'parse_uk_fts_response', 'test_parse_uk_fts_normalizes_realistic_release', 'valid'),
    ('canadabuys', 'test_canada_buys_source', 'parse_canadabuys_csv', 'test_parse_canadabuys_normalizes_notice', 'ambiguous'),
    ('nz_gets', 'test_nz_gets_source', 'parse_nz_gets_rss', 'test_parser_normalizes_gets_notice', 'valid'),
    ('india_cppp', 'test_india_cppp_source', 'parse_india_cppp_listing', 'test_parser_normalizes_cppp_tender', 'valid'),
    ('za_etenders', 'test_za_etenders_source', 'parse_za_etenders_response', 'test_parser_normalizes_active_tender', 'valid'),
    ('kz_goszakup', 'test_kz_goszakup_source', 'parse_kz_goszakup_response', 'test_parser_normalizes_kazakhstan_announcement', 'ambiguous'),
]


@pytest.mark.parametrize('source,module,parser,test_name,status', _SOURCE_TESTS)
def test_existing_source_fixtures_and_replay(monkeypatch, source, module, parser, test_name, status):
    fixture = importlib.import_module('tests.' + module)
    original = getattr(fixture, parser)
    captured = []
    def capture(*args, **kwargs):
        result = original(*args, **kwargs)
        captured.extend(result)
        return result
    monkeypatch.setattr(fixture, parser, capture)
    getattr(fixture, test_name)()  # Preserves original legacy-field assertions too.
    assert captured
    for notice in captured:
        publication = notice.enrichment['dates']['publication']
        assert publication['normalized']['status'] == ('ambiguous' if notice.source == 'kz_goszakup' else 'valid')
        entry = notice.enrichment['dates']['deadline']
        value = stored_date(entry, source=notice.source, path=entry['path'], field='deadline')
        assert value.status == status
        validate_enrichment(notice.enrichment, notice.source, notice.external_id)
        assert NoticeEnrichment.model_validate_json(json.dumps(notice.enrichment)).model_dump() == notice.enrichment
        pop = DeadlinePopulation(1, 2, 'fixture', (DeadlineRow(1, 2, notice.identity, value),))
        window = DeadlineWindow(AS_OF, 'UTC', 366)
        for kind, day, identities in group_deadlines(pop, window).buckets:
            assert filter_deadlines(pop, window, bucket=day, kind=kind) == identities


def test_austender_and_eis_remaining_fixture_evidence():
    from app.sources.austender_rss import parse_austender_detail_page, AUSTENDER_ATM_BASE_URL
    from tests.test_austender_source import _detail_html, UUID_1
    from app.sources.eis_rss import parse_eis_feed
    from tests.test_monitoring import RSS
    aus = parse_austender_detail_page(_detail_html(), external_id=UUID_1,
        url=AUSTENDER_ATM_BASE_URL + UUID_1, rss_title='ISO 9001 Certification Services')
    assert aus.enrichment['dates']['deadline']['normalized']['status'] == 'ambiguous'
    assert aus.enrichment['dates']['publication']['normalized']['status'] == 'valid'
    eis = parse_eis_feed(RSS)[0]
    assert eis.enrichment['dates']['deadline']['normalized']['status'] == 'ambiguous'
    assert eis.enrichment['dates']['publication']['path'] == 'pubdate'
    assert eis.enrichment['dates']['publication']['normalized']['status'] == 'valid'


def test_forged_normalized_evidence_rejected_and_legacy_retained():
    from tests.test_analytics_normalization import sam
    notice = sam()
    data = json.loads(json.dumps(notice.enrichment))
    data['dates']['deadline']['normalized']['offset_seconds'] = 0
    with pytest.raises(ValueError):
        NoticeEnrichment.model_validate(data)
    future = json.loads(json.dumps(notice.enrichment))
    future['dates']['deadline']['normalized']['version'] = 'future-policy'
    assert NoticeEnrichment.model_validate(future).model_dump() == future
    future_entry = future['dates']['deadline']
    assert stored_date(future_entry, source=notice.source, path=future_entry['path'], field='deadline').status == 'unsupported'
    for entry in data['dates'].values():
        entry.pop('normalized')
    assert NoticeEnrichment.model_validate(data).model_dump() == data
