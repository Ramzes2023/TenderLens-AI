"""Offline TEK-Torg export foundation; deliberately no SOAP client or live routing.

Input is an extracted, unnamespaced response fragment, NOT a verified SOAP
envelope. Procedure title/URL mapping is intentionally supplied separately.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Callable
from urllib.parse import parse_qsl, urlsplit
from xml.etree import ElementTree as ET

from .models import TenderNotice
from .opportunities import validate_notice

SOAP_URL = "https://api.tektorg.ru/procedures/soap"
WSDL_URL = "https://api.tektorg.ru/procedures/wsdl"
STATUS = "IMPLEMENTED_OFFLINE_NOT_LIVE"
MAX_BYTES = 2 * 1024 * 1024
MAX_PAGES = 5
FILTER_FIELDS = frozenset({"startDate", "endDate", "startUpdateAt", "endUpdateAt",
    "sectionCode", "registryNumber", "eisRegistryNumber", "typeId",
    "organizerINN", "customerINN", "limitPage", "sort", "page"})


def validate_filters(values: dict[str, str]) -> dict[str, str]:
    """Validate offline filter values; no guessed namespaces or serialization."""
    if type(values) is not dict or not set(values) <= FILTER_FIELDS:
        raise ValueError("Unknown export filter")
    for key, value in values.items():
        if (type(value) is not str or not value or len(value) > 200
                or any(ord(c) < 32 for c in value) or '<' in value or '>' in value):
            raise ValueError("Invalid filter value")
        if key in {"page", "limitPage"}:
            ceiling = MAX_PAGES if key == "page" else 500
            if not re.fullmatch(r"[1-9][0-9]*", value) or int(value) > ceiling:
                raise ValueError("Filter bound exceeded")
    return dict(values)


def validate_procedure_url(value: str) -> str:
    """Allow only explicit public TEK-Torg HTTPS links; never construct links."""
    if (type(value) is not str or len(value) > 2000 or not value
            or any(c.isspace() or ord(c) < 32 for c in value)
            or '\\' in value or '%' in value):
        raise ValueError("Invalid procedure URL")
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or parsed.netloc not in {'www.tektorg.ru', 'tektorg.ru'}
            or parsed.username is not None or parsed.password is not None
            or parsed.fragment or not parsed.path or parsed.path == '/'):
        raise ValueError("Unapproved procedure URL")
    if any(key.casefold() in {'token', 'access_token', 'api_key', 'apikey', 'password', 'secret'}
           for key, _ in parse_qsl(parsed.query, keep_blank_values=True)):
        raise ValueError("Credential-bearing URL")
    return value


@dataclass(frozen=True)
class ExportProcedure:
    section_code: str
    procedure_id: str
    xml: bytes

    @property
    def external_id(self) -> str:
        return json.dumps([self.section_code, self.procedure_id], ensure_ascii=False,
                          separators=(',', ':'))


@dataclass(frozen=True)
class ExportPage:
    total: int
    current_page: int
    total_pages: int
    page_size: int
    section_code: str
    section_name: str
    procedures: tuple[ExportProcedure, ...]
    payload_sha256: str


def parse_export_fragment(payload: bytes) -> ExportPage:
    """Parse documented fields from an offline fragment with caller-selected root.

    Root name is deliberately unspecified: the condensed evidence does not give
    the response wrapper. Namespaces/SOAP envelopes require verified WSDL first.
    """
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_BYTES:
        raise ValueError("Invalid payload bound")
    try:
        text = payload.decode('utf-8')
    except UnicodeError:
        raise ValueError("UTF-8 fragment required") from None
    if re.search(r'<!\s*(?:DOCTYPE|ENTITY)', text, re.I) or '\x00' in text:
        raise ValueError("DTD/entities forbidden")
    if re.search(r'<\?xml[^>]*encoding\s*=\s*[\"\'](?!utf-8[\"\'])', text, re.I):
        raise ValueError("UTF-8 fragment required")
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        raise ValueError("Malformed XML") from None
    pending = [(root, 0)]
    count = 0
    while pending:
        node, depth = pending.pop()
        count += 1
        if (depth > 16 or count > 20000 or not isinstance(node.tag, str)
                or '{' in node.tag or any('{' in key for key in node.attrib)):
            raise ValueError("Unsupported XML structure")
        pending.extend((child, depth + 1) for child in node)
    expected = {'totalProcedures', 'currentPage', 'totalPage', 'limitProceduresInPage',
                'sectionName', 'sectionCode', 'procedures'}
    children = list(root)
    if (root.attrib or (root.text or '').strip() or
            any((child.tail or '').strip() for child in children) or
            len(children) != len(expected) or {c.tag for c in children} != expected):
        raise ValueError("Invalid response fields")
    def scalar(name):
        node = root.find(name)
        if node is None or len(node) or node.attrib:
            raise ValueError("Invalid scalar")
        value = (node.text or '').strip()
        if not value or len(value) > 200:
            raise ValueError("Invalid scalar")
        return value
    def number(name, minimum, maximum):
        value = scalar(name)
        if not re.fullmatch(r'0|[1-9][0-9]*', value) or not minimum <= int(value) <= maximum:
            raise ValueError("Invalid pagination")
        return int(value)
    total = number('totalProcedures', 0, 10**9)
    current = number('currentPage', 1, MAX_PAGES)
    pages = number('totalPage', 0, 10**9)
    size = number('limitProceduresInPage', 1, 500)
    section = scalar('sectionCode')
    name = scalar('sectionName')
    container = root.find('procedures')
    if container.attrib or (container.text or '').strip():
        raise ValueError("Invalid procedure container")
    records = []
    seen = set()
    for node in container:
        if node.tag != 'procedure' or (node.tail or '').strip():
            raise ValueError("Invalid procedure container")
        ids = node.findall('id')
        if len(ids) != 1 or len(ids[0]) or ids[0].attrib:
            raise ValueError("Missing/ambiguous procedure id")
        identifier = (ids[0].text or '').strip()
        if not identifier or len(identifier) > 200 or identifier in seen:
            raise ValueError("Invalid/duplicate section identity")
        seen.add(identifier)
        records.append(ExportProcedure(section, identifier, ET.tostring(node, encoding='utf-8')))
    if (len(records) > size or len(records) > total
            or pages != (total + size - 1) // size
            or current > max(1, pages)
            or len(records) != (min(size, total - (current - 1) * size) if total else 0)):
        raise ValueError("Inconsistent pagination")
    return ExportPage(total, current, pages, size, section, name, tuple(records),
                      hashlib.sha256(payload).hexdigest())


@dataclass(frozen=True)
class TekTorgOfflineSource:
    """Opt-in offline replay implementing TenderSource; no automatic ingestion.

    Projector is an explicit integration seam, not an inferred XML field map.
    Page digest and original record XML remain available to that projector.
    """
    pages: tuple[bytes, ...] = ()
    projector: Callable[[ExportProcedure, ExportPage], TenderNotice] | None = None
    enabled: bool = False
    name: str = 'tektorg'

    async def fetch(self, limit: int = 20) -> list[TenderNotice]:
        if not self.enabled:
            return []
        if self.name != 'tektorg' or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Invalid offline source configuration")
        if not self.projector or not 1 <= len(self.pages) <= MAX_PAGES:
            raise ValueError("Bounded offline pages and explicit projector required")
        parsed = [parse_export_fragment(payload) for payload in self.pages]
        previous = {}
        seen = set()
        result = []
        for page in parsed:
            prior = previous.get(page.section_code)
            if ((prior is None and page.current_page != 1) or (prior is not None and
                    (page.current_page != prior.current_page + 1 or
                     (page.total, page.total_pages, page.page_size, page.section_name) !=
                     (prior.total, prior.total_pages, prior.page_size, prior.section_name)))):
                raise ValueError("Non-contiguous/inconsistent offline pages")
            previous[page.section_code] = page
            for procedure in page.procedures:
                if procedure.external_id in seen:
                    raise ValueError("Duplicate section identity across pages")
                seen.add(procedure.external_id)
                notice = self.projector(procedure, page)
                validate_notice(notice, 'tektorg')
                validate_procedure_url(notice.url)
                if notice.external_id != procedure.external_id:
                    raise ValueError("Projector changed section identity")
                result.append(notice)
        return result[:limit]
