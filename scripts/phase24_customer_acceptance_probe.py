"""One-shot TED acceptance benchmark. No database, configuration, credentials or LLM."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.monitoring.service import prefilter_notice
from app.scoring.models import CompanyProfile
from app.scoring.preview import score_metadata_preview
from app.services.tender_analysis import analysis_from_notice
from app.sources.catalog import SourceCatalog
from app.sources.http import FetchPolicy, bounded_fetch
from app.sources.multi import MultiSourceFetcher
from app.sources.registry import SourceRegistration, SourceRegistry
from app.sources.ted_api import TedApiSource, parse_ted_search_response


def synthetic_profile():
    return CompanyProfile(profile_version='phase24-synthetic-v5',
                          company_name='SYNTHETIC cable supplier',
                          product_keywords=['cables'], search_keywords=['cables'],
                          accepted_currencies=['EUR'], max_contract_value=1000000,
                          hard_stop_on_currency=True)


def fixture_payload():
    """Injected synthetic records in real TED field schema; NOT recorded live evidence."""
    return {'notices': [
        {'publication-number': '100001-2026',
         'notice-title': {'eng': 'SYNTHETIC Supply of industrial cables'},
         'total-value': 10000, 'total-value-cur': 'EUR',
         'deadline-receipt-tender-date-lot': '2099-01-01'},
        {'publication-number': '100002-2026',
         'notice-title': {'eng': 'SYNTHETIC Supply of industrial cables'}},
        {'publication-number': '100003-2026',
         'notice-title': {'eng': 'SYNTHETIC Office furniture'}},
    ]}


def ted_catalog(timeout=12):
    registry = SourceRegistry([
        SourceRegistration('ted', 'TED', TedApiSource(timeout=timeout), jurisdictions=('EU',)),
    ])
    return SourceCatalog(registry, MultiSourceFetcher(registry, concurrency=1))


async def probe(*, live=False):
    profile = synthetic_profile()
    result = dict(attempted_source='ted', timestamp=datetime.now(timezone.utc).isoformat(),
                  live=live, evidence='public_live' if live else 'synthetic_TED_schema_fixture',
                  real_results_count=0, fixture_results_count=0, outbound_calls=0,
                  examples=[], synthetic_profile_evaluations=0, matching_count=0,
                  excluded_count=0, unknown_data_count=0, analysis_stage='metadata_preview',
                  full_ai_analyzed=False, llm_used=False, status='UNAVAILABLE', reason=None)
    policy = FetchPolicy(frozenset({'api.ted.europa.eu'}), max_requests=1,
                         max_bytes=2 * 1024 * 1024)
    if live:
        try:
            with bounded_fetch(policy):
                report = await asyncio.wait_for(ted_catalog().fetch(limit_per_source=5,
                                                  search_terms=profile.monitoring_keywords), timeout=15)
            if report.failures:
                result['reason'] = 'TED request unavailable or response rejected; no retry performed.'
                return result, 1
            notices = list(report.notices)
        except Exception:
            result['reason'] = 'TED request unavailable or response rejected; no retry performed.'
            return result, 1
        finally:
            result['outbound_calls'] = policy.requests
        result['real_results_count'] = len(notices)
    else:
        notices = parse_ted_search_response(fixture_payload())
        result['fixture_results_count'] = len(notices)
    for notice in notices:
        score = score_metadata_preview(analysis_from_notice(notice), profile)
        matched = prefilter_notice(notice, profile) is not None
        unknowns = [row.explanation for row in score.criteria if row.status == 'not_scored']
        result['synthetic_profile_evaluations'] += 1
        result['matching_count' if matched else 'excluded_count'] += 1
        result['unknown_data_count'] += bool(unknowns or notice.deadline is None)
        if len(result['examples']) < 3:
            result['examples'].append(dict(public_notice_id=notice.external_id,
                official_url=notice.url, title=''.join(c for c in notice.title if ord(c) >= 32)[:160],
                preliminary_score=score.fit_score, prefilter_matched=matched,
                unknowns=unknowns, stop_factors=score.stop_factors))
    result['status'] = ('LIVE_VERIFIED' if live else 'OFFLINE_FIXTURE_EVALUATED') if notices else 'UNAVAILABLE'
    result['reason'] = None if notices else 'TED returned no usable notices.'
    return result, 0 if notices else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--offline', action='store_true')
    modes.add_argument('--live', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report, code = asyncio.run(probe(live=args.live))
    output = args.output
    if output is None:
        with tempfile.NamedTemporaryFile(prefix='phase24-acceptance-', suffix='.json', delete=False) as handle:
            output = Path(handle.name)
    output.write_text(json.dumps(report, ensure_ascii=True, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(output=str(output), status=report['status'], outbound_calls=report['outbound_calls'])))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
