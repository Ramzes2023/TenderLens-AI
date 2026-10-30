"""Experimental, fail-closed deadline evidence from an official EIS detail HTML page.

This module performs NO network I/O. A caller must fetch the exact canonical
RSS notice URL using scoped pinned CA, HTTPS-only and no redirect/proxy.
It does not claim that 223-FZ detail pages are currently reachable or that
the site's timezone is known. No fallback to publication/search dates.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
from html.parser import HTMLParser
import re
from urllib.parse import parse_qs, urlsplit

from app.api.public_eis_identity import accepted_eis_original
from app.api.public_source_deadline import eligible_published_deadline

MAX_HTML_BYTES = 1_200_000
MAX_VISIBLE_TEXT = 120_000

_DATE = (
    r"(?P<date>(?:0[1-9]|[12][0-9]|3[01])\."
    r"(?:0[1-9]|1[0-2])\.20[0-9]{2}\s+"
    r"(?:[01][0-9]|2[0-3]):[0-5][0-9](?::[0-5][0-9])?)"
)
_CLOSING = re.compile(
    r"(?:Дата\s+и\s+время\s+окончания\s+подачи\s+заявок"
    r"|Дата\s+окончания\s+подачи\s+заявок"
    r"|Окончание\s+подачи\s+заявок"
    r"|Срок\s+окончания\s+подачи\s+заявок)"
    r"\s*[:\-–]?\s*" + _DATE,
    re.I,
)
_SKIP = frozenset({"script", "style", "noscript", "template", "svg"})
_NUMBER_HEADER = (
    r"(?:Номер\s+(?:извещения|закупки)|Реестровый\s+номер"
    r"(?:\s+закупки)?|№)\s*[:№]?\s*"
)


class _VisibleBody(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.body = 0
        self.skip = 0
        self.parts: list[str] = []
        self.size = 0

    def handle_starttag(self, tag, attrs):
        if tag == "body":
            self.body += 1
        if tag in _SKIP:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in _SKIP and self.skip:
            self.skip -= 1
        if tag == "body" and self.body:
            self.body -= 1

    def handle_data(self, data):
        if self.body and not self.skip and data.strip():
            self.size += len(data)
            if self.size > MAX_VISIBLE_TEXT:
                raise ValueError("Detail text limit exceeded")
            self.parts.append(data)


def verified_detail_deadline(notice: object, payload: bytes, *, now: datetime) -> str | None:
    """Return a *safe future* original closing clock; else reject with None.

    Requires an independently verified notice registration identity and
    display of that exact number in the BODY as an explicitly labeled field.
    The response HTTP 200/Content-Type/actual origin must be validated by the
    caller, not inferred from HTML bytes.
    """
    if now.tzinfo is None:
        raise ValueError("Aware verification time required")
    if not is_dataclass(notice):
        return None
    item = asdict(notice)
    source = item.get("source")
    if source not in {"eis", "eis_223"} or not accepted_eis_original(item):
        return None
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_HTML_BYTES:
        return None
    if b"\x00" in payload:
        return None
    # Official detail HTML is UTF-8; never execute JavaScript or parse scripts.
    try:
        decoded = payload.decode("utf-8-sig")
    except UnicodeError:
        return None
    reader = _VisibleBody()
    try:
        reader.feed(decoded)
        reader.close()
    except ValueError:
        return None
    text = " ".join(" ".join(reader.parts).split())
    if not text:
        return None
    number = item["tender_number"]
    if not re.search(_NUMBER_HEADER + re.escape(number) + r"(?!\d)", text, re.I):
        return None
    found = [match.group("date") for match in _CLOSING.finditer(text)]
    if not found or len(set(found)) != 1:
        return None
    value = found[0]
    fmt = "%d.%m.%Y %H:%M:%S" if value.count(":") == 2 else "%d.%m.%Y %H:%M"
    try:
        dt = datetime.strptime(value, fmt)
    except ValueError:
        return None
    normal = dt.strftime(fmt)
    if not eligible_published_deadline(source, normal, now=now):
        return None
    return normal
