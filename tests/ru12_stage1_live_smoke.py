"""One authorized acquisition per Stage 1 source; ephemeral SQLite snapshot proof.

No captured response is promoted to live evidence. Run with an existing app env.
"""
import asyncio
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def run():
    names = ('EIS 44-FZ', 'EIS 223-FZ', 'B2B-Center')
    result = {'ai_query_verified': False, 'sources': {name: {
        'state': 'BLOCKED', 'database_upserts': 0, 'query_matches': 0,
        'reason': 'Not completed'} for name in names}}
    try:
        from app.database.backend import Database
        from app.database.config import DatabaseSettings
        from app.sources.eis_rss import EisRssSource, EIS_EXTENDED_RSS_URL
        from app.sources.eis_223_rss import Eis223RssSource
        from app.sources.b2b_center import B2BCenterSource
        from app.sources.catalog import SourceCatalog
        from app.sources.multi import MultiSourceFetcher
        from app.sources.opportunities import OpportunityRepository
        from app.sources.registry import SourceRegistry, SourceRegistration
        from app.sources.ru08_integration import LocalBoundedSource, save_and_query, HOSTS
        from app.sources.http import bounded_fetch, FetchPolicy, source_client
    except ImportError as error:
        for entry in result['sources'].values():
            entry['reason'] = 'App runtime dependency unavailable: ' + (error.name or type(error).__name__)
        return result
    adapters = (EisRssSource((EIS_EXTENDED_RSS_URL + '?fz44=on',), timeout=15, direct=True),
                Eis223RssSource((EIS_EXTENDED_RSS_URL + '?fz223=on',), timeout=15, direct=True),
                B2BCenterSource(timeout=15))
    registry = SourceRegistry(SourceRegistration(a.name, name, LocalBoundedSource(a, a.name))
                              for name, a in zip(names, adapters))
    catalog = SourceCatalog(registry, MultiSourceFetcher(registry, concurrency=1))
    with tempfile.TemporaryDirectory(prefix='ru12-', dir=Path.cwd()) as isolated:
        repo = OpportunityRepository(Database(DatabaseSettings('ru12-isolated', Path(isolated) / 'notices.sqlite')))
        repo.initialize()
        for name, adapter in zip(names, adapters):
            entry = result['sources'][name]
            try:
                report = await catalog.fetch(source_keys=(adapter.name,), limit_per_source=10)
                if report.failures:
                    entry['reason'] = 'Acquisition/law rejected: ' + report.failures[0].error_type
                    continue
                if not report.notices:
                    entry['reason'] = 'No real notices acquired'
                    continue
                details = []
                # Verify actual returned URLs using the unchanged public-IP/TLS transport.
                with bounded_fetch(FetchPolicy(HOSTS[adapter.name], len(report.notices), max_bytes=5*1024*1024)):
                    async with source_client(timeout=15, trust_env=False, follow_redirects=False) as client:
                        for notice in report.notices:
                            response = await client.get(notice.url)
                            response.raise_for_status()
                            details.append({'external_id': notice.external_id, 'url': notice.url,
                                            'published_at': notice.published_at, 'deadline': notice.deadline,
                                            'detail_status': response.status_code})
                entry['notices'] = details
                upserts, matches = await save_and_query(catalog, repo, adapter.name, report.notices)
                entry.update(database_upserts=upserts, query_matches=matches,
                             state='SNAPSHOT_ROUNDTRIP_VERIFIED',
                             reason='Fresh acquisition and detail HTTP checks; dates preserved as observed. '
                                    'Snapshot keyword query only; active deadline freshness requires review.')
            except Exception as error:
                entry['reason'] = 'Acquisition/detail/storage blocked: ' + type(error).__name__
    return result


if __name__ == '__main__':
    print(json.dumps(asyncio.run(run()), ensure_ascii=False, indent=2))
