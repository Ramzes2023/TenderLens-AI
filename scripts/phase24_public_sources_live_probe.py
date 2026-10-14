"""Explicit, keyless, database-free probe of the existing public adapters."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.sources.catalog import SourceCatalog
from app.sources.http import FetchPolicy, bounded_fetch
from app.sources.multi import MultiSourceFetcher
from app.sources.registry import SourceRegistration, SourceRegistry
from app.sources.ted_api import TedApiSource
from app.sources.uk_fts_api import UkFindTenderApiSource
from app.monitoring.service import prefilter_notice
from app.services.tender_analysis import analysis_from_notice
from app.scoring.engine import score_tender
from app.scoring.models import CompanyProfile


def synthetic_profile():
    """Public benchmark only: never resolve a customer's saved profile."""
    return CompanyProfile(profile_version='synthetic-benchmark-v1',
                          company_name='SYNTHETIC industrial cable supplier',
                          industry='Industrial electrical cables',
                          product_keywords=['cable', 'cables'],
                          search_keywords=['cable', 'cables'],
                          accepted_currencies=['EUR'], max_contract_value=1000000)


def benchmark_notices(notices):
    profile = synthetic_profile()
    examples = []
    for notice in notices:
        match = prefilter_notice(notice, profile)
        score = score_tender(analysis_from_notice(notice), profile)
        examples.append({
            'source': notice.source, 'public_notice_id': notice.tender_number or notice.external_id,
            'official_url': notice.url, 'prefilter_matched': match is not None,
            'fit_status': 'FILTERED_OUT' if match is None else (
                'UNKNOWN' if score.fit_score is None else 'PREFILTER_CANDIDATE'),
            'fit_score': score.fit_score, 'completeness_percent': score.completeness_percent,
            'criteria': [row.model_dump(mode='json') for row in score.criteria],
            'unknown_reason': [row.explanation for row in score.criteria if row.status == 'not_scored'],
            'stop_factors': score.stop_factors,
            'initial_price': notice.initial_price, 'currency': notice.currency,
            'deadline': notice.deadline,
        })
    return {'evaluated_notice_count': len(examples), 'examples': examples[:3],
            'profile_is_synthetic': True, 'profile': profile.model_dump(mode='json'),
            'full_pdf_analysis': False, 'llm_used': False,
            'analysis_stage': 'metadata_only_preliminary',
            'status': 'EVALUATED' if examples else 'NOT_EVALUATED'}


def public_catalog(timeout=12):
    # Use the canonical registry/catalog classes without environment credentials
    # or build_source_catalog(settings), which reads authenticated-source keys.
    registry = SourceRegistry([
        SourceRegistration('ted', 'TED', TedApiSource(timeout=timeout), jurisdictions=('EU',)),
        SourceRegistration('uk_fts', 'UK Find a Tender', UkFindTenderApiSource(timeout=timeout), jurisdictions=('GB',)),
    ])
    return SourceCatalog(registry, MultiSourceFetcher(registry, concurrency=1))


def redacted_title(value):
    value = re.sub(r'https?://\S+|[\w.+-]+@[\w.-]+', '[redacted]', value)
    value = re.sub(r'\+?\d[\d ()-]{8,}\d', '[redacted]', value)
    return ''.join(c for c in value if ord(c) >= 32)[:160]


async def probe(*, live=False, limit=5, timeout=12):
    result = {'timestamp': datetime.now(timezone.utc).isoformat(), 'live': live,
              'attempted_source_keys': [], 'outbound_calls': 0, 'sources': {},
              'sam_gov': {'status': 'AUTH_REQUIRED', 'verification': 'NOT_LIVE_VERIFIED'},
              'scoring': 'Synthetic benchmark only; metadata-only preliminary fit, NO LLM.',
              'live_scoring': benchmark_notices([])}
    if not 1 <= limit <= 5 or not 0 < timeout <= 12:
        raise ValueError('Probe requires limit 1..5 and timeout >0..12 seconds.')
    if not live:
        result['message'] = 'Network disabled. Supply --live to attempt public retrieval.'
        return result, 1
    policy = FetchPolicy(frozenset({'api.ted.europa.eu', 'www.find-tender.service.gov.uk'}),
                         max_requests=8, max_bytes=2 * 1024 * 1024)
    with bounded_fetch(policy):
        report = await public_catalog(timeout).fetch(limit_per_source=limit)
    result['attempted_source_keys'] = list(report.attempted_sources)
    result['outbound_calls'] = policy.requests
    eligible = []
    for status in report.statuses:
        notices = [n for n in report.notices if n.source == status.source][:limit]
        failed = status.error_type is not None
        if not failed:
            eligible.extend(notices)
        result['sources'][status.source] = {
            'status': ('UNAVAILABLE' if status.error_type == 'ConnectorTransportError' else 'FAILED')
                      if failed else ('LIVE_VERIFIED' if notices else 'UNAVAILABLE'),
            'adapter_state': status.state.value, 'real_results_count': len(notices),
            'live_scoring': benchmark_notices([] if failed else notices),
            'transport': {'error_type': status.error_type,
                          'summary': status.message if failed else 'HTTPS response parsed successfully',
                          # Policy verifies 2xx but catalog does not expose the
                          # exact HTTP code. Do not guess 200 or a failed code.
                          'http_status': None},
            'examples': [{'title': redacted_title(n.title), 'public_notice_id': n.tender_number or n.external_id,
                          'source': n.source, 'jurisdiction': 'EU' if n.source == 'ted' else 'GB',
                          'delivery_country': None, 'official_url': n.url,
                          'published_at': n.published_at, 'deadline': n.deadline, 'currency': n.currency}
                         for n in notices[:3]],
        }
        if failed and status.source == 'uk_fts':
            result['sources'][status.source]['failure_cause'] = (
                'Undetermined: provider blocking, policy rejection or endpoint change '
                'not independently established.')
    result['live_scoring'] = benchmark_notices(eligible)
    return result, 0 if report.notices else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--live', action='store_true')
    mode.add_argument('--offline', action='store_true')
    parser.add_argument('--limit', type=int, choices=range(1, 6), default=5)
    parser.add_argument('--timeout', type=float, default=12)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 0 < args.timeout <= 12:
        parser.error('--timeout must be greater than zero and at most 12')
    result, code = asyncio.run(probe(live=args.live, limit=args.limit, timeout=args.timeout))
    args.output.write_text(json.dumps(result, ensure_ascii=True, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(args.output), 'exit_code': code, 'outbound_calls': result['outbound_calls']}))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
