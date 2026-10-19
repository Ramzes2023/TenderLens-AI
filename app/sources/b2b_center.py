"""Evidence-backed B2B-Center aggregate listing; no upstream/detail fetches."""
from __future__ import annotations

import json
import math
import re
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from .eis_rss import SourceError
from .http import ConnectorTransportError, FetchPolicy, bounded_fetch, source_client, _policy
from .models import TenderNotice
from .opportunities import validate_notice

B2B_CENTER_NEXT_LIST_URL = 'https://www.b2b-center.ru/app/next/market-search/?from=0'
B2B_CENTER_LIST_URL = 'https://www.b2b-center.ru/search/'
# Unrestricted aggregate responses can exceed the audited 2 MiB cap.
# This official category is an explicitly LIMITED partial fallback.
B2B_CENTER_OFFICE_LIST_URL = 'https://www.b2b-center.ru/search/industry/ofis/'
B2B_CENTER_HOSTS = frozenset({'www.b2b-center.ru'})
# The public aggregate search mixes other procurement platforms into its feed.
# These are NOT B2B-Center notices; do not fetch, normalize or store them as B2B.
# All other external hosts, including lookalikes, remain fail-closed.
KNOWN_FOREIGN_AGGREGATE_HOSTS = frozenset({
    'www.rosatom.rts-tender.ru', 'www.rts-tender.ru', 'otc.ru', 'www.otc.ru',
    'zakupki.gov.ru',
})
MAX_BYTES = 2 * 1024 * 1024


class B2BNoNativeNotices(SourceError):
    """Structured public foreign records were found, but no native procedure."""


@dataclass
class _Node:
    tag: str
    attrs: dict[str, str | None] = field(default_factory=dict)
    children: list = field(default_factory=list)

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, _Node):
                yield from child.walk()

    def text(self):
        return ' '.join(' '.join(child.text() if isinstance(child, _Node) else child
                                 for child in self.children).split())


class _Document(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node('root')
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        if len(self.stack) >= 128:
            raise SourceError('B2B-Center HTML nesting exceeds bound.')
        node = _Node(tag, dict(attrs))
        self.stack[-1].children.append(node)
        if tag not in {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
                       'link', 'meta', 'param', 'source', 'track', 'wbr'}:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if self.stack[-1].tag == tag:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        if self.stack[-1].tag not in {'script', 'style'}:
            self.stack[-1].children.append(data)


def _property(node, prop, tag='meta'):
    # Direct children only: line-item names/prices must not replace notice fields.
    values = {child.attrs.get('content' if tag == 'meta' else 'href', '')
              for child in node.children if isinstance(child, _Node)
              and child.tag == tag and child.attrs.get('itemprop') == prop}
    values.discard('')
    if len(values) > 1:
        raise SourceError('B2B-Center returned conflicting structured properties.')
    return next(iter(values), None)


def _safe_url(raw, *, detail=False):
    if (not raw or raw.startswith('//') or '\\' in raw
            or any(ord(char) <= 32 or ord(char) == 127 for char in raw)):
        raise SourceError('B2B-Center returned unsafe notice URL.')
    url = urljoin(B2B_CENTER_LIST_URL, raw)
    try:
        parts = urlsplit(url)
        if (parts.scheme not in {'https', 'http'} or not parts.hostname
                or parts.username is not None or parts.password is not None
                or parts.port not in (None, 443 if parts.scheme == 'https' else 80)
                or parts.fragment or len(url) > 2000):
            raise ValueError
        if detail and (parts.scheme != 'https' or parts.hostname not in B2B_CENTER_HOSTS
                       or parts.query or not re.fullmatch(r'/search/number/[A-Za-z0-9-]{1,100}/', parts.path)):
            raise ValueError
    except ValueError:
        raise SourceError('B2B-Center returned unsafe notice URL.') from None
    return url


def _date(value):
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.isoformat()
    except ValueError:
        raise SourceError('B2B-Center returned invalid structured date.') from None


@dataclass(frozen=True)
class B2BCenterNotice(TenderNotice):
    listing_url: str = B2B_CENTER_LIST_URL
    upstream_url: str | None = None
    upstream_host: str | None = None
    origin: str = 'unknown'


def parse_b2b_center_listing(payload: bytes, *, limit=100, listing_url=B2B_CENTER_LIST_URL) -> list[TenderNotice]:
    if listing_url not in (B2B_CENTER_LIST_URL, B2B_CENTER_OFFICE_LIST_URL):
        raise SourceError('Unapproved B2B-Center public listing origin.')
    if not payload or len(payload) > MAX_BYTES:
        raise SourceError('B2B-Center empty or oversized HTML.')
    try:
        text = payload.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise SourceError('B2B-Center invalid HTML encoding.') from None
    document = _Document()
    document.feed(text)
    document.close()
    seen = {}
    has_foreign_records = False
    for card in document.root.walk():
        if (card.tag != 'div' or 'cards' not in (card.attrs.get('class') or '').split()
                or card.attrs.get('itemtype') != 'https://schema.org/ListItem'):
            continue
        organizations = [node for node in card.walk()
                         if node.attrs.get('itemtype') == 'https://schema.org/Organization']
        demands = [node for node in card.walk()
                   if node.attrs.get('itemtype') == 'https://schema.org/Demand']
        # Ignore explicitly known *other platforms* in the aggregate listing.
        # No HTTP requests to foreign hosts; never label their cards as B2B.
        foreign = []
        for candidate in demands:
            raw_detail = _property(candidate, 'url', 'link')
            if not raw_detail or '\\' in raw_detail or any(ord(ch) <= 32 for ch in raw_detail):
                foreign.append(False)
                continue
            parts = urlsplit(urljoin(B2B_CENTER_LIST_URL, raw_detail))
            foreign.append(parts.scheme == 'https'
                and parts.hostname in KNOWN_FOREIGN_AGGREGATE_HOSTS
                and parts.username is None and parts.password is None
                and parts.port in (None, 443) and not parts.fragment)
        if demands and all(foreign):
            has_foreign_records = True
            continue
        # Some genuine public B2B cards omit the Organization entity. Keep
        # customer unknown; never fabricate one or infer it from other cards.
        # Multiple organizations/demands still fail closed as ambiguous.
        if len(organizations) > 1 or len(demands) != 1:
            raise SourceError('B2B-Center unexpected procurement card structure.')
        demand = demands[0]
        if _property(demand, 'businessFunction') != 'http://purl.org/goodrelations/v1#Buy':
            continue
        url = _safe_url(_property(demand, 'url', 'link'), detail=True)
        external_id = urlsplit(url).path.split('/')[-2]
        title = _property(demand, 'name')
        if not title:
            raise SourceError('B2B-Center procurement title missing.')
        references = {(node.attrs.get('href'), node.text()) for node in demand.walk()
                      if node.tag == 'a' and re.fullmatch(r'Закупка №[A-Za-z0-9-]+(?: в ЕИС)?', node.text())}
        if len(references) > 1:
            raise SourceError('B2B-Center conflicting original notice references.')
        upstream, number = None, None
        if references:
            raw, label = next(iter(references))
            # The search wrapper alone cannot prove native ownership.
            # Unsafe provenance stays unverified and is excluded below;
            # never erase it to relabel another platform's purchase as B2B.
            try:
                upstream = _safe_url(raw)
            except SourceError:
                upstream = None
            if upstream is not None:
                number = label.removeprefix('Закупка №').removesuffix(' в ЕИС')
        host = urlsplit(upstream).hostname if upstream else None
        # A same-host search wrapper does not turn another platform's purchase
        # into a B2B procedure. Malformed optional provenance cannot erase this
        # distinction either. Require the native procedure reference and its
        # matching number; l-prefixed search IDs occur for BOTH native/foreign.
        native_parts = urlsplit(upstream) if upstream else None
        native_path = native_parts.path if native_parts else ''
        native = re.fullmatch(r'/(?:app/market-next|market)/[^/]+/tender-([0-9]+)/', native_path)
        if (host not in B2B_CENTER_HOSTS or native_parts.scheme != 'https' or
                native_parts.query or native is None or
                number != native.group(1) or
                not (external_id == number or external_id.startswith('l' + number + '-'))):
            if upstream is not None and host not in B2B_CENTER_HOSTS:
                has_foreign_records = True
            continue
        origin = 'first_party'
        # Original reference is retained in the base contract as well as provenance,
        # so repository/snapshot/scoring reconstruction cannot silently lose it.
        summary = json.dumps({'listing_url': listing_url, 'upstream_url': upstream,
                              'upstream_host': host, 'origin': origin,
                              'coverage_scope': ('office_only' if listing_url == B2B_CENTER_OFFICE_LIST_URL
                                                 else 'aggregate')}, ensure_ascii=False)
        prices = set()
        for node in demand.walk():
            if (node.attrs.get('itemprop') == 'priceSpecification'
                    and 'card-item__properties-cell' in (node.attrs.get('class') or '').split()):
                raw_price = _property(node, 'price')
                currency = _property(node, 'priceCurrency')
                if raw_price is not None and currency == 'RUB':
                    try:
                        price = float(raw_price)
                    except ValueError:
                        raise SourceError('B2B-Center invalid price.') from None
                    if not math.isfinite(price) or not 0 <= price <= 1e18:
                        raise SourceError('B2B-Center invalid price.')
                    prices.add(price)
        # Zero means unspecified in some cards; multiple specifications may be lots.
        price = next(iter(prices)) if len(prices) == 1 and 0 not in prices else None
        notice = B2BCenterNotice(
            source='b2b_center', external_id=external_id, title=title, url=url,
            tender_number=number,
            customer=(_property(organizations[0], 'name') if organizations else None),
            published_at=_date(_property(demand, 'validFrom')),
            deadline=_date(_property(demand, 'validThrough')),
            initial_price=price, currency='RUB' if price is not None else None,
            summary=summary, listing_url=listing_url,
            upstream_url=upstream, upstream_host=host, origin=origin)
        validate_notice(notice, 'b2b_center')
        if external_id in seen and seen[external_id] != notice:
            raise SourceError('B2B-Center conflicting duplicate identity.')
        seen[external_id] = notice
    if not seen:
        kind = B2BNoNativeNotices if has_foreign_records else SourceError
        raise kind('B2B-Center returned no usable procurement records.')
    return [seen[key] for key in sorted(seen)][:max(1, min(int(limit), 100))]


@dataclass(frozen=True)
class B2BCenterSource:
    timeout: float = 30
    name: str = 'b2b_center'
    listing_url: str = B2B_CENTER_NEXT_LIST_URL

    def __post_init__(self):
        if self.listing_url not in (B2B_CENTER_NEXT_LIST_URL, B2B_CENTER_LIST_URL):
            raise ValueError('Unapproved B2B-Center listing.')
        if not math.isfinite(self.timeout) or not 0 < self.timeout <= 120 or self.name != 'b2b_center':
            raise ValueError('Invalid B2B-Center source configuration.')

    async def fetch(self, limit=20):
        # Always use the existing bounded transport, including direct discovery.
        # No redirect, pagination, scripts, cookies or external detail requests.
        # Preserve worker policy and counters instead of replacing its budget.
        policy = (bounded_fetch(FetchPolicy(B2B_CENTER_HOSTS, 2, max_bytes=MAX_BYTES))
                  if _policy.get() is None else nullcontext())
        with policy:
            async with source_client(timeout=self.timeout, follow_redirects=False,
                                     trust_env=False, headers={'Accept': 'text/html'}) as client:
                try:
                    response = await client.get(self.listing_url)
                    response.raise_for_status()
                    if response.status_code != 200:
                        raise SourceError('B2B-Center listing unavailable.')
                    if self.listing_url == B2B_CENTER_NEXT_LIST_URL:
                        from .b2b_next_market import parse_next_market
                        return parse_next_market(response.content, limit=limit)
                    return parse_b2b_center_listing(response.content, limit=limit)
                except ConnectorTransportError as error:
                    if self.listing_url == B2B_CENTER_NEXT_LIST_URL or error.reason != 'response_size':
                        raise
                except B2BNoNativeNotices:
                    # An otherwise valid public aggregate can contain only
                    # foreign purchases. Never relabel them to force success.
                    pass
                # The alternate official listing is deliberately partial:
                # never fabricate full-aggregate coverage or missing records.
                client.cookies.clear()
                fallback = await client.get(B2B_CENTER_OFFICE_LIST_URL)
                fallback.raise_for_status()
                if fallback.status_code != 200:
                    raise SourceError('B2B-Center bounded office listing unavailable.')
                return parse_b2b_center_listing(
                    fallback.content, limit=limit, listing_url=B2B_CENTER_OFFICE_LIST_URL,
                )
