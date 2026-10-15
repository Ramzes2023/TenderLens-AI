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
_MAX_BYTES = 1024 * 1024
_CLEAN = re.compile(r"\s+")
_JETRO_LINK = re.compile(
    r"^/en/database/procurement/(national|local)/articles/([0-9]+)/([0-9]+)\.html$"
)
_JETRO_DATE = re.compile(r"\b[A-Z][a-z]{2} [0-9]{1,2}, 20[0-9]{2}\b")


def _text(value: str | None) -> str:
    return _CLEAN.sub(" ", re.sub(r"<[^>]+>", " ", html.unescape(value or ""))).strip()


def _safe_link(value: str, hosts: frozenset[str], *, base: str | None = None) -> str:
    if not value or any(ord(char) < 32 or char == "\\" for char in value):
        raise SourceError("Asian source provided an unsafe item URL.")
    candidate = urljoin(base, value) if base else value
    try:
        part = urlsplit(candidate)
        if (part.scheme != "https" or part.hostname not in hosts
                or part.username or part.password or part.port not in (None, 443)
                or part.fragment):
            raise ValueError()
    except ValueError:
        raise SourceError("Asian source provided an unsafe item URL.") from None
    return candidate


def _published(value: str | None) -> str | None:
    if not _text(value):
        return None
    try:
        parsed = parsedate_to_datetime(_text(value))
        if parsed.tzinfo is None:
            return None
        return parsed.isoformat()
    except (TypeError, ValueError, IndexError):
        return None


def parse_asia_rss(payload: bytes, *, source: str, limit: int = 20) -> list[TenderNotice]:
    if source not in ASIA_RSS_FEEDS or len(payload) > _MAX_BYTES:
        raise SourceError("Unapproved or oversized Asian RSS source.")
    if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise SourceError("Asian RSS contains forbidden XML declarations.")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        raise SourceError("Asian procurement RSS is malformed.") from None
    if root.tag not in ("rss", "{http://www.w3.org/2005/Atom}feed"):
        raise SourceError("Asian procurement endpoint did not return RSS/Atom.")
    hosts = frozenset({"www.housingauthority.gov.hk", "housingauthority.gov.hk"}) if source.startswith("hk_ha_") else frozenset({"www.emsd.gov.hk", "emsd.gov.hk"})
    output: list[TenderNotice] = []
    seen: set[str] = set()
    atom = "{http://www.w3.org/2005/Atom}"
    items = root.findall("./channel/item") if root.tag == "rss" else root.findall(f"./{atom}entry")
    for item in items:
        title = _text(item.findtext("title") if root.tag == "rss" else item.findtext(f"{atom}title"))
        raw_link = item.findtext("link") if root.tag == "rss" else next(
            (link.get("href", "") for link in item.findall(f"{atom}link") if link.get("rel", "alternate") == "alternate"),
            "",
        )
        if not title or not raw_link:
            continue
        try:
            link = _safe_link(_text(raw_link), hosts)
        except SourceError:
            continue
        guid = _text(item.findtext("guid") if root.tag == "rss" else item.findtext(f"{atom}id"))
        identity = guid or link
        external_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:40]
        if external_id in seen:
            continue
        seen.add(external_id)
        raw_date = item.findtext("pubDate") if root.tag == "rss" else item.findtext(f"{atom}published")
        description = (item.findtext("description") if root.tag == "rss"
                       else item.findtext(f"{atom}summary"))
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
    except (httpx.HTTPError, OSError):
        raise SourceError("Asian procurement endpoint is currently unavailable.") from None


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
        payload = await _fetch(JETRO_LISTS[self.name], self.timeout, "text/html")
        return parse_jetro_html(payload, source=self.name, limit=limit)
