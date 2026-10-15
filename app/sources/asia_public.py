"""Conservative Asian procurement adapters: four Hong Kong RSS feeds, two JETRO lists.

All endpoints are hard-coded official HTTPS sources.  No login, crawling of
detail pages, redirects, or speculative deadlines.  Registration is staged
behind VALYQON_ASIA_SOURCES_ENABLED until live acceptance is demonstrated.
"""
from __future__ import annotations

import hashlib
import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

from .eis_rss import SourceError
from .http import source_client
from .models import TenderNotice

ASIA_RSS_FEEDS = {
    "hk_ha_works": "https://www.housingauthority.gov.hk/en/rss/tenders.xml",
    "hk_ha_leasing": "https://www.housingauthority.gov.hk/en/rss/tender-notices-and-awards.xml",
    "hk_emsd_tenders": "https://www.emsd.gov.hk/filemanager/tendernotice/en/tender_notices.xml",
    "hk_emsd_consultancy": "https://www.emsd.gov.hk/filemanager/tendernotice/en/consultancy.xml",
}
JETRO_LISTS = {
    "jp_jetro_national": "https://www.jetro.go.jp/en/database/procurement/national/list.html",
    "jp_jetro_local": "https://www.jetro.go.jp/en/database/procurement/local/list.html",
}
# Explicit, anonymous official JETRO search-form parameters. A default GET may
# render an empty form rather than a submitted search result; the bounded
# fallback is accepted only if it yields verifiable linked procurement notices.
JETRO_SEARCH_URLS = {
    "jp_jetro_national": JETRO_LISTS["jp_jetro_national"]
    + "?_page=1&area=&classification1=&classification2=&classification3=&deadline=&entity=&from=&keyword=&to=&type=",
    "jp_jetro_local": JETRO_LISTS["jp_jetro_local"]
    + "?_page=1&local_area=&local_classification1=&local_classification2=&local_classification3=&local_deadline=&local_entity=&local_from=&local_keyword=&local_to=",
}
_MAX_BYTES = 1024 * 1024
_CLEAN = re.compile(r"\s+")
_JETRO_LINK = re.compile(
    r"^/en/database/procurement/(national|local)/articles/([0-9]+)/([0-9]+)\.html$"
)
_JETRO_DATE = re.compile(r"\b[A-Z][a-z]{2} [0-9]{1,2}, 20[0-9]{2}\b")


def _text(value: str | None) -> str:
    return _CLEAN.sub(" ", re.sub(r"<[^>]+>", " ", html.unescape(value or ""))).strip()


def _safe_link(
    value: str,
    hosts: frozenset[str],
    *,
    base: str | None = None,
    upgrade_official_http: bool = False,
) -> str:
    """Resolve approved public notice links without ever fetching insecure URLs.

    Official feeds can contain historic HTTP notice links. Only upgrade URLs
    with an *exact* allowlisted hostname to HTTPS; do not issue HTTP requests.
    """
    if (not value or any(char.isspace() or ord(char) < 32 or char == "\\" for char in value)
            or re.search(r"%(?:0[0-9a-f]|1[0-9a-f]|7f)", value, re.IGNORECASE)):
        raise SourceError("Asian source provided an unsafe item URL.")
    try:
        candidate = urljoin(base, value) if base else value
        part = urlsplit(candidate)
        if (part.hostname not in hosts or not part.netloc or "@" in part.netloc
                or part.username is not None or part.password is not None
                or part.fragment or not part.path.startswith("/")
                or part.port not in (None, 443)):
            raise ValueError()
        if part.scheme == "http" and upgrade_official_http:
            if part.port is not None:
                raise ValueError()
            # Strip the insecure scheme before sending notice links to users.
            candidate = "https://" + part.netloc + part.path
            if part.query:
                candidate += "?" + part.query
            part = urlsplit(candidate)
        if part.scheme != "https" or len(candidate) > 2000:
            raise ValueError()
    except ValueError:
        raise SourceError("Asian source provided an unsafe item URL.") from None
    return candidate

def _published(value: str | None) -> str | None:
    cleaned = _text(value)
    if not cleaned:
        return None
    try:
        parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(cleaned)
        except (TypeError, ValueError, IndexError, OverflowError):
            return None
    if parsed.tzinfo is None:
        return None
    return parsed.isoformat()

def parse_asia_rss(payload: bytes, *, source: str, limit: int = 20) -> list[TenderNotice]:
    if source not in ASIA_RSS_FEEDS or len(payload) > _MAX_BYTES:
        raise SourceError("Unapproved or oversized Asian RSS source.")
    if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise SourceError("Asian RSS contains forbidden XML declarations.")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        raise SourceError("Asian procurement RSS is malformed.") from None
    atom = "{http://www.w3.org/2005/Atom}"
    rdf = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
    rss1 = "{http://purl.org/rss/1.0/}"
    dc = "{http://purl.org/dc/elements/1.1/}"
    if root.tag not in ("rss", atom + "feed", rdf + "RDF"):
        raise SourceError("Asian procurement endpoint did not return RSS/Atom.")
    hosts = frozenset({"www.housingauthority.gov.hk", "housingauthority.gov.hk"}) if source.startswith("hk_ha_") else frozenset({"www.emsd.gov.hk", "emsd.gov.hk"})
    output: list[TenderNotice] = []
    seen: set[str] = set()
    if root.tag == "rss":
        items = root.findall("./channel/item")
    elif root.tag == atom + "feed":
        items = root.findall(f"./{atom}entry")
    else:
        items = root.findall(f"./{rss1}item")
    for item in items:
        if root.tag == "rss":
            raw_title = item.findtext("title")
            raw_link = item.findtext("link")
            raw_date = item.findtext("pubDate")
            guid = item.findtext("guid")
            description = item.findtext("description")
        elif root.tag == atom + "feed":
            raw_title = item.findtext(f"{atom}title")
            raw_link = next(
                (link.get("href", "") for link in item.findall(f"{atom}link")
                 if link.get("rel", "alternate") == "alternate"), "")
            raw_date = item.findtext(f"{atom}published") or item.findtext(f"{atom}updated")
            guid = item.findtext(f"{atom}id")
            description = item.findtext(f"{atom}summary")
        else:
            raw_title = item.findtext(f"{rss1}title")
            raw_link = item.findtext(f"{rss1}link")
            raw_date = item.findtext(f"{dc}date")
            guid = item.get(rdf + "about")
            description = item.findtext(f"{rss1}description")
        title = _text(raw_title)
        if not title or not raw_link:
            continue
        # A published award is not an opportunity to bid. Leasing feeds in
        # particular can mix tender notices and contract award announcements.
        if re.search(r"\b(?:contract awards?|tender awards?|award(?:ed|s)?)\b", title, re.I):
            continue
        try:
            link = _safe_link(
                _text(raw_link), hosts,
                base=ASIA_RSS_FEEDS[source],
                upgrade_official_http=True,
            )
        except SourceError:
            continue
        identity = _text(guid) or link
        external_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:40]
        if external_id in seen:
            continue
        seen.add(external_id)
        output.append(TenderNotice(
            source=source, external_id=external_id,
            title=title[:1000], url=link[:2000],
            published_at=_published(raw_date),
            customer=("Hong Kong Housing Authority" if source.startswith("hk_ha")
                      else "Hong Kong Electrical and Mechanical Services Department"),
            summary=_text(description)[:4000] or None,
            region="Hong Kong",
        ))
        if len(output) >= max(1, min(int(limit), 100)):
            break
    if not output:
        raise SourceError("Asian RSS returned no verifiable tender entries.")
    return output


class _JetroRows(HTMLParser):
    """Read only public procurement article anchors inside actual table rows."""

    def __init__(self, section: str):
        super().__init__(convert_charrefs=True)
        self.section = section
        self.rows: list[tuple[list[str], str, str]] = []
        self.in_row = False
        self.in_cell = False
        self.cell_parts: list[str] = []
        self.cells: list[str] = []
        self.anchor_href: str | None = None
        self.anchor_parts: list[str] = []
        self.match_href = ""
        self.match_title = ""

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.in_row = True
            self.cells = []
            self.match_href = ""
            self.match_title = ""
        elif self.in_row and tag in ("td", "th"):
            self.in_cell = True
            self.cell_parts = []
        elif self.in_row and tag == "a":
            href = dict(attrs).get("href", "")
            try:
                url = _safe_link(
                    href, frozenset({"www.jetro.go.jp"}),
                    base=JETRO_LISTS["jp_jetro_" + self.section],
                )
                path = urlsplit(url).path
                match = _JETRO_LINK.fullmatch(path)
                if match and match.group(1) == self.section:
                    self.anchor_href = path
                    self.anchor_parts = []
            except SourceError:
                pass

    def handle_data(self, data):
        if self.in_cell:
            self.cell_parts.append(data)
        if self.anchor_href is not None:
            self.anchor_parts.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.anchor_href is not None:
            if _text("".join(self.anchor_parts)):
                self.match_href = self.anchor_href
                self.match_title = _text("".join(self.anchor_parts))
            self.anchor_href = None
        elif tag in ("td", "th") and self.in_cell:
            self.cells.append(_text("".join(self.cell_parts)))
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            if self.match_href and self.match_title:
                self.rows.append((list(self.cells), self.match_href, self.match_title))
            self.in_row = False
            self.in_cell = False


def parse_jetro_html(payload: bytes, *, source: str, limit: int = 20) -> list[TenderNotice]:
    if source not in JETRO_LISTS or len(payload) > _MAX_BYTES:
        raise SourceError("Unapproved or oversized JETRO page.")
    section = "national" if source.endswith("national") else "local"
    parser = _JetroRows(section)
    try:
        parser.feed(payload.decode("utf-8-sig", errors="replace"))
        parser.close()
    except (ValueError, TypeError):
        raise SourceError("JETRO returned malformed listing markup.") from None
    output: list[TenderNotice] = []
    seen: set[str] = set()
    for cells, path, title in parser.rows:
        # National results contain several procurement-adjacent announcement
        # classes (e.g. requests for comments and sole-source notices). Only
        # send actual competitive tender notices to the tender search index.
        if section == "national":
            notice_type = cells[2].casefold() if len(cells) > 2 else ""
            if not any(term in notice_type for term in (
                "notice of procurement", "contract notice",
                "invitation to tender", "tender notice",
            )):
                continue
        url = _safe_link(path, frozenset({"www.jetro.go.jp"}), base="https://www.jetro.go.jp")
        if not _JETRO_LINK.fullmatch(urlsplit(url).path):
            continue
        external_id = urlsplit(url).path.rsplit("/", 2)[-2] + ":" + urlsplit(url).path.rsplit("/", 1)[-1].removesuffix(".html")
        if external_id in seen:
            continue
        seen.add(external_id)
        date_match = next((_JETRO_DATE.search(cell) for cell in cells if _JETRO_DATE.search(cell)), None)
        publication = None
        if date_match:
            try:
                publication = datetime.strptime(date_match.group(), "%b %d, %Y").date().isoformat()
            except ValueError:
                pass
        # A calendar date is not an exact submission time. Do not invent deadlines.
        output.append(TenderNotice(
            source=source, external_id=external_id,
            title=title[:1000], url=url, published_at=publication,
            customer=cells[1][:500] if len(cells) > 1 else None,
            region="Japan",
        ))
        if len(output) >= max(1, min(int(limit), 100)):
            break
    if not output:
        raise SourceError("JETRO returned no verifiable linked procurement notices.")
    return output


async def _fetch(url: str, timeout: float, accept: str) -> bytes:
    try:
        async with source_client(
            timeout=timeout, follow_redirects=False, trust_env=False,
            headers={"Accept": accept, "User-Agent": "VALYQON-AI/1.0 (public procurement discovery)"},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.content
            if len(payload) > _MAX_BYTES:
                raise SourceError("Asian procurement response exceeds 1 MiB.")
            return payload
    except SourceError:
        raise
    except httpx.HTTPStatusError as exc:
        # Expose only numeric public HTTP status for diagnostic gates.
        raise SourceError(
            f"Asian procurement upstream HTTP {exc.response.status_code}."
        ) from None
    except (httpx.HTTPError, OSError):
        raise SourceError("Asian procurement network/TLS unavailable.") from None


@dataclass(frozen=True)
class AsiaPublicSource:
    name: str
    timeout: float = 30.0

    def __post_init__(self):
        if self.name not in ASIA_RSS_FEEDS and self.name not in JETRO_LISTS:
            raise ValueError("Unknown Asian public procurement source.")
        if not 0 < self.timeout <= 120:
            raise ValueError("Invalid Asian source timeout.")

    async def fetch(self, limit: int = 20) -> list[TenderNotice]:
        if self.name in ASIA_RSS_FEEDS:
            payload = await _fetch(ASIA_RSS_FEEDS[self.name], self.timeout, "application/rss+xml,application/xml,text/xml")
            return parse_asia_rss(payload, source=self.name, limit=limit)
        try:
            payload = await _fetch(JETRO_LISTS[self.name], self.timeout, "text/html")
            return parse_jetro_html(payload, source=self.name, limit=limit)
        except SourceError:
            # JETRO's default listing route can return only an empty search
            # form; retry once using the fixed, official full-form query.
            # Never accept an HTTP 200 or a generic news page as a tender.
            payload = await _fetch(JETRO_SEARCH_URLS[self.name], self.timeout, "text/html")
            return parse_jetro_html(payload, source=self.name, limit=limit)
