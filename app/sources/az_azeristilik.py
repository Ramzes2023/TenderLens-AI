"""Official public purchase invitations of Azəristiliktəchizat (Azerbaijan).

An independently verified public contracting entity, NOT the national
Azerbaijan eTender API. Bounded HTTPS list -> anchored detail pages only.
Participation fees are NOT contract values and never enter initial_price.
Production registration stays disabled until explicit operator activation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit
import math
import re

import httpx

from .eis_rss import SourceError
from .http import ConnectorTransportError, FetchPolicy, _policy, bounded_fetch, source_client
from .models import TenderNotice
from .opportunities import validate_notice
from .transport_errors import SourceTransportError, transient_transport

SOURCE = "az_azeristilik"
HOST = "azeristilik.gov.az"
INDEX_URL = "https://azeristilik.gov.az/az/imkanlar/tender-elanlari"
MAX_BODY = 768 * 1024
MAX_DETAILS = 5
POST = re.compile(r"^/(?:(?:az|en|ru)/)?post/([a-z0-9-]{12,200})$")
DATE = re.compile(r"\b([0-3]\d\.[01]\d\.20\d{2})\b")
START_LABEL = "Müsabiqənin başlanma tarixi və vaxtı"
DEADLINE_LABEL = "Təkliflərin son təqdim olunma tarixi və vaxtı"
BUYER_NAME = "Azəristiliktəchizat"


class VisibleHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.tokens = []
        self.href_stack = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "template"):
            self.hidden += 1
        if tag == "a":
            self.href_stack.append(dict(attrs).get("href") or "")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "template"):
            self.hidden = max(0, self.hidden - 1)
        if tag == "a" and self.href_stack:
            self.href_stack.pop()

    def handle_data(self, data):
        if self.hidden:
            return
        value = " ".join(data.split())
        if value:
            self.tokens.append(value)
            if self.href_stack:
                self.links.append((self.href_stack[-1], value))


def approved_detail_url(raw):
    try:
        parts = urlsplit(raw)
        if (parts.scheme not in ("", "https") or parts.hostname not in (None, HOST)
            or parts.username or parts.password or parts.port not in (None, 443)
            or parts.fragment or parts.query or not POST.fullmatch(parts.path)):
            return None
        return "https://" + HOST + parts.path
    except ValueError:
        return None


def _html(raw):
    if type(raw) is not str or len(raw.encode("utf-8")) > MAX_BODY:
        raise SourceError("AZ official tender HTML oversized or malformed.")
    parser = VisibleHTML()
    parser.feed(raw)
    return parser


def discover_official_posts(html):
    """Only visible title anchors on pinned official host can supply IDs."""
    parser = _html(html)
    found = {}
    for href, value in parser.links:
        url = approved_detail_url(href)
        title = " ".join(value.split())
        if (url and 18 <= len(title) <= 1000
            and ("satına" in title.casefold() or "tender" in title.casefold())):
            found[url] = title
    if not 1 <= len(found) <= 40:
        raise SourceError("AZ official tender listing contains no valid posts.")
    return tuple(found.items())


def _date_after(visible_text, label):
    offset = visible_text.find(label)
    if offset < 0:
        raise SourceError("AZ mandatory official date label absent.")
    date = DATE.search(visible_text[offset + len(label):offset + len(label) + 160])
    if not date:
        raise SourceError("AZ official procurement date missing.")
    try:
        return datetime.strptime(date.group(1), "%d.%m.%Y")
    except ValueError:
        raise SourceError("AZ invalid official procurement date.") from None


def parse_public_detail(html, *, url, listed_title):
    approved = approved_detail_url(url)
    if approved != url:
        raise SourceError("AZ official detail identity URL rejected.")
    match = POST.fullmatch(urlsplit(url).path)
    if match is None:
        raise SourceError("AZ official stable detail ID missing.")
    if (type(listed_title) is not str or not 18 <= len(listed_title) <= 1000
            or "satına" not in listed_title.casefold() and "tender" not in listed_title.casefold()):
        raise SourceError("AZ official listing tender title missing.")
    visible = " ".join(_html(html).tokens)
    normalized_title = " ".join(listed_title.split())
    if normalized_title.casefold() not in visible.casefold():
        raise SourceError("AZ official detail not linked to listing title.")
    if "Satınalan təşkilatın adı" not in visible or BUYER_NAME not in visible:
        raise SourceError("AZ public buyer provenance absent.")
    published = _date_after(visible, START_LABEL)
    deadline = _date_after(visible, DEADLINE_LABEL)
    if not (2024 <= published.year <= datetime.now().year + 1) or deadline < published:
        raise SourceError("AZ official procurement period inconsistent.")
    notice = TenderNotice(
        source=SOURCE,
        external_id=match.group(1),
        title=normalized_title,
        url=url,
        customer='Azəristiliktəchizat ASC',
        published_at=published.date().isoformat(),
        deadline=deadline.date().isoformat(),
        region="Azerbaijan",
        # This official page gives a participation fee, NOT a contract
        # budget. Leave price/currency unknown, never hallucinate AZN amount.
        summary="Public tender notice of Azerbaijani state heating company.",
    )
    try:
        validate_notice(notice, SOURCE)
    except (TypeError, ValueError, OverflowError):
        raise SourceError("AZ normalized official notice rejected.") from None
    return notice


@dataclass(frozen=True)
class AzerbaijanHeatSource:
    timeout: float = 12.0
    name: str = SOURCE

    def __post_init__(self):
        if type(self.timeout) not in (int, float) or not math.isfinite(self.timeout) or not 0 < self.timeout <= 30:
            raise ValueError("AZ source timeout must be finite and bounded.")

    async def fetch(self, limit=5):
        if _policy.get() is None:
            with bounded_fetch(FetchPolicy(frozenset({HOST}), 1+MAX_DETAILS, max_bytes=MAX_BODY)):
                return await self._fetch(limit)
        return await self._fetch(limit)

    async def _fetch(self, limit):
        if type(limit) is not int:
            raise SourceError("AZ official limit must be integer.")
        count = min(MAX_DETAILS, max(1, limit))
        notices = []
        # The hardened Worker transport intentionally rejects non-2xx before
        # returning the response to this source. Observe only the exact status
        # of a requested, index-proven same-host detail via an HTTPX response
        # hook, which runs before BoundedClient checks the HTTP status. This
        # avoids changing security policy or request budgets of ANY source.
        active_detail = [None]
        detail_status = [None]

        async def remember_detail_status(response):
            if (active_detail[0] is not None
                    and str(response.request.url) == active_detail[0]):
                detail_status[0] = response.status_code

        try:
            async with source_client(
                timeout=self.timeout, trust_env=False, follow_redirects=False,
                event_hooks={"response": [remember_detail_status]},
            ) as client:
                index = await client.get(INDEX_URL, headers={
                    "Accept": "text/html", "User-Agent": "VALYQON-public-tender-audit/1.0"})
                index.raise_for_status()
                if "html" not in index.headers.get("content-type", "").lower():
                    raise SourceError("AZ official list not HTML.")
                cards = discover_official_posts(index.text)
                for url, title in cards[:count]:
                    active_detail[0], detail_status[0] = url, None
                    try:
                        detail = await client.get(url, headers={
                            "Accept": "text/html", "User-Agent": "VALYQON-public-tender-audit/1.0"})
                        detail.raise_for_status()
                    except httpx.HTTPStatusError as error:
                        if error.response.status_code in (403, 404, 410):
                            # Individual inaccessible/deleted original is not
                            # procurement evidence; another genuine card may
                            # survive. Index, 401, 429, 5xx and redirect
                            # failures still reject the entire source.
                            continue
                        raise
                    except ConnectorTransportError as error:
                        if (error.reason == "http_status"
                                and detail_status[0] in (403, 404, 410)):
                            continue
                        raise
                    finally:
                        active_detail[0] = None
                    if "html" not in detail.headers.get("content-type", "").lower():
                        # An individual non-HTML page is never a tender.
                        continue
                    try:
                        notices.append(parse_public_detail(detail.text, url=url, listed_title=title))
                    except SourceError:
                        # Incomplete individual notices never enter the store.
                        # Fail the batch if no complete notice remains.
                        continue
        except (httpx.HTTPError, ConnectorTransportError, OSError) as exc:
            if transient_transport(exc):
                raise SourceTransportError("AZ official tenders temporarily unavailable.") from None
            raise SourceError("AZ verified official HTTPS retrieval failed.") from None
        if not notices or len({x.identity for x in notices}) != len(notices):
            raise SourceError("AZ official complete notice batch empty or duplicated.")
        return notices
