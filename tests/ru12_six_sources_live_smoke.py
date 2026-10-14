"""No-argument host runner. Captures are observations, never acquisition input."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TARGETS = {'eis_44fz': ('eis', 'EIS 44-FZ'),
           'eis_223fz': ('eis_223', 'EIS 223-FZ'),
           'b2b_center': ('b2b_center', 'B2B-Center'),
           'tektorg': ('tektorg', 'TEK-Torg'),
           'roseltorg': ('roseltorg', 'Roseltorg'),
           'fabrikant': ('fabrikant', 'Fabrikant')}

STAGES = ('fetch', 'law', 'parse', 'ingestion', 'freshness', 'detail', 'keyword-search')


def exception_frames(error):
    """Types and repository-relative frames only; never exception messages/locals.

    Inspect suppressed context too: worker and transport deliberately sanitize
    their outward errors using `from None`.
    """
    root = Path(__file__).resolve().parents[1]
    result, seen = [], set()
    while isinstance(error, BaseException) and id(error) not in seen:
        seen.add(id(error))
        frames, tb = [], error.__traceback__
        while tb is not None:
            try:
                filename = Path(tb.tb_frame.f_code.co_filename).resolve().relative_to(root).as_posix()
            except ValueError:
                filename = '<runtime>'
            frames.append(dict(file=filename, line=tb.tb_lineno))
            tb = tb.tb_next
        result.append(dict(type=type(error).__name__, frames=frames))
        error = error.__cause__ or error.__context__
    return result


def blank():
    return dict(state='BLOCKED', proof_origin='offline', fixture_used=False,
                http_status=None, records=0, db=0, query=0, sample_notice_id='',
                sample_notice_url='', response_sha256='', reason='Not acquired',
                stages={stage: 'UNVERIFIED' for stage in STAGES}, exceptions=[])


def fresh(notice, now=None):
    now = now or datetime.now(timezone.utc)
    def date(value):
        if not value:
            return None
        for parse in (lambda v: datetime.fromisoformat(v.replace('Z', '+00:00')),
                      parsedate_to_datetime,
                      lambda v: datetime.strptime(v, '%d.%m.%Y %H:%M'),
                      lambda v: datetime.strptime(v, '%d.%m.%Y')):
            try:
                result = parse(value)
                # Local dates have no verified UTC offset: compare calendar days only.
                return result.date()
            except (ValueError, TypeError, OverflowError):
                pass
        return None
    published, deadline = date(notice.published_at), date(notice.deadline)
    return (published is not None and now.date() - timedelta(days=30) <= published <= now.date()
            and (deadline is None or deadline >= now.date()))


async def verify_detail(notice, hosts):
    from app.sources.http import bounded_fetch, FetchPolicy, source_client
    from urllib.parse import urlsplit, parse_qs
    parts = urlsplit(notice.url)
    if parts.scheme != 'https' or parts.hostname not in hosts:
        raise ValueError('Unapproved detail URL')
    identifier = (parse_qs(parts.query).get('regNumber', [''])[0]
                  if notice.source.startswith('eis') else notice.external_id)
    if not identifier or (notice.source.startswith('eis') and not re.fullmatch(r'\d{11,25}', identifier)):
        raise ValueError('Detail identity absent')
    if notice.source == 'eis' and not parts.path.startswith('/epz/order/notice/'):
        raise ValueError('44-FZ detail route mismatch')
    if notice.source == 'eis_223' and not parts.path.startswith('/223/purchase/'):
        raise ValueError('223-FZ detail route mismatch')
    with bounded_fetch(FetchPolicy(hosts, 1, max_bytes=5*1024*1024)):
        from app.sources.eis_rss import eis_system_ssl_context
        verify = (eis_system_ssl_context() if notice.source.startswith('eis')
                  and os.environ.get('EIS_SYSTEM_TRUST_ENABLED', '').lower() == 'true' else True)
        async with source_client(timeout=15, trust_env=False, follow_redirects=False, verify=verify) as client:
            response = await client.get(notice.url)
            response.raise_for_status()
            text = response.text
            if response.status_code != 200 or identifier not in text:
                raise ValueError('Detail body does not confirm notice identity')
            if re.search(r'captcha|access denied|robot verification', text, re.I):
                raise ValueError('Detail access challenge')


async def compare_eis_trust():
    """Independent secure host probe; HTTP 200 alone is not ingestion proof."""
    import certifi
    import ssl
    from app.sources.eis_rss import eis_system_ssl_context, EIS_EXTENDED_RSS_URL
    from app.sources.http import bounded_fetch, FetchPolicy, source_client
    result = {}
    for name in ('certifi', 'windows_roots'):
        entry = result[name] = {'state': 'UNVERIFIED'}
        try:
            context = (ssl.create_default_context(cafile=certifi.where())
                       if name == 'certifi' else eis_system_ssl_context())
            entry['roots'] = context.cert_store_stats()['x509_ca']
            entry['cert_required'] = context.verify_mode == ssl.CERT_REQUIRED
            entry['check_hostname'] = context.check_hostname
            with bounded_fetch(FetchPolicy(frozenset({'zakupki.gov.ru'}), 1, max_bytes=5*1024*1024)):
                async with source_client(verify=context, trust_env=False,
                                         follow_redirects=False, timeout=15) as client:
                    response = await client.get(EIS_EXTENDED_RSS_URL + '?fz44=on')
                    entry.update(state='TLS_VERIFIED', http_status=response.status_code)
        except Exception as error:
            entry.update(state='BLOCKED', exceptions=exception_frames(error))
    return result


def run(run_dir, *, proof_origin='host_live'):
    result = {'sources': {key: blank() for key in TARGETS}, 'ai_query_verified': False,
              'ai_query_evidence': 'No authenticated AI search session; existing snapshot keyword search only.'}
    try:
        from app.database.backend import Database
        from app.database.config import DatabaseSettings
        from app.sources import eis_rss, eis_223_rss, b2b_center
        from app.sources.catalog import SourceCatalog
        from app.sources.multi import MultiSourceFetcher
        from app.sources.registry import SourceRegistry, SourceRegistration
        from app.sources.opportunities import OpportunityRepository
        from app.sources.ingestion import ConnectorSyncHandler, connector_version, sync_window, SYSTEM_SCOPE, HOSTS
        from app.sources.snapshots import snapshot_catalog
    except ImportError as error:
        for report_key, entry in result['sources'].items():
            entry['reason'] = 'Runtime dependency unavailable: ' + str(error.name)
            print(TARGETS[report_key][1] + ': BLOCKED — ' + entry['reason'], flush=True)
        return result
    system_trust = os.environ.get('EIS_SYSTEM_TRUST_ENABLED', '').lower() == 'true'
    adapters = {
        'eis': (eis_rss, eis_rss.EisRssSource((eis_rss.EIS_EXTENDED_RSS_URL+'?fz44=on',), timeout=15, direct=True, system_trust=system_trust)),
        'eis_223': (eis_223_rss, eis_223_rss.Eis223RssSource((eis_rss.EIS_EXTENDED_RSS_URL+'?fz223=on',), timeout=15, direct=True, system_trust=system_trust)),
        'b2b_center': (b2b_center, b2b_center.B2BCenterSource(timeout=15))}
    registry = SourceRegistry(SourceRegistration(key, label, adapters[key][1])
                              for key, label in TARGETS.values() if key in adapters)
    catalog = SourceCatalog(registry, MultiSourceFetcher(registry, concurrency=1))
    # A fresh child directory prevents an operator path from selecting an existing DB.
    run_dir = Path(run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    isolated = Path(tempfile.mkdtemp(prefix='ru12-six-', dir=run_dir))
    repo = OpportunityRepository(Database(DatabaseSettings('ru12-ephemeral', isolated/'notices.sqlite')))
    try:
        repo.initialize()
    except Exception as error:
        for report_key, entry in result['sources'].items():
            entry['reason'] = 'Ephemeral database initialization blocked: ' + type(error).__name__
            print(TARGETS[report_key][1] + ': BLOCKED — ' + entry['reason'], flush=True)
        return result
    for report_key, (key, label) in TARGETS.items():
        entry = result['sources'][report_key]
        if key not in adapters:
            entry['reason'] = ('Offline XML parser only; no verified public live acquisition adapter.' if key == 'tektorg'
                               else 'No verified public live acquisition adapter; source remains OFF.')
        else:
            module, adapter = adapters[key]
            original = module.source_client
            parser_name = {'eis': 'parse_eis_feed', 'eis_223': 'parse_eis_223_feed',
                           'b2b_center': 'parse_b2b_center_listing'}[key]
            original_parser = getattr(module, parser_name)
            active_stage = 'fetch'
            def observed_parser(*args, **kwargs):
                nonlocal active_stage
                active_stage = 'parse'
                try:
                    notices = original_parser(*args, **kwargs)
                except Exception:
                    entry['stages']['parse'] = 'FAILED'
                    raise
                entry['stages']['parse'] = 'VERIFIED'
                active_stage = 'ingestion'
                return notices
            @asynccontextmanager
            async def observed_client(**kwargs):
                async with original(**kwargs) as client:
                    def observe(response):
                        nonlocal active_stage
                        entry.update(proof_origin=proof_origin, http_status=response.status_code,
                                     response_sha256=hashlib.sha256(response.content).hexdigest())
                        entry['stages']['fetch'] = 'VERIFIED' if response.status_code == 200 else 'FAILED'
                        if key in {'eis', 'eis_223'}:
                            active_stage = 'law'
                            try:
                                eis_rss.verify_eis_feed_law(response.content, '44-FZ' if key == 'eis' else '223-FZ')
                            except eis_rss.SourceError:
                                entry['stages']['law'] = 'FAILED'
                                entry['reason'] = 'EIS whole-feed law gate rejected mixed, unknown, conflicting or wrong-law notices.'
                                raise
                            entry['stages']['law'] = 'VERIFIED'
                        else:
                            entry['stages']['law'] = 'NOT_APPLICABLE'
                        active_stage = 'parse'
                    class Observed:
                        def __getattr__(self, name):
                            return getattr(client, name)

                        async def get(self, *args, **options):
                            # Observe only AFTER the unchanged transport enforces body bounds.
                            response = await client.get(*args, **options)
                            observe(response)
                            return response

                        @asynccontextmanager
                        async def stream(self, *args, **options):
                            async with client.stream(*args, **options) as response:
                                # BoundedClient has already consumed with wire/decoded caps.
                                await response.aread()
                                observe(response)
                                yield response
                    yield Observed()
            try:
                payload = dict(schema=1, source_id=key, sync_window=sync_window(), connector_version=connector_version(key))
                context = SimpleNamespace(job=SimpleNamespace(scope=SYSTEM_SCOPE), should_stop=False)
                with patch.object(module, 'source_client', observed_client), patch.object(module, parser_name, observed_parser):
                    counts = ConnectorSyncHandler(catalog, repo, max_records=10)(context, payload)
                entry.update(records=counts['fetched_count'], db=counts['inserted_count'])
                entry['stages']['ingestion'] = 'VERIFIED' if entry['db'] else 'UNVERIFIED'
                active_stage = 'freshness'
                notices = repo.read(key, 10)
                verified = 0
                for notice in notices:
                    if not fresh(notice):
                        continue
                    entry['stages']['freshness'] = 'VERIFIED'
                    active_stage = 'detail'
                    asyncio.run(verify_detail(notice, HOSTS[key]))
                    entry['stages']['detail'] = 'VERIFIED'
                    active_stage = 'keyword-search'
                    query = asyncio.run(snapshot_catalog(catalog, repo).fetch(
                        source_keys=(key,), search_terms=(notice.external_id,), limit_per_source=100))
                    if any(n.identity == notice.identity and n.url == notice.url for n in query.notices):
                        verified += 1
                        entry['stages']['keyword-search'] = 'VERIFIED'
                        entry.update(sample_notice_id=notice.external_id, sample_notice_url=notice.url)
                entry['query'] = verified
                if not verified or entry['db'] < 1 or entry['http_status'] != 200:
                    raise ValueError('Fresh notice, detail identity, insertion or keyword retrieval unproven')
                if proof_origin != 'host_live':
                    raise ValueError('Offline verification cannot establish live proof')
                entry.update(state='LIVE_E2E_VERIFIED', reason='Live adapter acquisition, fresh identity-confirmed detail, app ingestion and snapshot keyword retrieval verified.')
            except Exception as error:
                entry['exceptions'] = exception_frames(error)
                entry['failed_stage'] = active_stage
                if entry['stages'][active_stage] == 'UNVERIFIED':
                    entry['stages'][active_stage] = 'FAILED'
                # Never emit URLs, proxy credentials or arbitrary response text from exceptions.
                if entry['reason'] == 'Not acquired':
                    entry['reason'] = 'Acquisition/law/detail/ingestion/query blocked: ' + type(error).__name__
                if isinstance(error, ValueError):
                    entry['reason'] += ' (verification gate failed)'
        print(label + ': ' + entry['state'] + ' — ' + entry['reason'], flush=True)
    return result


if __name__ == '__main__':
    output = os.environ.get('VALYQON_RU12_REPORT')
    directory = os.environ.get('VALYQON_RU12_RUN_DIR')
    # VALYQON_RU12_MANIFEST is deliberately not consumed as notice input.
    if not output or not directory:
        report = {'sources': {key: dict(blank(), reason='Required REPORT/RUN_DIR environment missing') for key in TARGETS},
                  'ai_query_verified': False, 'ai_query_evidence': 'No authenticated AI session.'}
        for key, (_, label) in TARGETS.items():
            print(label + ': BLOCKED — ' + report['sources'][key]['reason'])
    else:
        report = run(directory)
        report['tls_comparison'] = asyncio.run(compare_eis_trust())
        Path(output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
