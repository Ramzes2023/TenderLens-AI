"""Explicit local RU-08 contract. Never load runtime settings or credentials.

Unavailable platforms are diagnostic registrations, not connected adapters.
"""
from dataclasses import dataclass
import asyncio
import json
import re
from urllib.parse import parse_qs, urlsplit

from .b2b_center import B2BCenterSource
from .catalog import SourceCatalog
from .eis_rss import EisRssSource, build_eis_rss_url, SourceError
from .eis_223_rss import Eis223RssSource, build_eis_223_rss_url
from .http import FetchPolicy, bounded_fetch
from .multi import MultiSourceFetcher
from .opportunities import validate_notice
from .registry import SourceRegistration, SourceRegistry, SourceTransport
from .snapshots import snapshot_catalog

SOURCE_KEYS = {
    'eis_44fz': 'eis', 'eis_223fz': 'eis_223', 'b2b_center': 'b2b_center',
    'tektorg': 'tektorg', 'roseltorg': 'roseltorg', 'fabrikant': 'fabrikant',
}
HOSTS = {'eis': frozenset({'zakupki.gov.ru'}),
         'eis_223': frozenset({'zakupki.gov.ru'}),
         'b2b_center': frozenset({'www.b2b-center.ru'})}
BLOCKERS = {
    'tektorg': ('OFFLINE_ONLY', 'Secure offline XML parser exists; public capture HTTP 307; no verified live contract.'),
    'roseltorg': ('BLOCKED', 'Both public listings timed out; no body or repeated records captured. Not connected.'),
    'fabrikant': ('BLOCKED', 'Both public listings timed out; no body captured. Indexed cards do not prove host acquisition. Not connected.'),
}


@dataclass(frozen=True)
class UnavailableSource:
    name: str

    async def fetch(self, limit=20):
        raise SourceError(BLOCKERS[self.name][1])


@dataclass(frozen=True)
class LocalBoundedSource:
    """One anonymous public listing request; no redirects, retry or detail fetch."""
    source: object
    name: str

    async def fetch(self, limit=20):
        with bounded_fetch(FetchPolicy(
            HOSTS[self.name], 2 if self.name == 'b2b_center' else 1,
            max_bytes=(2 if self.name == 'b2b_center' else 5) * 1024 * 1024,
        )):
            return await asyncio.wait_for(self.source.fetch(min(limit, 20)), timeout=25)


def local_catalog(*, enable_eis223=False, enable_b2b=False):
    """Flags are in-memory test arguments; normal production defaults stay OFF."""
    adapters = [
        ('eis', EisRssSource((build_eis_rss_url('поставка'),), timeout=15), True),
        ('eis_223', Eis223RssSource((build_eis_223_rss_url('поставка'),), timeout=15), enable_eis223),
        ('b2b_center', B2BCenterSource(timeout=15), enable_b2b),
    ]
    registrations = [SourceRegistration(
        key=key, display_name=key, source=LocalBoundedSource(source, key),
        transport=SourceTransport.HTML if key == 'b2b_center' else SourceTransport.RSS,
        jurisdictions=('RU',), languages=('ru',), enabled=enabled,
    ) for key, source, enabled in adapters]
    registrations += [SourceRegistration(key=key, display_name=key,
        source=UnavailableSource(key), enabled=False, jurisdictions=('RU',), languages=('ru',))
        for key in BLOCKERS]
    registry = SourceRegistry(registrations)
    return SourceCatalog(registry, MultiSourceFetcher(registry, concurrency=1))


def eis_reference(notice):
    """Link explicit EIS numbers only; never infer identity from title similarity."""
    url = notice.url
    if notice.source not in {'eis', 'eis_223'}:
        try:
            provenance = json.loads(notice.summary or '{}')
            url = provenance.get('upstream_url') or ''
        except (ValueError, AttributeError):
            return None
    parts = urlsplit(url)
    if parts.scheme != 'https' or parts.hostname not in {'zakupki.gov.ru', 'www.zakupki.gov.ru'}:
        return None
    numbers = parse_qs(parts.query).get('regNumber', [])
    if not numbers and notice.source in {'eis', 'eis_223'}:
        numbers = [notice.tender_number or '']
    return numbers[0] if len(numbers) == 1 and re.fullmatch(r'\d{11,25}', numbers[0]) else None


def duplicate_diagnostics(notices):
    groups = {}
    for notice in notices:
        number = eis_reference(notice)
        if number:
            groups.setdefault(number, []).append(list(notice.identity))
    return {'eis_references': groups,
            'cross_source_links': {key: value for key, value in groups.items()
                                   if len({item[0] for item in value}) > 1},
            'note': 'EIS-linked aggregate records are not new unique coverage; unlinked records have unknown uniqueness.'}


async def save_and_query(catalog, repository, key, notices, *, progress=None):
    """Verify exact identity AND URL through the existing user snapshot query path."""
    unique = {notice.identity: notice for notice in notices}
    upserts = matches = 0
    snapshot = snapshot_catalog(catalog, repository)
    for notice in unique.values():
        validate_notice(notice, key)
        if urlsplit(notice.url).hostname not in HOSTS[key]:
            raise ValueError('Unexpected source detail host')
        repository.upsert(notice, f'connector-sync-v1:{key}:adapter-r1')
        upserts += 1
        if progress is not None:
            progress['database_upserts'] = upserts
        report = await snapshot.fetch(source_keys=(key,), search_terms=(notice.external_id,), limit_per_source=100)
        if any(item.identity == notice.identity and item.url == notice.url for item in report.notices):
            matches += 1
        if progress is not None:
            progress['query_matches'] = matches
    return upserts, matches
