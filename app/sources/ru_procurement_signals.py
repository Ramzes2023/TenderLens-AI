"""Extract explicit textual metadata; never determine legal applicability."""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal


Law = Literal["44-FZ", "223-FZ", "ambiguous", "unknown"]
Kind = Literal["law", "okpd2", "ktru"]
TEXT_FIELDS = (
    "title", "description", "summary", "procurement_law", "law_text",
    "classification_text",
)
MAX_FIELD_CHARS = 100_000
_SPACE = r"[^\S\r\n]{0,16}"
_DASH = r"[-‐‑‒–—−]"
_LAW = re.compile(
    rf"(?<![\w.\-‐‑‒–—−])(?:"
    rf"(?P<abbr>44|223){_SPACE}(?:{_DASH}{_SPACE})?(?:ФЗ|FZ)"
    rf"|(?:Федеральн(?:ый|ого|ому|ым)\s+закон(?:а|у|ом)?"
    rf"|Federal\s+Law){_SPACE}(?:№|No\.?|N)?{_SPACE}"
    rf"(?P<full>44|223)(?:{_SPACE}{_DASH}{_SPACE}(?:ФЗ|FZ))?"
    rf")(?![\w.\-‐‑‒–—−])", re.IGNORECASE,
)
_OKPD = r"[0-9]{2}(?:\.[0-9]{2}(?:\.[0-9](?:[0-9](?:\.[0-9]{3})?)?)?)?"
_CODE = re.compile(
    rf"(?<![\w])(?:(?P<okpd>ОКПД{_SPACE}2|OKPD{_SPACE}2)"
    rf"|(?P<ktru>КТРУ|KTRU))(?!\w){_SPACE}"
    rf"(?:(?:код|code)(?!\w){_SPACE})?(?:[:=№]{_SPACE})?"
    rf"(?P<value>{_OKPD}(?:{_DASH}[0-9]{{8}})?)"
    rf"(?![\w.\-‐‑‒–—−])", re.IGNORECASE,
)
_KTRU_VALUE = re.compile(rf"[0-9]{{2}}\.[0-9]{{2}}\.[0-9]{{2}}\.[0-9]{{3}}{_DASH}[0-9]{{8}}")


@dataclass(frozen=True)
class Signal:
    kind: Kind
    value: str
    evidence: str
    source_field: str
    start: int
    end: int


@dataclass(frozen=True)
class InputIssue:
    source_field: str
    reason: Literal["invalid_type", "too_long"]


@dataclass(frozen=True)
class ProcurementSignals:
    law: Law
    okpd2_codes: tuple[str, ...]
    ktru_codes: tuple[str, ...]
    signals: tuple[Signal, ...]
    issues: tuple[InputIssue, ...]


def extract_ru_procurement_signals(
    fields: Mapping[str, object] | None,
) -> ProcurementSignals:
    """Scan allowlisted text in fixed order, with offsets into unmodified strings.

    None means no metadata. Other non-mapping inputs raise TypeError. Invalid
    field values and fields exceeding MAX_FIELD_CHARS are skipped in full.
    No conversion, truncation, lookup, or inference is performed.
    """
    if fields is None:
        fields = {}
    if not isinstance(fields, Mapping):
        raise TypeError("fields must be a mapping or None")
    signals: list[Signal] = []
    issues: list[InputIssue] = []
    for field in TEXT_FIELDS:
        value = fields.get(field)
        if value is None:
            continue
        if not isinstance(value, str):
            issues.append(InputIssue(field, "invalid_type"))
            continue
        if len(value) > MAX_FIELD_CHARS:
            issues.append(InputIssue(field, "too_long"))
            continue
        found: list[Signal] = []
        for match in _LAW.finditer(value):
            number = match.group("abbr") or match.group("full")
            found.append(Signal("law", f"{number}-FZ", match.group(), field,
                                match.start(), match.end()))
        for match in _CODE.finditer(value):
            code = match.group("value")
            kind: Kind = "okpd2" if match.group("okpd") else "ktru"
            if kind == "ktru":
                if not _KTRU_VALUE.fullmatch(code):
                    continue
                code = re.sub(_DASH, "-", code)
            elif not re.fullmatch(_OKPD, code):
                continue
            found.append(Signal(kind, code, match.group(), field,
                                match.start(), match.end()))
        signals.extend(sorted(found, key=lambda signal: (signal.start, signal.end, signal.kind)))
    laws = {signal.value for signal in signals if signal.kind == "law"}
    law: Law = "ambiguous" if len(laws) > 1 else "unknown"
    if len(laws) == 1:
        law = "44-FZ" if "44-FZ" in laws else "223-FZ"
    return ProcurementSignals(
        law,
        tuple(sorted({s.value for s in signals if s.kind == "okpd2"})),
        tuple(sorted({s.value for s in signals if s.kind == "ktru"})),
        tuple(signals), tuple(issues),
    )
