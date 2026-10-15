"""Pure date evidence policy. No clock, storage, authorization or source IO."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

DATE_POLICY = 'source-date-v1'
DateStatus = Literal['valid', 'missing', 'invalid', 'ambiguous', 'unsupported']
TimeField = Literal['published_at', 'deadline', 'discovery_search_event',
                    'scoring_calculation', 'source_sync_observation']


class CalendarDate(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')
    kind: Literal['calendar_date'] = 'calendar_date'
    day: date

    @field_validator('day', mode='before')
    @classmethod
    def validate_day(cls, value):
        if type(value) is date or isinstance(value, str) and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
            return value
        raise ValueError('A calendar date cannot be supplied as a timestamp.')


class UTCInstant(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')
    kind: Literal['utc_instant'] = 'utc_instant'
    utc: datetime

    @model_validator(mode='after')
    def validate_utc(self):
        if self.utc.tzinfo is None or self.utc.utcoffset() != timedelta(0):
            raise ValueError('UTC aware instant required.')
        return self


class NormalizedDate(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')
    version: Literal['source-date-v1'] = DATE_POLICY
    source: str
    path: str
    field: TimeField
    semantics: str
    raw: Any
    status: DateStatus
    parsed: CalendarDate | UTCInstant | None = None
    precision: str | None = None
    timezone_evidence: str | None = None
    offset_seconds: int | None = None
    reason: str | None = None

    @model_validator(mode='after')
    def validate_precision(self):
        if (self.status == 'valid') != (self.parsed is not None):
            raise ValueError('Only valid evidence has a parsed value.')
        if isinstance(self.parsed, CalendarDate) and (
                self.precision != 'day' or self.offset_seconds is not None or self.timezone_evidence is not None):
            raise ValueError('Calendar dates cannot carry an invented offset.')
        if isinstance(self.parsed, UTCInstant) and (
                self.offset_seconds is None or self.timezone_evidence is None or self.precision is None):
            raise ValueError('Instant precision and timezone evidence required.')
        return self


_DATE = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}\Z')
_ISO = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}'
                  r'(?::[0-9]{2}(?:\.([0-9]+))?)?(Z|[+-][0-9]{2}:[0-9]{2})?\Z')
_MONTHS = {name.casefold(): i for i, name in enumerate(
    ('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
     'September', 'October', 'November', 'December'), 1)}
_MONTHS.update({name[:3]: number for name, number in list(_MONTHS.items())})


def _english(value: str) -> str:
    # Locale-independent English month and weekday conversion for evidenced feeds.
    value = re.sub(r'^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s*', '', value)
    return re.sub(r'[A-Za-z]+', lambda m: f'{_MONTHS[m[0].casefold()]:02d}'
                  if m[0].casefold() in _MONTHS else m[0], value)


def _clock12(value: str) -> str:
    """Convert English AM/PM without depending on process locale."""
    def replace(match):
        hour = int(match[1])
        if not 1 <= hour <= 12:
            raise ValueError('Invalid 12-hour clock.')
        hour = hour % 12 + (12 if match[3].casefold() == 'pm' else 0)
        return f'{hour:02d}:{match[2]}'
    return re.sub(r'([0-9]{1,2}):([0-9]{2})\s+([AaPp][Mm])', replace, value)


def normalize_date(raw: Any, *, source: str, path: str, field: TimeField,
                   semantics: str | None = None) -> NormalizedDate:
    """Only exact evidence contexts enable non-ISO formats or local timezone policy."""
    base = dict(source=source, path=path, field=field, semantics=semantics or field, raw=raw)

    def result(status, **kwargs):
        return NormalizedDate(**base, status=status, **kwargs)

    if raw is None or isinstance(raw, str) and not raw.strip():
        return result('missing')
    value = raw
    if isinstance(value, list):
        # TED's existing list fields: only one scalar can establish one date.
        if source != 'ted' or len(value) != 1:
            return result('ambiguous', reason='multiple_or_unverified_values')
        value = value[0]
    if not isinstance(value, str):
        return result('invalid', reason='expected_text')
    value = value.strip()
    if not value:
        return result('missing')
    if _DATE.fullmatch(value):
        try:
            return result('valid', parsed=CalendarDate(day=date.fromisoformat(value)), precision='day')
        except ValueError:
            return result('invalid', reason='invalid_calendar_date')
    parsed = None
    precision = 'second'
    zone_evidence = None
    match = _ISO.fullmatch(value)
    if match is None and re.match(r'[0-9]{4}-[0-9]', value):
        return result('invalid', reason='malformed_iso_date')
    try:
        if match:
            fraction, offset = match.groups()
            if fraction and len(fraction) > 6:
                return result('unsupported', reason='fraction_exceeds_microsecond_precision')
            if offset == '-00:00':
                return result('ambiguous', reason='unknown_offset_minus_zero')
            if offset and offset != 'Z' and (int(offset[1:3]) > 23 or int(offset[4:]) > 59):
                return result('invalid', reason='invalid_offset')
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            precision = f'fraction_{len(fraction)}' if fraction else 'second' if value[16:17] == ':' else 'minute'
            if offset:
                zone_evidence = f'explicit_offset:{offset}'
            elif source == 'za_etenders' and path in {'date_Published', 'closing_Date'}:
                parsed = parsed.replace(tzinfo=timezone(timedelta(hours=2)))
                zone_evidence = 'adapter_policy:SAST:+02:00'
        elif source == 'eis' and path == 'description.deadline':
            if re.fullmatch(r'[0-9]{2}\.[0-9]{2}\.[0-9]{4}', value):
                return result('valid', parsed=CalendarDate(day=datetime.strptime(value, '%d.%m.%Y').date()), precision='day')
            if re.fullmatch(r'[0-9]{2}\.[0-9]{2}\.[0-9]{4} [0-9]{2}:[0-9]{2}', value):
                parsed = datetime.strptime(value, '%d.%m.%Y %H:%M')
                precision = 'minute'
        elif source == 'austender' and path == 'detail.TimeZone.CloseDateTime':
            parsed = datetime.strptime(value, '%m/%d/%Y %H:%M:%S')
        elif source == 'austender' and path == 'detail.Close Date & Time':
            display = re.sub(r'\|\s*Show close time for other time zones.*$', '', value, flags=re.I).strip()
            display = re.sub(r'\s*\(ACT Local Time\)\s*$', '', display, flags=re.I).strip()
            parsed = datetime.strptime(_clock12(_english(display)), '%d-%m-%Y %H:%M')
            precision = 'minute'
        elif source == 'austender' and path == 'detail.Publish Date':
            return result('valid', parsed=CalendarDate(day=datetime.strptime(_english(value), '%d-%m-%Y').date()), precision='day')
        elif source == 'india_cppp' and path in {'listing.Published Date', 'listing.Bid Submission End Date'}:
            if not re.fullmatch(r'[0-9]{1,2}-[A-Za-z]{3}-[0-9]{4} [0-9]{1,2}:[0-9]{2} [AaPp][Mm]', value):
                return result('invalid', reason='invalid_source_format')
            parsed = datetime.strptime(_clock12(_english(value)), '%d-%m-%Y %H:%M').replace(
                tzinfo=timezone(timedelta(hours=5, minutes=30)))
            precision = 'minute'
            zone_evidence = 'adapter_policy:IST:+05:30'
        elif source == 'nz_gets' and path == 'item.description.Close date':
            for fmt in ('%d %m %Y %H:%M %z',):
                try:
                    parsed = datetime.strptime(_clock12(_english(value)), fmt)
                    break
                except ValueError:
                    continue
            if parsed is None:
                return result('invalid', reason='invalid_source_format')
            precision = 'minute'
            zone_evidence = 'explicit_source_offset'
        elif (source, path) in {('nz_gets', 'item.pubDate'), ('austender', 'rss.pubDate'),
                               ('eis', 'pubDate'), ('eis', 'pubdate')}:
            if not re.fullmatch(r'(?:[A-Za-z]{3}, )?[0-9]{1,2} [A-Za-z]{3} [0-9]{4} '
                                r'[0-9]{2}:[0-9]{2}:[0-9]{2} (?:GMT|UTC|UT|[+-][0-9]{4})', value):
                return result('invalid', reason='invalid_evidenced_rss_format')
            rss_offset = re.search(r'([+-])([0-9]{2})([0-9]{2})$', value)
            if rss_offset and (int(rss_offset[2]) > 23 or int(rss_offset[3]) > 59):
                return result('invalid', reason='invalid_rss_offset')
            if rss_offset and rss_offset[0] == '-0000':
                return result('ambiguous', reason='unknown_rss_offset')
            parsed = parsedate_to_datetime(value)
            zone_evidence = 'explicit_rss_offset' if parsed.tzinfo else None
    except (ValueError, TypeError, OverflowError):
        return result('invalid', reason='invalid_date_or_source_format')
    if parsed is None:
        return result('unsupported', reason='format_not_verified_for_path')
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return result('ambiguous', precision=precision, reason='source_timezone_unverified')
    try:
        utc = parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return result('invalid', reason='utc_out_of_range')
    return result('valid', parsed=UTCInstant(utc=utc), precision=precision,
                  timezone_evidence=zone_evidence, offset_seconds=int(parsed.utcoffset().total_seconds()))


def stored_date(entry: dict | None, *, source: str, path: str, field: TimeField) -> NormalizedDate:
    """Legacy values are unavailable; never upgrade stored unversioned evidence."""
    raw = entry.get('value') if isinstance(entry, dict) else None
    normalized = entry.get('normalized') if isinstance(entry, dict) else None
    if isinstance(normalized, dict) and normalized.get('version') == DATE_POLICY:
        expected = normalize_date(raw, source=source, path=path, field=field,
                                  semantics=entry.get('semantics'))
        if expected.model_dump(mode='json') == normalized:
            return expected
        reason = 'stored_evidence_mismatch'
    else:
        reason = 'legacy_or_unknown_policy_unavailable'
    return NormalizedDate(source=source, path=path, field=field, semantics=field,
                          raw=raw, status='unsupported', reason=reason)
