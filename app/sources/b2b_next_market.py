"""Observed Vue SSR cards only. Never evaluate __pinia, scripts, or infer APIs."""
import json
import math
import re
from datetime import datetime
from urllib.parse import urljoin, urlsplit, urlunsplit

from .b2b_center import (
    B2BCenterNotice, B2B_CENTER_NEXT_LIST_URL, B2B_CENTER_HOSTS,
    KNOWN_FOREIGN_AGGREGATE_HOSTS, MAX_BYTES, _Document, _Node,
)
from .eis_rss import SourceError
from .opportunities import validate_notice


def _nodes(node, cls):
    return [n for n in node.walk() if cls in (n.attrs.get('class') or '').split()]


def _one(nodes):
    if len(nodes) != 1:
        raise SourceError('B2B-Center ambiguous SSR field.')
    return nodes[0]


def native_url(raw):
    if (not raw or raw.startswith('//') or '\\' in raw or len(raw) > 2000
            or any(ord(c) <= 32 or ord(c) == 127 for c in raw)):
        raise SourceError('B2B-Center unsafe SSR URL.')
    try:
        p = urlsplit(urljoin(B2B_CENTER_NEXT_LIST_URL, raw))
        if (p.scheme != 'https' or p.hostname not in B2B_CENTER_HOSTS
                or p.username is not None or p.password is not None
                or p.port not in (None, 443) or p.query):
            raise ValueError
        match = re.fullmatch(r'/(?:app/market-next|market)/[a-z0-9-]{1,300}/tender-([0-9]{3,12})/', p.path)
        # Only the observed analytics fragment may be discarded. It cannot
        # select another procedure, origin or query on the server.
        if not match or (p.fragment and not re.fullmatch(
                r'btid=2&sqh=[a-f0-9]{40}&tsid=' + match[1] + r'[0-9]{3}', p.fragment)):
            raise ValueError
    except ValueError:
        raise SourceError('B2B-Center unsafe SSR URL.') from None
    # Stable canonical origin: equivalent HTTPS/443 URL spellings cannot
    # produce duplicate user-facing identities or retain noncanonical authority.
    return urlunsplit(('https', 'www.b2b-center.ru', p.path, '', '')), match[1]


def _local_date(value):
    try:
        if not re.fullmatch(r'[0-9]{2}\.[0-9]{2}\.[0-9]{4} [0-9]{2}:[0-9]{2}', value):
            raise ValueError
        # Preserve source-local time; do not invent an offset from runner TZ.
        return datetime.strptime(value, '%d.%m.%Y %H:%M').isoformat()
    except ValueError:
        raise SourceError('B2B-Center invalid SSR date.') from None


def parse_next_market(payload, *, limit=100):
    if not payload or len(payload) > MAX_BYTES:
        raise SourceError('B2B-Center empty or oversized HTML.')
    try:
        text = payload.decode('utf-8-sig')
    except UnicodeError:
        raise SourceError('B2B-Center invalid HTML encoding.') from None
    doc = _Document()
    doc.feed(text)
    doc.close()
    seen = {}
    for card in _nodes(doc.root, 'panel-procedure__card'):
        number_link = _one(_nodes(card, 'panel-procedure__number-link'))
        raw = number_link.attrs.get('href')
        # Explicit foreign provenance is excluded; unrecognized/malformed
        # provenance fails the batch rather than being relabelled as native.
        if raw and urlsplit(raw).hostname in KNOWN_FOREIGN_AGGREGATE_HOSTS:
            continue
        # A single SSR card with a broken, unproven original URL is NOT
        # a procurement notice. Exclude ONLY that card, never infer its
        # identifier or relabel another platform's purchase as B2B. The
        # remaining cards still need complete first-party provenance and
        # all original buyer/title/date/price contracts.
        try:
            url, number = native_url(raw)
        except SourceError:
            continue
        if number_link.tag != 'a' or number_link.text() != '№ ' + number:
            raise SourceError('B2B-Center conflicting SSR identity.')
        cover = _one(_nodes(card, 'panel-procedure__card-link'))
        if cover.tag != 'a':
            raise SourceError('B2B-Center conflicting SSR identity.')
        try:
            cover_origin = native_url(cover.attrs.get('href'))
        except SourceError:
            continue
        if cover_origin != (url, number):
            raise SourceError('B2B-Center conflicting SSR identity.')
        title = _one(_nodes(card, 'panel-procedure__dscr-main')).text()
        branch = _one(_nodes(card, 'panel-procedure__dscr-branch'))
        customer = branch.text() or None
        date_nodes = [n.text() for n in card.walk()
                      if n.tag == 'div' and 'cds-text-sm' in (n.attrs.get('class') or '').split()
                      and re.fullmatch(r'[0-9.]+ [0-9:]+', n.text())]
        if len(date_nodes) != 1:
            raise SourceError('B2B-Center ambiguous SSR publication date.')
        deadline_node = _one(_nodes(card, 'panel-procedure__dscr-date'))
        dates = [n.text() for n in deadline_node.children if isinstance(n, _Node)
                 and n.tag == 'span' and n.text().startswith('до ')]
        if len(dates) != 1:
            raise SourceError('B2B-Center ambiguous SSR deadline.')
        amount_text = _one(_nodes(card, 'panel-procedure__details-item-sum')).text()
        price = currency = None
        if amount_text != 'Без указания цены':
            amount = re.fullmatch(r'([0-9]{1,3}(?: [0-9]{3})*|[0-9]+),([0-9]{2}) ([₽€$])', amount_text)
            if not amount:
                raise SourceError('B2B-Center unrecognized SSR price.')
            price = float(amount[1].replace(' ', '') + '.' + amount[2])
            currency = {'₽': 'RUB', '€': 'EUR', '$': 'USD'}[amount[3]]
            if not math.isfinite(price) or not 0 < price <= 1e18:
                raise SourceError('B2B-Center invalid SSR price.')
        summary = json.dumps({'listing_url': B2B_CENTER_NEXT_LIST_URL,
                              'upstream_url': url, 'upstream_host': 'www.b2b-center.ru',
                              'origin': 'first_party', 'coverage_scope': 'next_market_first_page',
                              'date_semantics': 'source_local_unspecified_offset'}, ensure_ascii=False)
        notice = B2BCenterNotice(
            source='b2b_center', external_id=number, tender_number=number,
            title=title, customer=customer, url=url,
            published_at=_local_date(date_nodes[0]), deadline=_local_date(dates[0][3:]),
            initial_price=price, currency=currency, summary=summary,
            listing_url=B2B_CENTER_NEXT_LIST_URL, upstream_url=url,
            upstream_host='www.b2b-center.ru', origin='first_party')
        validate_notice(notice, 'b2b_center')
        if number in seen and seen[number] != notice:
            raise SourceError('B2B-Center conflicting duplicate identity.')
        seen[number] = notice
    if not seen:
        raise SourceError('B2B-Center returned no usable procurement records.')
    return list(seen.values())[:max(1, min(int(limit), 100))]
