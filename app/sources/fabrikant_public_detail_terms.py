"""Strict public Fabrikant 44-FZ original closing times and price terms.

Only visible first-party original document fields qualify. Do NOT infer
dates from listing snippets, stage history, hidden scripts, inferred region,
or text from a third-party index. 'МСК+00:00' is Moscow local time (UTC+03),
NOT UTC+00. Conflicting or unsupported timezone labels fail closed.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
import math
import re

MAX_HTML = 1_800_000
_MOSCOW = timezone(timedelta(hours=3))
_CLOSE = re.compile(
    r"дата\s+и\s+время\s+окончания\s+срока\s+подачи\s+заявок"
    r"\s*:?\s*(?P<date>[0-3]\d\.[01]\d\.20\d{2})"
    r"\s*(?:[•·]\s*)?(?P<clock>(?:[01]\d|2[0-3]):[0-5]\d)"
    r"\s*\((?P<zone>МСК\+00:00|MSK\+00:00)\)",
    re.I,
)
_PRICE = re.compile(
    r"начальная\s*\(максимальная\)\s*цена\s*:?\s*"
    r"(?P<money>[0-9]{1,3}(?:[ \u00a0\u202f][0-9]{3})*"
    r"(?:[.,][0-9]{1,2})?|[0-9]{4,16}(?:[.,][0-9]{1,2})?)"
    r"(?=\s|$)",
    re.I,
)


class _FirstPartyVisible(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden: list[str] = []
        self.chunks: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "template", "noscript", "svg", "iframe"}:
            self.hidden.append(tag)

    def handle_endtag(self, tag):
        if self.hidden and self.hidden[-1] == tag:
            self.hidden.pop()

    def handle_data(self, data):
        if not self.hidden:
            self.chunks.append(data)


def _published_visible(html: bytes) -> str:
    if type(html) is not bytes or not 0 < len(html) <= MAX_HTML or b"\x00" in html:
        raise ValueError("Invalid official HTML")
    parser = _FirstPartyVisible()
    parser.feed(html.decode("utf-8-sig", "replace"))
    parser.close()
    return " ".join(" ".join(parser.chunks).split())


def original_terms(html: bytes) -> dict[str, str | float | None]:
    """Source-owned optional terms, not permission to activate a source.

    A verified list identity and independently checked original H1, title
    and organizer are required by the caller. No login or redirect bypass.
    """
    visible = _published_visible(html)
    closings = list(_CLOSE.finditer(visible))
    if len(closings) > 4:
        raise ValueError("Ambiguous publisher submission field")
    deadline_set: set[str] = set()
    for match in closings:
        try:
            day = datetime.strptime(
                match.group("date") + " " + match.group("clock"), "%d.%m.%Y %H:%M"
            )
            deadline_set.add(day.replace(tzinfo=_MOSCOW).isoformat())
        except ValueError as error:
            raise ValueError("Invalid publisher closing time") from None
    # An explicitly labeled date with an unsupported/contradictory timezone
    # is NOT proof of the desired official closing time.
    marker = "дата и время окончания срока подачи заявок"
    occurrences = len(re.findall(re.escape(marker), visible, re.I))
    if occurrences != len(closings) or len(deadline_set) > 1:
        deadline = None
    else:
        deadline = next(iter(deadline_set)) if deadline_set else None

    # Price is optional; the original must explicitly state RUB currency.
    price: float | None = None
    found = _PRICE.findall(visible)
    if len(found) == 1 and re.search(
        r"валюта\s+российский\s+рубль\b", visible, re.I
    ):
        raw = re.sub(r"[ \u00a0\u202f]", "", found[0]).replace(",", ".")
        try:
            numeric = float(raw)
            if math.isfinite(numeric) and 0 < numeric <= 1e18:
                price = numeric
        except (ValueError, OverflowError):
            pass
    return {"deadline": deadline, "initial_price": price,
            "currency": "RUB" if price is not None else None}
