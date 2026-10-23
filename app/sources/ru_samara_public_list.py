"""Opt-in Samara official public-list procurement adapter, disabled by default.

Authentic first-party public list provides ID, number, title and buyer.
Independently verified detail pages are not yet established; never present them as
verified or usable. No proxy, auth, redirects, TLS bypass or production writes.
"""
from __future__ import annotations
import calendar
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
import math
import re
from urllib.parse import urljoin, urlsplit

from .http import FetchPolicy, _policy, bounded_fetch, source_client
from .models import TenderNotice
from .opportunities import validate_notice

SOURCE_ID = "ru_samara_public_list"
HOST = "webtorgi.samregion.ru"
GRID = "https://" + HOST + "/smallpurchases/GzwSP/NoticesGrid"
JSON_URL = "https://" + HOST + "/smallpurchases/GzwSP/NoticesJson"
PATH = "/smallpurchases/GzwSP/NoticesJson"
MAX_BYTES = 1_800_000
PAGE_SIZE = 10
DETAIL_PATTERN = re.compile(r"/smallpurchases/GzwSP/([0-9]{6,12})\Z")
NATIVE_NUMBER = re.compile(r"ИМЗ-20[0-9]{2}-[0-9-]{5,20}\Z", re.I)
SORT_COLUMNS = {
    "pub_date": "Дата публикации",
    "number": "Рег. номер",
    "name": "Наименование",
    "summa": "НМЦК",
    "uchr_sname": "Заказчик",
    "collecting_endDate": "Дата окончания подачи заявок",
}


class GridToken(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.tokens = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "div":
            self.stack.append((self.stack[-1] if self.stack else False)
                              or "grid_filter" in (a.get("class") or "").split())
        if tag == "input" and self.stack and self.stack[-1]:
            if a.get("name") == "__RequestVerificationToken":
                self.tokens.append(a.get("value"))

    def handle_endtag(self, tag):
        if tag == "div" and self.stack:
            self.stack.pop()


def public_token(body):
    if type(body) is not bytes or not 0 < len(body) <= MAX_BYTES or b"\0" in body:
        raise ValueError("Invalid original public Samara grid")
    if PATH.encode("ascii") not in body:
        raise ValueError("Official public page does not advertise native JSON path")
    parser = GridToken()
    parser.feed(body.decode("utf-8-sig", "replace"))
    parser.close()
    distinct = set(parser.tokens)
    if len(distinct) != 1:
        raise ValueError("Ambiguous original anonymous grid token")
    token = next(iter(distinct))
    if type(token) is not str or not re.fullmatch(r"[A-Za-z0-9_./+=~-]{20,2048}", token):
        raise ValueError("Invalid anonymous public grid token")
    return token


def previous_month(today=None):
    if today is None:
        today = datetime.now(timezone(timedelta(hours=4))).date()
    if type(today) is not date:
        raise ValueError("Invalid Samara local date")
    y, m = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    d = min(today.day, calendar.monthrange(y, m)[1])
    return date(y, m, d).strftime("%d.%m.%Y")


def public_settings(today=None):
    return {
        "page": 0,
        "rp": PAGE_SIZE,
        "totalRows": 0,
        "sortField": "pub_date",
        "sortDir": "desc",
        "filter": {"dtDatePubBegin": {
            "PName": "dtDatePubBegin", "PType": "Date",
            "PValue": previous_month(today),
        }},
        "sortList": SORT_COLUMNS,
        "rpList": [10, 20, 30],
        "localFilter": [],
    }


def canonical_id(raw):
    if type(raw) is not str or not 0 < len(raw) <= 1800 or "\\" in raw:
        raise ValueError("Invalid first-party listing detail reference")
    if any(c.isspace() or ord(c) < 32 for c in raw):
        raise ValueError("Unsafe first-party listing link")
    try:
        parsed = urlsplit(urljoin(GRID, raw))
    except ValueError:
        raise ValueError("Invalid original Samara listing URL") from None
    match = DETAIL_PATTERN.fullmatch(parsed.path)
    if (parsed.scheme != "https" or parsed.hostname != HOST or
            parsed.port not in (None, 443) or parsed.username or
            parsed.password or parsed.query or parsed.fragment or not match):
        raise ValueError("Noncanonical original Samara list identity")
    return match.group(1)


def safe_string(row, key, max_length=1000):
    value = row.get(key)
    if (type(value) is not str or
            not 3 <= len(value.strip()) <= max_length or
            "\0" in value or re.search(r"<\s*/?\s*[a-zA-Z][^>]*>", value)):
        raise ValueError("Missing or untrusted first-party list field")
    return " ".join(value.split())



def public_amount(raw):
    """Normalize first-party table НМЦК without guessing missing amounts.

    Only genuine list-level `summa`, never the inaccessible detail card.
    """
    if type(raw) is int:
        # Native JSON may contain unbounded-precision ints. Bound them before
        # float conversion so one malformed optional price cannot abort an
        # otherwise valid real page of municipal procurement notices.
        if not 0 < raw <= 1e18:
            return None
        amount = float(raw)
    elif type(raw) is float:
        if not math.isfinite(raw):
            return None
        amount = raw
    elif type(raw) is str and len(raw) <= 80:
        # Thousands separators occur in native Russian UI and test fixtures.
        value = raw.strip().replace("\u00a0", " ").replace("\u202f", " ")
        plain = re.fullmatch(r"[0-9]+(?:[.,][0-9]{1,2})?", value)
        grouped = re.fullmatch(r"[0-9]{1,3}(?: [0-9]{3})+(?:,[0-9]{1,2})?", value)
        if not plain and not grouped:
            return None
        amount = float(value.replace(" ", "").replace(",", "."))
    else:
        return None
    return amount if math.isfinite(amount) and 0 < amount <= 1e18 else None


def public_grid_date(raw):
    """Preserve a source-published calendar deadline, never invent a clock time.

    The Samara official anonymous list publishes dd.mm.yyyy or its timed
    variant. Keep date-only values as date-only, not midnight/end-of-day.
    """
    if type(raw) is not str or len(raw) > 35:
        return None
    value = raw.strip()
    if not re.fullmatch(r"[0-9]{2}\.[0-9]{2}\.20[0-9]{2}(?: [0-9]{2}:[0-9]{2}(?::[0-9]{2})?)?", value):
        return None
    try:
        fmt = ("%d.%m.%Y %H:%M:%S" if value.count(":") == 2 else
               "%d.%m.%Y %H:%M" if ":" in value else "%d.%m.%Y")
        moment = datetime.strptime(value, fmt)
    except ValueError:
        return None
    # Retain the original date-only/time semantics. Local UTC offset is not
    # present in the public list, so do not inject an assumed timezone.
    return moment.isoformat(timespec="seconds") if value.count(":") == 2 else value

def public_deadline(row):
    """Accept either real native JSON field spelling, never a conflicting value.

    The original grid advertises collecting_endDate; some publisher responses
    and research exports use the lower-case 'collecting_enddate'.  Do not
    manufacture missing or contradictory calendar deadlines.
    """
    if type(row) is not dict:
        return None
    first = row.get("collecting_endDate")
    second = row.get("collecting_enddate")
    if first is not None and second is not None and first != second:
        return None
    return public_grid_date(first if first is not None else second)


def parse_public_list(data, *, limit=2):
    """Validate original Samara public-list rows; live worker demands two."""
    if type(limit) is not int or not 1 <= limit <= PAGE_SIZE:
        raise ValueError("Invalid list size")
    if type(data) is not dict or type(data.get("items")) is not list:
        raise ValueError("Samara original native JSON items missing")
    rows = data["items"]
    total = data.get("totalRows")
    if (type(total) is not int or total < len(rows)
            or not 0 <= len(rows) <= PAGE_SIZE
            or (not rows and total != 0)):
        raise ValueError("Inconsistent public notice list rows")
    notices, ids, numbers = [], set(), set()
    for row in rows[:limit]:
        if type(row) is not dict:
            raise ValueError("Nonobject original notice row")
        identity = canonical_id(row.get("link"))
        number = safe_string(row, "number", 250)
        if NATIVE_NUMBER.fullmatch(number) is None:
            raise ValueError("Missing Samara native municipal purchase number")
        title = safe_string(row, "name", 1000)
        buyer = safe_string(row, "uchr_sname", 2000)
        if identity in ids or number in numbers:
            raise ValueError("Duplicated original listing notice identity")
        ids.add(identity)
        numbers.add(number)
        # Price and dates below are directly from original anonymous JSON
        # table fields. Individual detail documents are STILL login-protected.
        price = public_amount(row.get("summa"))
        published = public_grid_date(row.get("pub_date"))
        deadline = public_deadline(row)
        # The native HTML grid labels "summa" as НМЦК (in rubles).
        # Keep unknown/zero/unsafe amounts absent, not synthetic.
        notice = TenderNotice(
            source=SOURCE_ID,
            external_id=identity,
            tender_number=number,
            title=title,
            url=GRID,
            customer=buyer,
            published_at=published,
            initial_price=price,
            currency="RUB" if price is not None else None,
            deadline=deadline,
            region="Самарская область",
            summary="Публичный реестр малых закупок Самарской области. "
                    "Подробная карточка может требовать авторизацию; "
                    "Цена и даты (когда указаны) взяты из публичного "
                    "списка, не из закрытой карточки; ищите по "
                    "регистрационному номеру: " + number,
        )
        validate_notice(notice, SOURCE_ID)
        notices.append(notice)
    return notices


@dataclass(frozen=True)
class SamaraPublicListSource:
    timeout: float = 25
    name: str = SOURCE_ID

    def __post_init__(self):
        if (self.name != SOURCE_ID or type(self.timeout) not in (int, float) or
                not math.isfinite(self.timeout) or not 0 < self.timeout <= 30):
            raise ValueError("Invalid public list-only source configuration")

    async def fetch(self, limit=20):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Invalid public list fetch limit")
        # First-party pages 0, 1, and 2 independently returned thirty
        # distinct native notices in the exact-head live research gate.
        # Further native pages are unverified, and may not be fetched.
        cap = min(limit, 3 * PAGE_SIZE)
        pages = (cap + PAGE_SIZE - 1) // PAGE_SIZE
        max_calls = 1 + pages
        ctx = (bounded_fetch(FetchPolicy(frozenset({HOST}), max_calls,
                                         max_bytes=MAX_BYTES))
               if _policy.get() is None else nullcontext())
        with ctx:
            async with source_client(
                timeout=self.timeout,
                trust_env=False,
                follow_redirects=False,
                headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0"},
            ) as client:
                landing = await client.get(GRID)
                landing.raise_for_status()
                if "html" not in landing.headers.get("content-type", "").lower():
                    raise ValueError("No public Samara HTML grid")
                token = public_token(landing.content)
                headers = {
                    "Accept": "application/json, text/javascript",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": GRID,
                    "RequestVerificationToken": token,
                }
                found, ids, numbers = [], set(), set()
                for page in range(pages):
                    settings = public_settings()
                    settings["page"] = page
                    response = await client.post(
                        JSON_URL, json={"settings": settings}, headers=headers,
                    )
                    response.raise_for_status()
                    if "application/json" not in response.headers.get("content-type", "").lower():
                        raise ValueError("No native first-party JSON media type")
                    if not 0 < len(response.content) <= MAX_BYTES:
                        raise ValueError("Native public listing response too large")
                    payload = response.json()
                    rows = parse_public_list(
                        payload, limit=min(PAGE_SIZE, cap - len(found)),
                    )
                    for notice in rows:
                        if notice.external_id in ids or notice.tender_number in numbers:
                            raise ValueError("Duplicate Samara procurement across native pages")
                        ids.add(notice.external_id)
                        numbers.add(notice.tender_number)
                    found.extend(rows)
                    if len(rows) < PAGE_SIZE or payload["totalRows"] <= len(found):
                        break
                return found
