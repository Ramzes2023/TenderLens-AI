"""ARMEPS public table adapter validated against captured official HTML.

Host retrieval and keyword acceptance evidence is recorded in docs/cis for
CIS-31–35. Offline replay alone is not live evidence; activation stays disabled.
"""
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
import math
import re

import httpx
import httpcore

from .eis_rss import SourceError
from .transport_errors import SourceTransportError, transient_transport
from .http import ConnectorTransportError, FetchPolicy, _policy, bounded_fetch, source_client, _is_public_ip_error
from .models import TenderNotice
from .opportunities import validate_notice

def _retryable_official_dns_failure(error):
    """Only the audited resolver's exact HTTPCore DNS failure can retry.

    HTTPX may discard the nested OSError while preserving HTTPCore's exact
    'DNS resolution failed' marker. Never retry PublicIPError, TLS failures,
    or unclassified connect errors. No alternate host or insecure fallback.
    """
    if _is_public_ip_error(error):
        return False
    # BoundedClient intentionally wraps HTTPX transport exceptions into a
    # retryability-labelled ConnectorTransportError; never blindly trust
    # that flag or retry an arbitrary policy failure without matching
    # the exact audited DNS cause inside its exception chain.
    if isinstance(error, ConnectorTransportError):
        if not error.retryable:
            return False
    elif not isinstance(error, httpx.ConnectError):
        return False
    seen, has_httpx_connect = set(), False
    current = error
    while isinstance(current, BaseException) and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, httpx.ConnectError):
            has_httpx_connect = True
        if (has_httpx_connect
                and type(current) is httpcore.ConnectError
                and str(current) == "DNS resolution failed"):
            return True
        current = current.__cause__
    return False


ARMEPS_LISTING_URL = "https://eauction.armeps.am/en/public/tender/"
ARMEPS_PAGE_TWO_URL = ARMEPS_LISTING_URL + "start/2"
MAX_BYTES = 1024 * 1024
MAX_PAGES = 5


def approved_listing_url(url):
    return url == ARMEPS_LISTING_URL or url in {
        ARMEPS_LISTING_URL + f"start/{page}" for page in range(2, MAX_PAGES + 1)}


class _Navigation(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = set()
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        attrs = dict(attrs)
        if not self.hidden and tag == "a" and attrs.get("class") in {"pg_n", "pg_b"}:
            self.urls.add(attrs.get("href"))

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)


def observed_next_page(html, page):
    """Only traverse an exact official navigation link; never infer a remote route."""
    if type(page) is not int or not 1 <= page < MAX_PAGES:
        return None
    if not isinstance(html, str) or len(html.encode("utf-8")) > MAX_BYTES:
        raise SourceError("ARMEPS oversized or invalid navigation HTML.")
    parser = _Navigation()
    parser.feed(html)
    candidate = ARMEPS_LISTING_URL + f"start/{page + 1}"
    return candidate if approved_listing_url(candidate) and candidate in parser.urls else None


class _Tables(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.table = None
        self.row = None
        self.cell = None
        self.hidden = 0
        self.links = {}

    def finish_row(self):
        if self.row is not None:
            if self.cell is not None:
                raise SourceError("ARMEPS unclosed cell.")
            self.table.append(self.row)
            self.row = None

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag == "table":
            if self.table is not None:
                raise SourceError("ARMEPS nested table is unsupported.")
            self.table = []
        elif tag == "tr" and self.table is not None:
            # Official captures omit </tr>; a new tr implicitly ends the row.
            self.finish_row()
            self.row = []
            self.links[id(self.row)] = []
        elif tag in {"td", "th"} and self.row is not None:
            self.cell = []
        elif tag == "a" and self.cell is not None and not self.hidden:
            href = dict(attrs).get("href")
            if href is not None:
                self.links[id(self.row)].append((len(self.row), href))

    def handle_data(self, data):
        if self.cell is not None and not self.hidden:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        elif tag in {"td", "th"} and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.finish_row()
        elif tag == "table" and self.table is not None:
            self.finish_row()
            self.tables.append(self.table)
            self.table = None


def _merge(result, notice):
    previous = result.get(notice.identity)
    if previous is not None and previous != notice:
        raise SourceError("ARMEPS conflicting duplicate ID.")
    result[notice.identity] = notice


def parse_armeps_listing(html: str, *, listing_url=ARMEPS_LISTING_URL):
    """Observed seven-column DOM, plus legacy synthetic six-column fixtures."""
    if not approved_listing_url(listing_url):
        raise SourceError("ARMEPS unapproved listing URL.")
    if not isinstance(html, str) or len(html.encode("utf-8")) > MAX_BYTES:
        raise SourceError("ARMEPS oversized or invalid HTML.")
    parser = _Tables()
    parser.feed(html)
    expected = ["id", "code", "title", "lotcount", "status", "endbidtime"]
    observed = ["id", "code", "title", "lotscount", "status", "endbidtime", ""]
    matches = [table for table in parser.tables if table and
               [re.sub(r"[^a-z]", "", cell.casefold()) for cell in table[0]] in (expected, observed)]
    if len(matches) != 1 or parser.table is not None:
        raise SourceError("ARMEPS listing structure unverified or changed.")
    result = {}
    real_dom = len(matches[0][0]) == 7
    if len(matches[0]) > 1001:
        raise SourceError("ARMEPS too many rows.")
    for row in matches[0][1:]:
        if len(row) != (7 if real_dom else 6):
            raise SourceError("ARMEPS invalid listing row.")
        identifier, code, title, lots, status, deadline = row[:6]
        detail_url = ARMEPS_LISTING_URL
        if real_dom:
            links = parser.links[id(row)]
            expected_detail = f"https://eauction.armeps.am/en/public/tender_details/tid/{identifier}/"
            if links != [(6, expected_detail)] or row[6]:
                raise SourceError("ARMEPS unsafe or mismatched observed detail link.")
            detail_url = links[0][1]
        if not re.fullmatch(r"[0-9]{1,30}", identifier) or not re.fullmatch(r"[0-9]{1,6}", lots):
            raise SourceError("ARMEPS invalid ID or lot count.")
        if not code or not title or not status:
            raise SourceError("ARMEPS missing public field.")
        try:
            date_format = "%Y-%m-%d %H:%M:%S" if real_dom else "%d.%m.%Y %H:%M"
            normalized_deadline = datetime.strptime(deadline, date_format).isoformat()
        except ValueError:
            raise SourceError("ARMEPS unverified end bid time format.") from None
        notice = TenderNotice(source="am_armeps", external_id=identifier, title=title,
                              tender_number=code, url=detail_url, deadline=normalized_deadline,
                              summary=f"Lot count: {lots}; Status: {status}")
        try:
            validate_notice(notice, "am_armeps")
        except ValueError:
            raise SourceError("ARMEPS invalid normalized notice.") from None
        _merge(result, notice)
    return list(result.values())


@dataclass(frozen=True)
class ArmeniaArmepsSource:
    timeout: float = 10.0
    max_pages: int = 2
    name: str = "am_armeps"

    def __post_init__(self):
        if not math.isfinite(self.timeout) or not 0 < self.timeout <= 30:
            raise ValueError("timeout must be between 0 and 30 seconds.")
        if type(self.max_pages) is not int or not 1 <= self.max_pages <= MAX_PAGES:
            raise ValueError("max_pages must be between 1 and 5.")

    async def fetch(self, limit=20):
        # Preserve any enclosing ingestion policy; never broaden its allowlist.
        if _policy.get() is None:
            with bounded_fetch(FetchPolicy(frozenset({"eauction.armeps.am"}), self.max_pages, max_bytes=MAX_BYTES)):
                return await self._fetch(limit)
        return await self._fetch(limit)

    async def _fetch(self, limit):
        requested = max(1, min(int(limit), 100))
        result = {}
        try:
            async with source_client(timeout=self.timeout, trust_env=False, follow_redirects=False) as client:
                url = ARMEPS_LISTING_URL
                for page in range(1, self.max_pages + 1):
                    response = await client.get(url)
                    response.raise_for_status()
                    if "text/html" not in response.headers.get("content-type", "").lower():
                        raise SourceError("ARMEPS response is not HTML.")
                    rows = parse_armeps_listing(response.text, listing_url=url)
                    for notice in rows:
                        _merge(result, notice)
                    if len(result) >= requested or not rows:
                        break
                    # Preserve the accepted two-page contract. Additional pages
                    # require a navigation link in the immediately preceding HTML.
                    next_url = ARMEPS_PAGE_TWO_URL if page == 1 else observed_next_page(response.text, page)
                    if next_url is None:
                        break
                    url = next_url
        except (httpx.HTTPError, ConnectorTransportError, OSError) as error:
            if transient_transport(error) or _retryable_official_dns_failure(error):
                raise SourceTransportError("Temporary source transport failure.") from None
            # Strictly sanitized transport diagnosis. Do not echo upstream URLs,
            # exception string, data, TLS contents, or DNS address. Security
            # policy failures and client 4xx remain permanent, never green.
            if _is_public_ip_error(error):
                raise SourceError("ARMEPS verified public-IP policy rejected connection.") from None
            if isinstance(error, httpx.HTTPStatusError):
                status = error.response.status_code
                if status in (408, 429) or 500 <= status <= 599:
                    raise SourceTransportError("ARMEPS official temporary HTTP failure.") from None
                raise SourceError("ARMEPS official HTTP client status rejected.") from None
            if isinstance(error, httpx.ConnectError):
                raise SourceError("ARMEPS unclassified HTTPS connection failure.") from None
            if isinstance(error, ConnectorTransportError):
                raise SourceError("ARMEPS strict transport policy rejected request.") from None
            raise SourceError("ARMEPS bounded HTTPS retrieval failed; live verification unavailable.") from None
        return list(result.values())[:requested]
