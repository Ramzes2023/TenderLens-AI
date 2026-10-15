"""Opt-in public MikroTon Tender v1 acquisition, documented API for aggregators.

Only publicly published rows from the original HTTPS API are normalized.
No credentials, invented notices, proxy, redirects, TLS bypass or production
configuration changes. Schema reference: https://tender.mt52.ru/api-docs
"""
from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
import json
import math
import re
from urllib.parse import urlsplit

from .http import FetchPolicy, bounded_fetch, _policy, source_client
from .models import TenderNotice
from .opportunities import validate_notice

SOURCE_ID = "mikroton_tender"
HOST = "tender.mt52.ru"
BASE = f"https://{HOST}/api/v1"
OPEN_LIST = BASE + "/tenders?page=1&page_size=10"
ARCHIVE_LIST = BASE + "/tenders/archive?page=1&page_size=10"
MAX_BYTES = 1024 * 1024
MAX_LIST_ITEMS = 10


def _str(value, *, max_length: int = 1000, required: bool = False):
    if value is None:
        if required:
            raise ValueError("Required public field missing")
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise ValueError("Invalid public text")
    if "\x00" in value or re.search(r"<\s*/?\s*[a-zA-Z][^>]*>", value):
        raise ValueError("Invalid public text")
    return value.strip()


class _PlainDescription(HTMLParser):
    """Convert public explanatory markup to inert text, excluding active tags."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.blocked = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"script", "style", "iframe", "object", "svg", "template"}:
            self.blocked += 1

    def handle_endtag(self, tag):
        if tag.lower() in {"script", "style", "iframe", "object", "svg", "template"}:
            self.blocked = max(0, self.blocked - 1)

    def handle_data(self, data):
        if self.blocked == 0:
            self.parts.append(data)


def _summary(value):
    if value is None:
        return None
    if type(value) is not str or len(value) > 20000 or "\\x00" in value:
        raise ValueError("Invalid public description")
    parser = _PlainDescription()
    parser.feed(value)
    parser.close()
    text = " ".join(" ".join(parser.parts).split())
    return _str(text[:4000], max_length=4000) if text else None


def _date(value):
    if value is None:
        return None
    cleaned = _str(value, max_length=120)
    parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Date missing source timezone")
    return parsed.isoformat()


def _portal_url(value, identity: int):
    raw = _str(value, max_length=2000, required=True)
    u = urlsplit(raw)
    if (u.scheme != "https" or u.netloc != HOST or u.username or u.password
            or u.fragment or u.query or u.path != f"/tenders/{identity}"):
        raise ValueError("Portal notice URL does not match source identity")
    return raw


def parse_listing(payload: bytes) -> list[TenderNotice]:
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_BYTES:
        raise ValueError("Invalid public API response size")
    body = json.loads(payload)
    if (type(body) is not dict or type(body.get("meta")) is not dict
            or body["meta"].get("api_version") != "v1"
            or type(body.get("items")) is not list
            or len(body["items"]) > MAX_LIST_ITEMS):
        raise ValueError("Unexpected public API response contract")
    seen = set()
    out = []
    for row in body["items"]:
        if type(row) is not dict:
            raise ValueError("Invalid public procurement record")
        identity = row.get("id")
        if type(identity) is not int or identity <= 0 or identity in seen:
            raise ValueError("Invalid or duplicate procurement identity")
        seen.add(identity)
        customer_obj = row.get("customer")
        if customer_obj is not None and type(customer_obj) is not dict:
            raise ValueError("Invalid customer object")
        customer = (_str(customer_obj.get("name"), max_length=2000)
                    if customer_obj else None)
        amount = row.get("start_price")
        if amount is not None and (type(amount) not in (int, float)
                or not math.isfinite(amount) or amount < 0 or amount > 1e18):
            raise ValueError("Invalid price")
        currency = (_str(row.get("currency"), max_length=3)
                    if amount is not None else None)
        if currency is not None and not re.fullmatch(r"[A-Z]{3}", currency):
            raise ValueError("Invalid currency")
        notice = TenderNotice(
            source=SOURCE_ID,
            external_id=str(identity),
            title=_str(row.get("title"), required=True),
            url=_portal_url(row.get("portal_url"), identity),
            published_at=_date(row.get("created_at")),
            deadline=_date(row.get("submission_deadline")),
            customer=customer,
            initial_price=amount,
            currency=currency,
            summary=_summary(row.get("description")),
        )
        validate_notice(notice, SOURCE_ID)
        out.append(notice)
    return out


@dataclass(frozen=True)
class MikrotonTenderSource:
    timeout: float = 20
    name: str = SOURCE_ID

    def __post_init__(self):
        if (self.name != SOURCE_ID or not math.isfinite(self.timeout)
                or not 0 < self.timeout <= 30):
            raise ValueError("Invalid Russian public API configuration")

    async def fetch(self, limit: int = 20) -> list[TenderNotice]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Invalid source request bound")
        policy = (bounded_fetch(FetchPolicy(frozenset({HOST}), 2, max_bytes=MAX_BYTES))
                  if _policy.get() is None else nullcontext())
        results = {}
        with policy:
            async with source_client(
                timeout=self.timeout, trust_env=False, follow_redirects=False,
                headers={"Accept": "application/json"},
            ) as client:
                for url in (OPEN_LIST, ARCHIVE_LIST):
                    response = await client.get(url)
                    response.raise_for_status()
                    if response.status_code != 200 or "json" not in response.headers.get("content-type", "").lower():
                        raise ValueError("Unexpected public API HTTP response")
                    for notice in parse_listing(response.content):
                        previous = results.get(notice.external_id)
                        if previous and previous != notice:
                            raise ValueError("Conflicting open/archive public identity")
                        results[notice.external_id] = notice
        return list(results.values())[:limit]
