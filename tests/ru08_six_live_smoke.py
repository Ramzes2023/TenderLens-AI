"""Optional HOST-ONLY smoke; exactly three supported public GETs, no runtime env loading."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def initial_report():
    keys = ('eis_44fz', 'eis_223fz', 'b2b_center', 'tektorg', 'roseltorg', 'fabrikant')
    return {'sources': {key: {'state': 'NOT_AVAILABLE', 'real_records': 0,
        'database_upserts': 0, 'query_matches': 0, 'reason': 'Initialization not completed.'}
        for key in keys}, 'ai_query_verified': False,
        'note': 'Existing snapshot keyword query only; AI/LLM API and authenticated UI are not exercised. No six-source readiness claim.'}


async def run(workdir):
    result = initial_report()
    keys = tuple(result['sources'])
    try:
        from app.database.backend import Database
        from app.database.config import DatabaseSettings
        from app.sources.opportunities import OpportunityRepository
        from app.sources.ru08_integration import (
            local_catalog, SOURCE_KEYS, BLOCKERS, save_and_query, duplicate_diagnostics)
    except Exception as error:
        for entry in result['sources'].values():
            entry['reason'] = 'Dependency/import unavailable: ' + type(error).__name__
        return result
    for key, (state, reason) in BLOCKERS.items():
        result['sources'][key].update(state=state, reason=reason)
    # Fresh randomly named child: never open any existing database or configured URL.
    with tempfile.TemporaryDirectory(prefix='ru08-', dir=workdir) as isolated:
        database = Database(DatabaseSettings('ru08-isolated-sqlite', Path(isolated) / 'notices.sqlite'))
        repository = OpportunityRepository(database)
        try:
            repository.initialize()
        except Exception as error:
            for key in keys[:3]:
                result['sources'][key]['reason'] = 'Isolated database unavailable: ' + type(error).__name__
            return result
        catalog = local_catalog(enable_eis223=True, enable_b2b=True)
        retrieved = []
        for output_key in keys[:3]:
            key = SOURCE_KEYS[output_key]
            entry = result['sources'][output_key]
            report = await catalog.fetch(source_keys=(key,), limit_per_source=20)
            notices = list(report.notices)
            if report.failures or not notices:
                entry.update(state='BLOCKED', reason=(report.failures[0].error_type
                    if report.failures else 'No usable records; empty response is not proof of no data.'))
            else:
                entry.update(state='LIVE_FETCH_ONLY', real_records=len(notices), reason='Normalized public notices fetched.')
                retrieved.extend(notices)
                try:
                    upserts, matches = await save_and_query(catalog, repository, key, notices, progress=entry)
                    entry.update(database_upserts=upserts, query_matches=matches)
                    if upserts == matches == len(notices):
                        entry.update(state='LIVE_E2E_VERIFIED', reason='Same fetched identities and URLs saved and found via snapshot_catalog keyword query; law filter is not independent legal verification.')
                except Exception as error:
                    entry['reason'] = 'Fetch succeeded; storage/query verification failed: ' + type(error).__name__
            await asyncio.sleep(1)
        result['note'] += ' Duplicate diagnostics: ' + json.dumps(duplicate_diagnostics(retrieved), ensure_ascii=False)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workdir', type=Path, required=True)
    args = parser.parse_args()
    temp_root = Path(tempfile.gettempdir()).resolve()
    resolved = args.workdir.resolve()
    if resolved == temp_root or temp_root not in resolved.parents:
        parser.error('--workdir must be a child directory of the host temporary directory')
    args.workdir.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        parser.error('--output must be a new file')
    try:
        result = asyncio.run(run(args.workdir.resolve()))
    except Exception as error:
        result = initial_report()
        for entry in result['sources'].values():
            entry['reason'] = 'Smoke could not complete; no proof reported: ' + type(error).__name__
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
