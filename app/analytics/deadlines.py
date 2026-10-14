"""Shared deadline identities for future authorized Discover replay and heatmaps.

Callers must authorize and select the population BEFORE constructing these inputs.
Scope labels are integrity checks, never credentials or authorization substitutes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .dates import CalendarDate, NormalizedDate, UTCInstant

DEADLINE_POLICY = 'deadline-window-v1'
Identity = tuple[str, str]


@dataclass(frozen=True)
class DeadlineWindow:
    as_of: datetime
    display_timezone: str
    days: int = 7
    request_timezone: str | None = None

    def __post_init__(self):
        if not isinstance(self.as_of, datetime) or self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError('Explicit aware server as_of required.')
        if type(self.days) is not int or not 1 <= self.days <= 366:
            raise ValueError('Window must be an integer in 1..366 days.')
        if not isinstance(self.display_timezone, str) or not self.display_timezone:
            raise ValueError('Explicit display IANA timezone required.')
        if self.request_timezone is not None and not isinstance(self.request_timezone, str):
            raise ValueError('Request timezone must be a string when supplied.')
        object.__setattr__(self, 'as_of', self.as_of.astimezone(timezone.utc))
        # Check bounds up front, including maximum-date overflow.
        try:
            self.as_of + timedelta(days=self.days)
        except OverflowError:
            raise ValueError('Window exceeds datetime range.') from None

    @property
    def zone(self):
        # No fixed offset or machine timezone fallback. ZoneInfo may lack data on Windows.
        try:
            return ZoneInfo(self.display_timezone)
        except (ZoneInfoNotFoundError, ValueError):
            return None


@dataclass(frozen=True)
class DeadlineDecision:
    kind: Literal['instant', 'date_only', 'unknown']
    status: str
    included: bool
    bucket: date | None = None
    reason: str | None = None


def deadline_decision(value: NormalizedDate, window: DeadlineWindow) -> DeadlineDecision:
    """UTC elapsed-day interval OR distinctly typed local calendar-day interval."""
    if value.field != 'deadline':
        raise ValueError('Deadline evidence required; other time fields are not interchangeable.')
    if value.status != 'valid':
        return DeadlineDecision('unknown', value.status, False, reason=value.reason)
    zone = window.zone
    if isinstance(value.parsed, UTCInstant):
        instant = value.parsed.utc
        included = window.as_of <= instant < window.as_of + timedelta(days=window.days)
        state = 'expired' if instant < window.as_of else 'closing_soon' if included else 'future'
        try:
            bucket = instant.astimezone(zone).date() if zone else None
        except (OverflowError, ValueError):
            return DeadlineDecision('instant', state, included, reason='display_date_out_of_range')
        return DeadlineDecision('instant', state, included, bucket,
                                None if zone else 'display_timezone_unavailable')
    if isinstance(value.parsed, CalendarDate):
        if zone is None:
            return DeadlineDecision('date_only', 'unavailable', False, reason='display_timezone_unavailable')
        try:
            start = window.as_of.astimezone(zone).date()
            end = start + timedelta(days=window.days)
        except (OverflowError, ValueError):
            return DeadlineDecision('date_only', 'unavailable', False, reason='display_date_out_of_range')
        day = value.parsed.day
        included = start <= day < end
        state = 'expired' if day < start else 'closing_soon' if included else 'future'
        return DeadlineDecision('date_only', state, included, day)
    return DeadlineDecision('unknown', 'invalid', False, reason='missing_typed_value')


@dataclass(frozen=True)
class DeadlineRow:
    organization_id: int
    company_id: int
    identity: Identity
    deadline: NormalizedDate


@dataclass(frozen=True)
class DeadlinePopulation:
    """One preauthorized selected population; no H/R joins or revision selection here."""
    organization_id: int
    company_id: int
    population_id: str
    rows: tuple[DeadlineRow, ...]

    def __post_init__(self):
        if (type(self.organization_id) is not int or self.organization_id <= 0
                or type(self.company_id) is not int or self.company_id <= 0
                or not isinstance(self.population_id, str) or not self.population_id
                or type(self.rows) is not tuple):
            raise ValueError('Explicit immutable selected population and scope required.')
        for row in self.rows:
            if not isinstance(row, DeadlineRow) or not isinstance(row.deadline, NormalizedDate):
                raise ValueError('Typed deadline row required.')
            if (row.organization_id, row.company_id) != (self.organization_id, self.company_id):
                raise ValueError('Cross-scope population rejected.')
            if (type(row.identity) is not tuple or len(row.identity) != 2 or any(not isinstance(v, str) or not v for v in row.identity)
                    or row.identity[0] != row.deadline.source or row.deadline.field != 'deadline'):
                raise ValueError('Invalid deadline identity.')


@dataclass(frozen=True)
class DeadlineGrouping:
    version: str
    population_id: str
    window: DeadlineWindow
    selected: tuple[Identity, ...]
    # kind is part of bucket identity; date-only never becomes an instant.
    buckets: tuple[tuple[str, date, tuple[Identity, ...]], ...]
    states: tuple[tuple[str, str, tuple[Identity, ...]], ...]
    duplicate_count: int
    conflicting: tuple[Identity, ...]
    timezone_status: str
    unbucketed: tuple[tuple[Identity, str], ...]


def group_deadlines(population: DeadlinePopulation, window: DeadlineWindow) -> DeadlineGrouping:
    """Exactly the same decisions supply closing-soon filtering and heatmap cells."""
    unique = {}
    conflicts = set()
    duplicates = 0
    for row in population.rows:
        if row.identity in unique:
            duplicates += 1
            if unique[row.identity].deadline != row.deadline:
                conflicts.add(row.identity)
        else:
            unique[row.identity] = row
    buckets, states, selected, unbucketed = {}, {}, [], []
    for identity, row in sorted(unique.items()):
        if identity in conflicts:
            states.setdefault(('unknown', 'conflicting'), []).append(identity)
            continue
        decision = deadline_decision(row.deadline, window)
        states.setdefault((decision.kind, decision.status), []).append(identity)
        if decision.included:
            selected.append(identity)
            if decision.bucket is not None:
                buckets.setdefault((decision.kind, decision.bucket), []).append(identity)
            else:
                unbucketed.append((identity, decision.reason or 'date_bucket_unavailable'))
    return DeadlineGrouping(DEADLINE_POLICY, population.population_id, window, tuple(selected),
                            tuple((kind, day, tuple(ids)) for (kind, day), ids in sorted(buckets.items())),
                            tuple((kind, state, tuple(ids)) for (kind, state), ids in sorted(states.items())),
                            duplicates, tuple(sorted(conflicts)),
                            'available' if window.zone else 'unavailable', tuple(unbucketed))


def filter_deadlines(population: DeadlinePopulation, window: DeadlineWindow, *,
                     bucket: date | None = None, kind: str | None = None) -> tuple[Identity, ...]:
    """Discover-style closing-soon predicate; optional exact heatmap cell replay."""
    if kind not in {None, 'instant', 'date_only'}:
        raise ValueError('Unknown deadline kind.')
    grouped = group_deadlines(population, window)
    if bucket is None and kind is None:
        return grouped.selected
    if grouped.timezone_status != 'available':
        raise ValueError('Date bucket filtering unavailable without display timezone data.')
    if grouped.unbucketed:
        raise ValueError('Date bucket population incomplete.')
    return tuple(sorted(identity for cell_kind, day, identities in grouped.buckets
                        if (bucket is None or day == bucket) and (kind is None or kind == cell_kind)
                        for identity in identities))
