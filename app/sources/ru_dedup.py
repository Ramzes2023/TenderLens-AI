"""Collapse only explicit matching EIS references; retain original notices."""
import json
import re
from urllib.parse import parse_qs, urlsplit


def procedure_key(notice):
    if notice.source == 'ru_ingushetia_fabrikant44':
        parts = urlsplit(notice.url)
        number = notice.tender_number
        match = re.fullmatch(r'/44/procedure/[a-z0-9-]{2,18}/([0-9]{19})', parts.path)
        if (parts.scheme == 'https' and parts.netloc == '44.fabrikant.ru'
                and not parts.query and not parts.fragment
                and match and match.group(1) == number):
            return '44', number
        return None
    if notice.source not in {'eis', 'eis_223', 'b2b_center', 'ru_ingushetia_eis44'}:
        return None
    url = notice.url
    if notice.source == 'b2b_center':
        try:
            url = json.loads(notice.summary or '{}').get('upstream_url') or ''
        except (ValueError, AttributeError):
            return None
    parts = urlsplit(url)
    if parts.scheme != 'https' or parts.netloc != 'zakupki.gov.ru' or parts.fragment:
        return None
    law = ('223' if parts.path.startswith('/223/purchase/public/purchase/') else
           '44' if parts.path.startswith('/epz/order/notice/') else None)
    numbers = parse_qs(parts.query, keep_blank_values=True).get('regNumber', [])
    if law and len(numbers) == 1 and re.fullmatch(r'[0-9]{11,20}', numbers[0]):
        return law, numbers[0]
    return None


def deduplicate(notices):
    groups = {}
    for notice in notices:
        key = procedure_key(notice) or notice.identity
        groups.setdefault(key, []).append(notice)
    result, provenance = [], []
    for group in groups.values():
        primary = next((n for n in group if n.source in {'eis', 'eis_223'}), group[0])
        result.append(primary)
        if len(group) > 1:
            provenance.append(tuple(group))
    return tuple(result), tuple(provenance)
