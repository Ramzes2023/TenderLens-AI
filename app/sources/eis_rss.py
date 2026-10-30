"""EIS (zakupki.gov.ru) RSS/Atom adapter.

Static source URLs can be configured by the operator. Phase 13 can also derive
per-company search feeds from the active profile's keywords while retaining the
static feeds as a fallback. Both RSS 2.0 and Atom payloads are accepted.
"""
from __future__ import annotations

import hashlib
import math
from contextlib import asynccontextmanager, nullcontext
import html
import re
import ssl
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

from .http import FetchPolicy, bounded_fetch, _policy, page_limit, source_client

from .models import TenderNotice
from .enrichment import enrichment as build_notice_enrichment
from .eis_deadlines import result_deadline


class SourceError(RuntimeError):
    pass


def eis_system_ssl_context() -> ssl.SSLContext:
    """Use Windows' server-auth trusted roots, without environment CA overrides.

    This is an operator opt-in, not a fallback after certificate failure.
    No certificate is downloaded or trusted merely because a server supplied it.
    """
    if not hasattr(ssl, "enum_certificates"):
        raise SourceError("EIS system trust requires the Windows certificate store")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    purpose = ssl.Purpose.SERVER_AUTH.oid
    # Windows' default trust loader consults both ROOT and CA stores.
    # Omitting CA can discard an intermediate needed for a verified chain.
    # Enumerate only the system's server-auth-trusted entries; never use
    # environment CA files, untrusted certificates, or TLS verification bypass.
    certificates = []
    for store in ("ROOT", "CA"):
        for cert, encoding, trust in ssl.enum_certificates(store):
            if encoding == "x509_asn" and (trust is True or purpose in trust):
                certificates.append(ssl.DER_cert_to_PEM_cert(cert))
    if not certificates:
        raise SourceError("Windows has no server-auth trusted roots")
    context.load_verify_locations(cadata="".join(certificates))
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = True
    return context


def eis_tls_verify(*, direct, system_trust, ca_bundle_file):
    if system_trust:
        if not direct or ca_bundle_file is not None:
            raise ValueError("EIS system trust requires direct=True and no CA bundle override")
        return eis_system_ssl_context()
    return str(ca_bundle_file) if ca_bundle_file else True


@asynccontextmanager
async def eis_client(factory, *, direct, **kwargs):
    """Bound direct discovery too; retain an existing worker request budget."""
    policy = (bounded_fetch(FetchPolicy(frozenset({'zakupki.gov.ru'}), 20,
                                       max_bytes=5 * 1024 * 1024))
              if direct and _policy.get() is None else nullcontext())
    with policy:
        async with factory(**kwargs) as client:
            yield client

EIS_EXTENDED_RSS_URL = "https://zakupki.gov.ru/epz/order/extendedsearch/rss.html"
# Operator-supplied links must originate from the publisher's own RSS action.
# /rss is a narrowly scoped candidate variant, NOT a verified working feed.
# Generated/default URLs remain unchanged until strict live publisher proof.
EIS_ALLOWED_RSS_PATHS = frozenset({
    "/epz/order/extendedsearch/rss.html",
    "/epz/order/extendedsearch/rss",
})


def build_eis_rss_url(search_term: str) -> str:
    """Build the same EIS filtered-search RSS shape used by the operator UI.

    The adapter keeps static EIS_RSS_URLS support; generated URLs are used only
    for per-company dynamic monitoring.
    """
    term = " ".join(search_term.split())
    if not term:
        raise ValueError("search_term must not be empty")
    query = urlencode({
        "searchString": term,
        "morphology": "on",
        "pageNumber": "1",
        "fz44": "on",
    })
    return f"{EIS_EXTENDED_RSS_URL}?{query}"


def build_eis_rss_urls(search_terms, *, max_feeds: int = 5) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in search_terms:
        term = " ".join(str(raw).split())
        key = term.casefold()
        if not term or key in seen:
            continue
        seen.add(key)
        result.append(build_eis_rss_url(term))
        if len(result) >= max(1, min(int(max_feeds), 20)):
            break
    return tuple(result)


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_NOTICE_RE = re.compile(r"(?<!\d)(\d{11,20})(?!\d)")
_PRICE_PATTERNS = (
    re.compile(r"(?:НМЦК|начальн(?:ая|ой)\s+цена|цена\s+контракта)[^\d]{0,40}([\d\s\u00a0]+(?:[,.]\d{1,2})?)", re.I),
    re.compile(r"([\d\s\u00a0]+(?:[,.]\d{1,2})?)\s*(?:₽|руб(?:\.|лей|ля)?)", re.I),
)
_CUSTOMER_RE = re.compile(r"(?:заказчик|организация)\s*[:\-]\s*([^;\n|]{3,300})", re.I)
_DEADLINE_RE = re.compile(r"(?:окончани[ея]\s+подачи\s+заявок|срок\s+подачи\s+заявок)\s*[:\-]\s*([^;\n|]{3,120})", re.I)
_REGION_RE = re.compile(r"(?:регион|место\s+поставки)\s*[:\-]\s*([^;\n|]{3,160})", re.I)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()



def _clean(
    value: str | None,
) -> str:
    """
    Normalize EIS text without breaking words around
    inline search-highlight tags.

    <b>Gold</b>hofer -> Goldhofer
    <b>Gold</b>en Eagle -> Golden Eagle
    """
    import html
    import re

    if value is None:
        return ""

    text = html.unescape(
        str(value)
    )

    # Structural HTML should create spacing.
    text = re.sub(
        r"(?is)<\s*br\s*/?\s*>",
        " ",
        text,
    )

    text = re.sub(
        (
            r"(?is)</\s*"
            r"(?:p|div|li|tr|td|h[1-6])"
            r"\s*>"
        ),
        " ",
        text,
    )

    # Inline formatting/search-highlight tags must
    # disappear without inserting spaces.
    text = re.sub(
        r"(?is)<[^>]+>",
        "",
        text,
    )

    return " ".join(
        text.split()
    )



def _child_text(element: ET.Element, names: set[str]) -> str:
    for child in list(element):
        if _local_name(child.tag) in names:
            text = "".join(child.itertext()) if list(child) else (child.text or "")
            cleaned = _clean(text)
            if cleaned:
                return cleaned
    return ""


def _entry_link(element: ET.Element) -> str:
    for child in list(element):
        if _local_name(child.tag) != "link":
            continue
        href = (child.attrib.get("href") or "").strip()
        if href:
            return href
        text = _clean(child.text)
        if text:
            return text
    return ""


def _parse_money(text: str) -> float | None:
    for pattern in _PRICE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        value = match.group(1).replace("\u00a0", "").replace(" ", "").replace(",", ".")
        try:
            return float(value)
        except ValueError:
            continue
    return None


def _extract(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return _clean(match.group(1)) if match else None


def _stable_id(guid: str, link: str, title: str, published: str) -> str:
    basis = guid or link or f"{title}|{published}"
    return hashlib.sha256(basis.encode("utf-8", errors="replace")).hexdigest()


# VALYQON EIS BUSINESS SUMMARY V1
def _extract_eis_labeled_field(
    text: str | None,
    label: str,
    stop_labels: tuple[str, ...],
) -> str | None:
    """Extract one business field from the verbose EIS RSS description."""

    cleaned = _clean(text or "")

    if not cleaned:
        return None

    folded = cleaned.lower()
    wanted = label.lower()

    start = folded.find(wanted)

    if start < 0:
        return None

    start += len(wanted)
    end = len(cleaned)

    for stop_label in stop_labels:
        position = folded.find(
            stop_label.lower(),
            start,
        )

        if position >= 0:
            end = min(
                end,
                position,
            )

    value = _clean(
        cleaned[start:end]
    ).strip(" :-")

    return value or None


def _eis_business_summary(
    description: str | None,
) -> str | None:
    """Return procurement content without EIS search-form metadata."""

    cleaned = _clean(
        description or ""
    )

    if not cleaned:
        return None

    procurement_object = (
        _extract_eis_labeled_field(
            cleaned,
            "\u041d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u0435 "
            "\u043e\u0431\u044a\u0435\u043a\u0442\u0430 "
            "\u0437\u0430\u043a\u0443\u043f\u043a\u0438:",
            (
                "\u0420\u0430\u0437\u043c\u0435\u0449\u0435\u043d\u0438\u0435 "
                "\u0432\u044b\u043f\u043e\u043b\u043d\u044f\u0435\u0442\u0441\u044f "
                "\u043f\u043e:",
                "\u041d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u0435 "
                "\u0417\u0430\u043a\u0430\u0437\u0447\u0438\u043a\u0430:",
                "\u041d\u0430\u0447\u0430\u043b\u044c\u043d\u0430\u044f "
                "\u0446\u0435\u043d\u0430 "
                "\u043a\u043e\u043d\u0442\u0440\u0430\u043a\u0442\u0430:",
                "\u0412\u0430\u043b\u044e\u0442\u0430:",
                "\u0420\u0430\u0437\u043c\u0435\u0449\u0435\u043d\u043e:",
                "\u041e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u043e:",
            ),
        )
    )

    if procurement_object:
        return procurement_object[:4000]

    result_marker = (
        "\u041d\u0430\u0439\u0434\u0435\u043d\u043d\u044b\u0439 "
        "\u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442:"
    )

    position = cleaned.lower().find(
        result_marker.lower()
    )

    if position >= 0:
        cleaned = _clean(
            cleaned[
                position
                + len(result_marker):
            ]
        )

    return cleaned[:4000] or None


def requires_eis_law_validation(client, url: str, *, direct: bool) -> bool:
    """Only legacy in-memory MockTransport fixtures may omit legal evidence.

    Inspect the selected route, not the factory identity or the feed content.
    Unknown clients/routes fail closed; direct-mode tests exercise the live gate.
    MockTransport results never establish live or independently verified law.
    """
    if direct:
        return True
    select = getattr(client, "_transport_for_url", None)
    if not callable(select):
        return True
    return type(select(httpx.URL(url))) is not httpx.MockTransport


def verify_eis_feed_law(payload: bytes, wanted: str) -> None:
    """Validate the whole feed before limiting records or assigning identity."""
    if len(payload) > 5 * 1024 * 1024:
        raise SourceError("EIS RSS exceeds 5 MiB")
    probe = payload.replace(b"\x00", b"").lower()
    if b"<!doctype" in probe or b"<!entity" in probe:
        raise SourceError("EIS DTD/entities rejected")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        raise SourceError("EIS malformed XML") from None
    if _local_name(root.tag) not in {"rss", "feed", "rdf"}:
        raise SourceError("EIS response is not a feed")
    for entry in root.iter():
        if _local_name(entry.tag) not in {"item", "entry"}:
            continue
        parts = urlsplit(_entry_link(entry))
        description = _child_text(entry, {"description", "summary", "content"})
        marker = "Найденный результат:"
        result = description.partition(marker)[2] if marker in description else description
        labels = re.findall(
            r"Размещение\s+выполняется\s+по\s*:\s*(44|223)\s*[-–]?\s*ФЗ\b", result, re.I)
        route = ("223-FZ" if parts.path.startswith("/223/purchase/public/purchase/")
                 else "44-FZ" if parts.path.startswith("/epz/order/notice/") else None)
        numbers = parse_qs(parts.query, keep_blank_values=True).get("regNumber", [])
        if (parts.scheme != "https" or parts.netloc != "zakupki.gov.ru"
                or parts.fragment or len(numbers) != 1
                or not re.fullmatch(r"[0-9]{11,20}", numbers[0])
                or route != wanted or not labels
                or {label + "-FZ" for label in labels} != {wanted}):
            raise SourceError("EIS law verification failed: mixed, unknown or conflicting result")


def validate_eis_direct_urls(urls) -> None:
    for raw in urls:
        parts = urlsplit(raw)
        if (parts.scheme != "https" or parts.netloc != "zakupki.gov.ru"
                or parts.path not in EIS_ALLOWED_RSS_PATHS or parts.fragment
                or "\\" in raw or any(c.isspace() or ord(c) < 32 for c in raw)):
            raise SourceError("Direct EIS requires the official HTTPS RSS endpoint")


def parse_eis_feed(payload: bytes, *, source_name: str = "eis") -> list[TenderNotice]:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        raise SourceError("ЕИС вернул некорректный RSS/Atom XML.") from None

    entries = [node for node in root.iter() if _local_name(node.tag) in {"item", "entry"}]
    notices: list[TenderNotice] = []
    for entry in entries:
        title = _child_text(entry, {"title"}) or "Закупка без названия"
        description = _child_text(entry, {"description", "summary", "content"})
        published = None
        published_raw = None
        published_path = None
        for date_node in list(entry):
            name = _local_name(date_node.tag)
            if name not in {"pubdate", "published", "updated"}:
                continue
            candidate = "".join(date_node.itertext()) if list(date_node) else (date_node.text or "")
            cleaned = _clean(candidate)
            if cleaned:
                published, published_raw, published_path = cleaned, candidate, name
                break
        guid = _child_text(entry, {"guid", "id"})
        link = _entry_link(entry)
        combined = _clean(" ".join(filter(None, [title, description])))
        number_match = _NOTICE_RE.search(combined + " " + link)
        tender_number = number_match.group(1) if number_match else None
        external_id = guid or tender_number or _stable_id(guid, link, title, published or "")
        # An explicit actual notice closing clock is safer than free-text
        # matches on the EIS advanced-search form or publication timestamp.
        deadline_text = result_deadline(description)
        notices.append(TenderNotice(
            source=source_name,
            external_id=external_id[:500],
            title=title[:1000],
            url=link[:2000],
            published_at=published,
            tender_number=tender_number,
            customer=(
                _extract_eis_labeled_field(
                    description,
                    "\u041d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u0435 "
                    "\u0417\u0430\u043a\u0430\u0437\u0447\u0438\u043a\u0430:",
                    (
                        "\u041d\u0430\u0447\u0430\u043b\u044c\u043d\u0430\u044f "
                        "\u0446\u0435\u043d\u0430 "
                        "\u043a\u043e\u043d\u0442\u0440\u0430\u043a\u0442\u0430:",
                        "\u0412\u0430\u043b\u044e\u0442\u0430:",
                        "\u0420\u0430\u0437\u043c\u0435\u0449\u0435\u043d\u043e:",
                        "\u041e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u043e:",
                        "\u042d\u0442\u0430\u043f "
                        "\u0440\u0430\u0437\u043c\u0435\u0449\u0435\u043d\u0438\u044f:",
                        "\u0418\u0434\u0435\u043d\u0442\u0438\u0444\u0438\u043a\u0430\u0446\u0438\u043e\u043d\u043d\u044b\u0439 "
                        "\u043a\u043e\u0434:",
                    ),
                )
                or _extract(
                    _CUSTOMER_RE,
                    combined,
                )
            ),
            initial_price=_parse_money(combined),
            currency="RUB" if re.search(r"(?:₽|руб(?:\.|лей|ля)?)", combined, re.I) else None,
            deadline=deadline_text,
            region=_extract(_REGION_RE, combined),
            summary=_eis_business_summary(description),
            enrichment=build_notice_enrichment(
                source_name, external_id[:500],
                dates={
                    'publication': {
                        'path': published_path or 'pubdate',
                        'value': published_raw,
                        'semantics': 'source_update' if published_path == 'updated' else 'published_at',
                        'raw_status': 'rss_text' if published_raw else 'missing',
                    },
                    'deadline': {
                        'path': 'description.deadline',
                        'value': deadline_text,
                        'raw_status': 'description_text' if deadline_text else 'missing',
                    },
                },
            ),
        ))
    return notices


@dataclass(frozen=True)
class EisRssSource:
    urls: tuple[str, ...]
    timeout: float = 30.0
    ca_bundle_file: Path | None = None
    name: str = "eis"
    direct: bool = False
    system_trust: bool = False

    def __post_init__(self):
        if not math.isfinite(self.timeout) or not 0 < self.timeout <= 120:
            raise ValueError("EIS timeout must be finite and in (0, 120]")

    def for_search_terms(self, search_terms, *, max_feeds: int = 5) -> "EisRssSource":
        generated = build_eis_rss_urls(search_terms, max_feeds=max_feeds)
        return EisRssSource(
            urls=generated or self.urls,
            timeout=self.timeout,
            ca_bundle_file=self.ca_bundle_file,
            name=self.name,
            direct=self.direct,
            system_trust=self.system_trust,
        )

    async def fetch(self, limit: int = 20) -> list[TenderNotice]:
        limit = max(1, min(int(limit), 100))
        if not self.urls:
            return []
        if self.direct:
            validate_eis_direct_urls(self.urls)
        verify = eis_tls_verify(direct=self.direct, system_trust=self.system_trust,
                                ca_bundle_file=self.ca_bundle_file)
        merged: list[TenderNotice] = []
        seen: set[tuple[str, str]] = set()
        try:
            async with eis_client(source_client, direct=self.direct,
                timeout=self.timeout,
                follow_redirects=not self.direct,
                verify=verify,
                trust_env=not self.direct,
                headers={"User-Agent": "TenderLensAI/0.9 (+RSS monitor)"},
            ) as client:
                for url in self.urls[:page_limit(len(self.urls))]:
                    response = await client.get(url)
                    response.raise_for_status()
                    payload = response.content
                    if len(payload) > 5 * 1024 * 1024:
                        raise SourceError("RSS ЕИС превышает безопасный лимит 5 МиБ.")
                    content_type = response.headers.get("content-type", "").lower()
                    if "html" in content_type or payload.lstrip().lower().startswith(b"<!doctype html"):
                        raise SourceError("ЕИС вернул HTML вместо RSS/Atom XML.")
                    if requires_eis_law_validation(client, url, direct=self.direct):
                        verify_eis_feed_law(payload, "44-FZ")
                    for notice in parse_eis_feed(payload, source_name=self.name):
                        if notice.identity in seen:
                            continue
                        seen.add(notice.identity)
                        merged.append(notice)
                        if len(merged) >= limit:
                            return merged
        except SourceError:
            raise
        except (httpx.HTTPError, OSError):
            raise SourceError("Не удалось получить RSS ЕИС: проверьте URL, сеть, proxy и TLS CA.") from None
        return merged
