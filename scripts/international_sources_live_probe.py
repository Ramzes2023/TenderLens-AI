"""Explicit anonymous live checks for this phase only; no settings/DB/keys."""
import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.sources.catalog import SourceCatalog
from app.sources.multi import MultiSourceFetcher
from app.sources.registry import SourceRegistration, SourceRegistry
from app.sources.ted_api import TedApiSource
from app.sources.uk_fts_api import UkFindTenderApiSource
from app.sources.world_bank import WorldBankSource
from app.sources.http import source_client
from app.sources.opportunities import validate_notice


def international_catalog():
    registry = SourceRegistry(SourceRegistration(key=source.name, display_name=label, source=source)
        for source, label in [(TedApiSource(timeout=20), 'EU / TED'),
                              (UkFindTenderApiSource(timeout=20), 'UK Find a Tender'),
                              (WorldBankSource(timeout=20), 'World Bank Finances One')])
    return SourceCatalog(registry, MultiSourceFetcher(registry))


async def probe():
    observations = []

    class RecordedClient:
        def __init__(self, **kwargs):
            self.client = source_client(**kwargs)

        async def __aenter__(self):
            await self.client.__aenter__()
            return self

        async def __aexit__(self, *args):
            return await self.client.__aexit__(*args)

        async def record(self, method, url, **kwargs):
            entry = {'host': __import__('urllib.parse', fromlist=['urlsplit']).urlsplit(url).hostname,
                     'method': method, 'checked_at': datetime.now(timezone.utc).isoformat()}
            observations.append(entry)
            try:
                response = await getattr(self.client, method)(url, **kwargs)
                entry.update(http_status=response.status_code, bytes=len(response.content))
                if response.status_code == 200:
                    payload = response.json()
                    items = payload.get('notices', payload.get('releases', payload.get('data', [])))
                    entry['raw_records'] = len(items)
                return response
            except Exception as error:
                entry['error_type'] = type(error).__name__
                raise

        async def post(self, url, **kwargs):
            return await self.record('post', url, **kwargs)

        async def get(self, url, **kwargs):
            return await self.record('get', url, **kwargs)

    with patch('app.sources.ted_api.source_client', RecordedClient), patch('app.sources.uk_fts_api.source_client', RecordedClient), patch('app.sources.world_bank.source_client', RecordedClient):
        catalog = international_catalog()
        report = await catalog.fetch(limit_per_source=20, search_terms=['construction', 'engineering'])
        for notice in report.notices:
            validate_notice(notice, notice.source)
        narrow_queries = {}
        # TED supports real server-side expert text search; other feeds are
        # transparently matched locally against this bounded recent batch.
        for term in ('aluminium profiles', 'aluminium constructions'):
            try:
                notices = await TedApiSource(timeout=20).for_search_terms([term]).fetch(5)
                narrow_queries[term] = {'ted': len(notices)}
            except Exception as error:
                narrow_queries[term] = {'ted_error': str(error)}
            for source in ('uk_fts', 'world_bank'):
                narrow_queries[term][source + '_local_batch'] = sum(
                    term in (n.title + ' ' + (n.summary or '')).casefold()
                    for n in report.notices if n.source == source)
    url_checks = []
    async with source_client(timeout=10, trust_env=False, follow_redirects=False) as client:
        for source in ('ted', 'uk_fts', 'world_bank'):
            notice = next((n for n in report.notices if n.source == source), None)
            if notice is None:
                url_checks.append({'source': source, 'state': 'no_notice_in_current_batch'})
                continue
            try:
                response = await client.get(notice.url)
                url_checks.append({'source': source, 'http_status': response.status_code,
                                   'url': notice.url, 'published_at': notice.published_at,
                                   'deadline': notice.deadline})
            except Exception as error:
                url_checks.append({'source': source, 'error_type': type(error).__name__})
    return {'checked_at': datetime.now(timezone.utc).isoformat(),
            'attempted_sources': list(report.attempted_sources),
            'successful_sources': list(report.successful_sources),
            'failures': [asdict(f) for f in report.failures],
            'statuses': [asdict(s) for s in report.statuses],
            'normalized_notices': [asdict(n) for n in report.notices],
            'observations': observations, 'url_checks': url_checks,
            'narrow_queries': narrow_queries,
            'limitations': 'UK one-hour update window; World Bank seven calendar days and 200 records; TED max 100 per query. No full-market recall claim.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/intl-sources-20261014_162147/live_final.json')
    args = parser.parse_args()
    if not args.live:
        print('SKIP: --live required; no outbound calls.')
        raise SystemExit(0)
    result = asyncio.run(probe())
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in result.items() if key != 'normalized_notices'}, indent=2))
