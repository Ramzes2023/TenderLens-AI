"""HOST ONLY: two bounded existing EIS adapter GETs; no settings/.env loading.

Captured evidence is offline diagnostics only and never supplies live records.
"""
import argparse
import asyncio
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import parse_qs, urlsplit
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
MAX_BYTES = 5 * 1024 * 1024


def law_evidence(payload):
    """Require agreement of result-level law label AND official detail route.

    This proves feed-record classification, not a separately fetched detail page.
    Query intent, source key, title and number length are never law evidence.
    """
    from app.sources.eis_rss import _child_text, _entry_link, _local_name
    if len(payload) > MAX_BYTES:
        raise ValueError('Evidence exceeds limit')
    probe = payload.replace(b'\x00', b'').lower()
    if b'<!doctype' in probe or b'<!entity' in probe:
        raise ValueError('DTD/entity evidence rejected')
    root = ET.fromstring(payload)
    if _local_name(root.tag) not in {'rss', 'feed', 'rdf'}:
        raise ValueError('Not a feed')
    evidence = {}
    for node in root.iter():
        if _local_name(node.tag) not in {'item', 'entry'}:
            continue
        link = _entry_link(node)
        parts = urlsplit(link)
        description = _child_text(node, {'description', 'summary', 'content'})
        # Exclude search-form preamble even if it contains a result-like label.
        result = description.partition('Найденный результат:')[2] if 'Найденный результат:' in description else description
        labels = re.findall(r'Размещение\s+выполняется\s+по\s*:\s*(44|223)\s*[-–]?\s*ФЗ\b', result, re.I)
        route = ('223' if parts.path.startswith('/223/purchase/public/purchase/')
                 else '44' if parts.path.startswith('/epz/order/notice/') else None)
        numbers = parse_qs(parts.query).get('regNumber', [])
        law = labels[0] if len(set(labels)) == 1 and labels else None
        valid = (parts.scheme == 'https' and parts.netloc == 'zakupki.gov.ru'
                 and not parts.fragment and len(numbers) == 1
                 and re.fullmatch(r'\d{11,20}', numbers[0]) and route == law)
        # Contradictory duplicate links fail closed.
        value = law + '-FZ' if valid else None
        evidence[link] = value if link not in evidence or evidence[link] == value else None
    return evidence


def external_evidence(path):
    """Bounded external TEMP read; no fixture copying or live state promotion."""
    path = path.resolve()
    root = Path(tempfile.gettempdir()).resolve()
    if root not in path.parents or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError('Evidence must be a bounded existing TEMP file')
    payload = path.read_bytes()
    laws = law_evidence(payload)
    return {'sha256': hashlib.sha256(payload).hexdigest(), 'bytes': len(payload),
            'record_links': len(laws), 'law_44_links': list(laws.values()).count('44-FZ'),
            'law_223_links': list(laws.values()).count('223-FZ'),
            'live_proof': False, 'note': 'Caller-supplied offline host evidence; origin not authenticated by this script.'}


def initial_report():
    return {'sources': {key: {'state': 'BLOCKED', 'real_records': 0,
        'database_upserts': 0, 'query_matches': 0, 'reason': 'Not completed',
        'endpoint_host': 'zakupki.gov.ru', 'law_verified': False}
        for key in ('eis_44fz', 'eis_223fz')}, 'ai_query_verified': False,
        'diagnostics': {}, 'note': 'Existing snapshot keyword query; no authenticated user AI path. Law proof uses fetched result label plus official detail route, without detail GET.'}


@contextmanager
def observe_adapter(module, endpoint, diagnostics):
    """Observe existing client route/HTTP and parser input; preserve all policies."""
    import httpx
    from app.sources.http import _RejectedProxyTransport
    original_client = module.source_client
    parser_name = 'parse_eis_223_feed' if module.__name__.endswith('eis_223_rss') else 'parse_eis_feed'
    original_parser = getattr(module, parser_name)
    payloads = []

    async def response_hook(response):
        diagnostics['http_status'] = response.status_code

    def client(**kwargs):
        result = original_client(**kwargs, event_hooks={'response': [response_hook]})
        # Inspect route type only; never stringify a proxy object or environment.
        diagnostics['proxy_route_rejected'] = isinstance(
            result._transport_for_url(httpx.URL(endpoint)), _RejectedProxyTransport)
        return result

    def parser(payload, **kwargs):
        records = original_parser(payload, **kwargs)
        payloads.append(payload)
        return records

    module.source_client = client
    setattr(module, parser_name, parser)
    try:
        yield payloads
    finally:
        module.source_client = original_client
        setattr(module, parser_name, original_parser)


async def run(workdir, evidence=None):
    result = initial_report()
    if evidence is not None:
        try:
            result['external_evidence'] = external_evidence(evidence)
        except Exception as error:
            result['external_evidence'] = {'error_type': type(error).__name__, 'live_proof': False}
    try:
        from app.database.backend import Database
        from app.database.config import DatabaseSettings
        from app.sources import eis_rss, eis_223_rss
        from app.sources.catalog import SourceCatalog
        from app.sources.multi import MultiSourceFetcher
        from app.sources.opportunities import OpportunityRepository
        from app.sources.registry import SourceRegistration, SourceRegistry, SourceTransport
        from app.sources.ru08_integration import LocalBoundedSource, save_and_query
    except Exception as error:
        for entry in result['sources'].values():
            entry['reason'] = 'Import blocked: ' + type(error).__name__
        return result
    adapters = (('eis_44fz', eis_rss, eis_rss.EisRssSource((eis_rss.build_eis_rss_url('поставка'),), timeout=15), '44-FZ'),
                ('eis_223fz', eis_223_rss, eis_223_rss.Eis223RssSource((eis_223_rss.build_eis_223_rss_url('поставка'),), timeout=15), '223-FZ'))
    # In-memory registrations only: EIS223 normal default remains OFF.
    registry = SourceRegistry(SourceRegistration(source.name, source.name,
        LocalBoundedSource(source, source.name), transport=SourceTransport.RSS,
        jurisdictions=('RU',), languages=('ru',)) for _, _, source, _ in adapters)
    catalog = SourceCatalog(registry, MultiSourceFetcher(registry, concurrency=1))
    with tempfile.TemporaryDirectory(prefix='ru09-', dir=workdir) as isolated:
        repository = OpportunityRepository(Database(DatabaseSettings('ru09-isolated-sqlite', Path(isolated) / 'notices.sqlite')))
        for output_key, module, source, wanted in adapters:
            entry = result['sources'][output_key]
            diagnostics = {'http_status': None, 'proxy_route_rejected': None,
                           'exception_type': None, 'requests_max': 1}
            result['diagnostics'][output_key] = diagnostics
            with observe_adapter(module, source.urls[0], diagnostics) as payloads:
                report = await catalog.fetch(source_keys=(source.name,), limit_per_source=20)
            if report.failures or not report.notices:
                diagnostics['exception_type'] = report.failures[0].error_type if report.failures else None
                entry['reason'] = ('Fetch blocked: ' + (diagnostics['exception_type'] or 'empty feed')
                    + '; HTTP=' + str(diagnostics['http_status'])
                    + '; rejected_proxy_route=' + str(diagnostics['proxy_route_rejected']))
                continue
            entry.update(state='LIVE_FETCH_ONLY', real_records=len(report.notices), reason='Live adapter fetch; correct-law verification pending')
            try:
                laws = {}
                for payload in payloads:
                    laws.update(law_evidence(payload))
                verified = [notice for notice in report.notices if laws.get(notice.url) == wanted]
                diagnostics['correct_law_records'] = len(verified)
                diagnostics['unverified_or_other_law_records'] = len(report.notices) - len(verified)
                if not verified:
                    entry['reason'] = 'Fetched records do not prove requested law; filter intent is insufficient'
                    continue
                entry['law_verified'] = True
                repository.initialize()
                upserts, matches = await save_and_query(catalog, repository, source.name, verified, progress=entry)
                if upserts == matches == len(verified):
                    entry.update(state='LIVE_E2E_VERIFIED', reason='Correct-law live notices saved and same identities/URLs found via existing snapshot keyword query')
            except Exception as error:
                entry['reason'] = 'Live fetch only; law/storage/query blocked: ' + type(error).__name__
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workdir', type=Path, required=True)
    parser.add_argument('--evidence', type=Path)
    args = parser.parse_args()
    root = Path(tempfile.gettempdir()).resolve()
    if root not in args.workdir.resolve().parents or root not in args.output.resolve().parents:
        parser.error('Output and workdir must be children of HOST TEMP')
    if args.output.exists():
        parser.error('Output must be a new file')
    args.workdir.mkdir(parents=True, exist_ok=True)
    try:
        result = asyncio.run(run(args.workdir.resolve(), args.evidence))
    except Exception as error:
        result = initial_report()
        for entry in result['sources'].values():
            entry['reason'] = 'Smoke blocked: ' + type(error).__name__
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
