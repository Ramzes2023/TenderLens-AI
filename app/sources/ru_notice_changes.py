"""Bounded, offline comparison of source-supplied procurement observations."""
from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
import re
from types import MappingProxyType
from typing import Literal, TypeAlias

SCHEMA_VERSION = "ru-notice-changes/1"
FIELDS = (
    "title", "buyer", "buyer_inn", "price", "currency", "deadline", "status",
    "okpd2_codes", "ktru_codes", "document_ids",
)
COLLECTION_FIELDS = frozenset(("okpd2_codes", "ktru_codes", "document_ids"))
MAX_STRING_CHARS = 4096
MAX_IDENTIFIER_CHARS = 256
MAX_COLLECTION_ITEMS = 256
MAX_TOTAL_CHARS = 32768
MAX_DECIMAL_DIGITS = 128
Status: TypeAlias = Literal[
    "first_observation", "changed", "unchanged", "insufficient_data",
    "identity_mismatch", "out_of_order",
]
ChangeType: TypeAlias = Literal["added", "modified", "removed"]
FieldValue: TypeAlias = str | Decimal | date | tuple[str, ...] | None


def _text(value: object, label: str, limit: int = MAX_STRING_CHARS) -> str:
    if not isinstance(value, str) or not 0 < len(value) <= limit:
        raise ValueError(f"{label}: expected nonempty string of at most {limit} characters")
    if value != value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError(f"{label}: surrounding whitespace and control characters are invalid")
    return value


def _identifier(value: object, label: str) -> str:
    result = _text(value, label, MAX_IDENTIFIER_CHARS)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]*", result):
        raise ValueError(f"{label}: expected an explicit ASCII identifier")
    return result


def _instant(value: object, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label}: expected timezone-aware datetime")
    try:
        return value.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"{label}: UTC timestamp is out of range") from exc


@dataclass(frozen=True, slots=True)
class ObservationKey:
    namespace: str
    procurement_id: str
    lot_id: str | None = None

    def __post_init__(self) -> None:
        _identifier(self.namespace, "namespace")
        _identifier(self.procurement_id, "procurement_id")
        if self.lot_id is not None:
            _identifier(self.lot_id, "lot_id")


def _field(name: str, value: object) -> FieldValue:
    if value is None:
        return None
    if name == "price":
        if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
            raise ValueError("price: expected finite nonnegative Decimal")
        parts = value.as_tuple()
        if len(parts.digits) > MAX_DECIMAL_DIGITS or abs(parts.exponent) > MAX_DECIMAL_DIGITS:
            raise ValueError("price: Decimal precision/exponent exceeds limit")
        return value
    if name == "deadline":
        if isinstance(value, datetime):
            _instant(value, name)
        elif not isinstance(value, date):
            raise ValueError("deadline: expected date or timezone-aware datetime")
        return value
    if name in COLLECTION_FIELDS:
        if not isinstance(value, Collection) or isinstance(value, (str, bytes, Mapping)):
            raise ValueError(f"{name}: expected bounded identifier collection")
        if len(value) > MAX_COLLECTION_ITEMS:
            raise ValueError(f"{name}: collection exceeds {MAX_COLLECTION_ITEMS} items")
        items = [_identifier(item, name) for item in value]
        pattern = {"okpd2_codes": r"[0-9]{2}(?:\.[0-9]{2}(?:\.[0-9]{1,2}(?:\.[0-9]{3})?)?)?",
                   "ktru_codes": r"[0-9]{2}\.[0-9]{2}\.[0-9]{2}\.[0-9]{3}-[0-9]{8}"}.get(name)
        if pattern and any(not re.fullmatch(pattern, item) for item in items):
            raise ValueError(f"{name}: invalid classification identifier syntax")
        return tuple(sorted(set(items)))
    result = _text(value, name)
    if name == "buyer_inn" and not re.fullmatch(r"(?:[0-9]{10}|[0-9]{12})", result):
        raise ValueError("buyer_inn: expected 10 or 12 ASCII digits; checksum is not assessed")
    if name == "currency" and not re.fullmatch(r"[A-Z]{3}", result):
        raise ValueError("currency: expected three uppercase ASCII letters")
    return result


@dataclass(frozen=True, slots=True)
class Observation:
    key: ObservationKey
    observed_at: datetime
    values: Mapping[str, FieldValue]
    complete_fields: Collection[str] = ()
    source_revision: str | None = None
    source_updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.key, ObservationKey):
            raise ValueError("key: expected ObservationKey")
        _instant(self.observed_at, "observed_at")
        if self.source_updated_at is not None:
            _instant(self.source_updated_at, "source_updated_at")
        if self.source_revision is not None:
            _text(self.source_revision, "source_revision", MAX_IDENTIFIER_CHARS)
        if not isinstance(self.values, Mapping) or len(self.values) > len(FIELDS):
            raise ValueError("values: expected mapping with supported fields only")
        mask = self.complete_fields
        if not isinstance(mask, Collection) or isinstance(mask, (str, bytes, Mapping)) or len(mask) > len(FIELDS):
            raise ValueError("complete_fields: expected bounded field-name collection")
        if any(not isinstance(n, str) or n not in FIELDS for n in mask):
            raise ValueError("complete_fields: unsupported field name")
        if len(set(mask)) != len(mask):
            raise ValueError("complete_fields: duplicate field name")
        copied = {}
        total = len(self.key.namespace) + len(self.key.procurement_id) + len(self.key.lot_id or "")
        total += len(self.source_revision or "")
        for name, value in self.values.items():
            if not isinstance(name, str) or name not in FIELDS:
                raise ValueError("values: unsupported field name")
            # Count raw duplicate entries too, before canonicalization.
            if isinstance(value, Collection) and not isinstance(value, (str, bytes, Mapping)):
                if len(value) > MAX_COLLECTION_ITEMS:
                    raise ValueError(f"{name}: collection exceeds limit")
                total += sum(len(item) for item in value if isinstance(item, str))
            elif isinstance(value, str):
                total += len(value)
            if total > MAX_TOTAL_CHARS:
                raise ValueError("values: total input character budget exceeded")
            copied[name] = _field(name, value)
        object.__setattr__(self, "values", MappingProxyType(copied))
        object.__setattr__(self, "complete_fields", frozenset(mask))


@dataclass(frozen=True, slots=True)
class Issue:
    code: str
    field: str | None
    message: str


@dataclass(frozen=True, slots=True)
class Change:
    field: str
    change_type: ChangeType
    previous_value: FieldValue
    current_value: FieldValue


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    schema_version: str
    key: ObservationKey
    status: Status
    changes: tuple[Change, ...]
    unobserved_fields: tuple[str, ...]
    issues: tuple[Issue, ...]
    previous_fingerprint: str | None
    current_fingerprint: str


def _canonical(value: FieldValue) -> object:
    if isinstance(value, Decimal):
        # No normalize(): it rounds under the caller's decimal context.
        text = format(value, "f")
        text = text.rstrip("0").rstrip(".") if "." in text else text
        return {"decimal": "0" if value == 0 else text}
    if isinstance(value, datetime):
        return {"instant": _instant(value, "timestamp").isoformat(timespec="microseconds")}
    if isinstance(value, date):
        return {"date": value.isoformat()}
    return value


def _fingerprint(observation: Observation) -> str:
    payload = {
        "schema": SCHEMA_VERSION,
        "key": [observation.key.namespace, observation.key.procurement_id, observation.key.lot_id],
        "values": {n: _canonical(observation.values[n]) for n in FIELDS if n in observation.values},
        "complete_fields": [n for n in FIELDS if n in observation.complete_fields],
    }
    return sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("ascii")).hexdigest()


def _known(observation: Observation, name: str) -> bool:
    return name in observation.values and (observation.values[name] is not None or name in observation.complete_fields)


def compare_observations(previous: Observation | None, current: Observation) -> ComparisonResult:
    """Compare explicit evidence; malformed inputs raise ValueError at construction."""
    if not isinstance(current, Observation) or (previous is not None and not isinstance(previous, Observation)):
        raise ValueError("compare_observations: expected Observation objects (previous may be None)")
    changes: list[Change] = []
    issues: list[Issue] = []
    unknown = [n for n in FIELDS if not _known(current, n) or (previous is not None and not _known(previous, n))]
    for obs, label in ((previous, "previous"), (current, "current")):
        if obs is not None:
            for n in FIELDS:
                if n in obs.values and obs.values[n] is None and n not in obs.complete_fields:
                    issues.append(Issue("unconfirmed_absence", n, f"{label}: None without completeness is not evidence of absence"))
                if n in obs.complete_fields and n not in obs.values:
                    issues.append(Issue("missing_complete_value", n, f"{label}: missing value remains unobserved despite completeness mask"))

    def result(status: Status) -> ComparisonResult:
        return ComparisonResult(SCHEMA_VERSION, current.key, status, tuple(changes),
                                tuple(n for n in FIELDS if n in unknown), tuple(issues),
                                _fingerprint(previous) if previous is not None else None, _fingerprint(current))

    if previous is None:
        return result("first_observation")
    if previous.key != current.key:
        issues.append(Issue("identity_mismatch", None, "Exact namespace, procurement_id and lot_id equality is required"))
        return result("identity_mismatch")
    if (_instant(current.observed_at, "observed_at") < _instant(previous.observed_at, "observed_at")
            or (previous.source_updated_at is not None and current.source_updated_at is not None
                and _instant(current.source_updated_at, "source_updated_at") < _instant(previous.source_updated_at, "source_updated_at"))):
        issues.append(Issue("timestamp_regression", None, "Observation or source timestamp regressed"))
        return result("out_of_order")
    if _instant(current.observed_at, "observed_at") == _instant(previous.observed_at, "observed_at") and _fingerprint(current) != _fingerprint(previous):
        issues.append(Issue("ambiguous_order", None, "Different evidence at the same observation instant has no established order"))
        return result("out_of_order")
    if previous.source_revision != current.source_revision:
        issues.append(Issue("revision_not_ordered", None, "Opaque source revisions are not used to establish chronology"))
    for n in FIELDS:
        if n in unknown:
            continue
        old, new = previous.values[n], current.values[n]
        if n == "deadline" and old is not None and new is not None and isinstance(old, datetime) != isinstance(new, datetime):
            unknown.append(n)
            issues.append(Issue("precision_mismatch", n, "Date-only and datetime deadlines cannot be compared without source timezone/precision evidence"))
            continue
        if n in COLLECTION_FIELDS and old is not None and new is not None:
            old_set, new_set = set(old), set(new)
            # A partial previous list cannot prove an addition; a partial new list cannot prove removal.
            added = new_set - old_set if n in previous.complete_fields else set()
            removed = old_set - new_set if n in current.complete_fields else set()
            if n not in previous.complete_fields or n not in current.complete_fields:
                unknown.append(n)
                issues.append(Issue("partial_collection", n, "Collection membership differences require completeness on the side establishing absence"))
            if added or removed:
                kind: ChangeType = "modified"
                if not old_set and added:
                    kind = "added"
                elif not new_set and removed:
                    kind = "removed"
                changes.append(Change(n, kind, tuple(sorted(old_set)), tuple(sorted((old_set - removed) | added))))
            continue
        if _canonical(old) != _canonical(new):
            kind = "added" if old is None else "removed" if new is None else "modified"
            # A partial old collection does not establish absence even if empty.
            if n in COLLECTION_FIELDS and new is None and n not in current.complete_fields:
                continue
            changes.append(Change(n, kind, old, new))
    return result("changed" if changes else "insufficient_data" if unknown else "unchanged")
