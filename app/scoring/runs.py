"""Authorized bounded snapshot selection, durable scoring and private presentation.

No procurement fetches, AI generation or runtime configuration loading occurs here.
"""
import hashlib
import json
import re
import sqlite3
from contextlib import closing
from dataclasses import asdict

from pydantic import ValidationError

from app.database.backend import StorageError, StorageIntegrityError
from app.jobs.models import JobScope, JobValueError, LeaseLostError, decode_job, encode_json
from app.jobs.worker import PermanentJobError, RetryableJobError
from app.monitoring.service import prefilter_notice
from app.services.tender_analysis import analysis_from_notice
from app.sources.models import TenderNotice
from app.sources.opportunities import validate_notice
from .models import CompanyProfile
from .preview import score_metadata_preview

JOB_TYPE = 'scoring.run.v1'
ENGINE_VERSION = 'scoring-engine-v1'
MAX_SOURCES = 5
MAX_PER_SOURCE = 100
SCAN_PER_SOURCE = 1000
MAX_RESULTS = MAX_SOURCES * MAX_PER_SOURCE
SOURCE_IDS = frozenset({'eis', 'ted', 'sam_gov', 'uk_fts', 'canada_buys', 'austender',
                        'nz_gets', 'india_cppp', 'kz_goszakup', 'za_etenders'})


class ScoringAccessError(ValueError):
    pass


class ScoringInputError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def profile_digest(profile):
    return digest(profile.model_dump(mode='json'))


def validate_configuration(sources, limit):
    if (type(sources) not in (list, tuple) or not 1 <= len(sources) <= MAX_SOURCES
            or any(type(source) is not str or source not in SOURCE_IDS for source in sources)
            or len(set(sources)) != len(sources)
            or type(limit) is not int or not 1 <= limit <= MAX_PER_SOURCE):
        raise ScoringInputError('Invalid scoring selection.')
    return {'sources': sorted(sources), 'limit_per_source': limit, 'scan_per_source': SCAN_PER_SOURCE}


def validate_payload(payload):
    if (type(payload) is not dict or set(payload) != {'snapshot_id', 'profile_digest', 'engine_version'}
            or payload['engine_version'] != ENGINE_VERSION
            or any(type(payload[key]) is not str or not re.fullmatch('[a-f0-9]{64}', payload[key])
                   for key in ('snapshot_id', 'profile_digest'))):
        raise ScoringInputError('Invalid scoring computation identity.')


class ScoringRunService:
    def __init__(self, jobs):
        self.jobs = jobs
        self.database = jobs.repository.database

    def _profile(self, conn, scope):
        if not isinstance(scope, JobScope) or any(value is None for value in scope.values):
            raise ScoringAccessError('Scoring access denied.')
        row = conn.execute('''SELECT c.profile_json FROM company_workspaces c
            JOIN organization_members m ON m.organization_id=c.organization_id
            JOIN auth_accounts a ON a.id=m.account_id
            WHERE c.id=? AND c.organization_id=? AND m.account_id=? AND a.is_active=1''',
            (scope.company_id, scope.organization_id, scope.account_id)).fetchone()
        if row is None:
            raise ScoringAccessError('Scoring access denied.')
        try:
            return CompanyProfile.model_validate_json(row['profile_json'])
        except ValidationError:
            raise ScoringInputError('Invalid company profile.') from None

    def _snapshot(self, conn, scope, payload):
        validate_payload(payload)
        row = conn.execute('''SELECT * FROM scoring_snapshots WHERE identity=?
            AND account_id=? AND organization_id=? AND company_id=?''',
            (payload['snapshot_id'], *scope.values)).fetchone()
        if (row is None or row['profile_digest'] != payload['profile_digest']
                or row['engine_version'] != ENGINE_VERSION):
            raise ScoringInputError('Invalid scoring snapshot.')
        if profile_digest(self._profile(conn, scope)) != row['profile_digest']:
            raise ScoringInputError('Company profile changed; request a new scoring run.')
        return row

    def enqueue(self, *, scope, sources=('ted',), limit_per_source=20):
        config = validate_configuration(sources, limit_per_source)
        # Short bounded transaction freezes the selected public revisions together.
        # Existing adapter's transaction lock serializes snapshot reads with ingestion.
        with closing(self.database.connect()) as conn:
            with conn:
                conn.execute('BEGIN IMMEDIATE')
                profile = self._profile(conn, scope)
                pd = profile_digest(profile)
                selected, counts, examined = [], {}, []
                terms = tuple(term.casefold() for term in profile.monitoring_keywords[:20] if term.strip())
                for source in config['sources']:
                    rows = conn.execute('''SELECT notice_json,connector_version FROM source_opportunities
                        WHERE source_id=? ORDER BY last_seen DESC,external_id LIMIT 1000''', (source,)).fetchall()
                    counts[source] = len(rows)
                    taken = 0
                    for row in rows:
                        notice = validate_notice(TenderNotice(**json.loads(row['notice_json'])), source)
                        revision = digest([asdict(notice), row['connector_version']])
                        examined.append([source, notice.external_id, revision])
                        # Same source snapshot keyword semantics as OpportunityRepository.read.
                        text = ' '.join(str(value or '') for value in asdict(notice).values()).casefold()
                        if taken >= limit_per_source or (terms and not any(term in text for term in terms)):
                            continue
                        taken += 1
                        selected.append(revision)
                        conn.execute('''INSERT INTO scoring_public_revisions
                            (revision,source_id,external_id,notice_json,connector_version) VALUES(?,?,?,?,?)
                            ON CONFLICT(revision) DO NOTHING''',
                            (revision, source, notice.external_id, canonical(asdict(notice)), row['connector_version']))
                identity = digest([scope.values, pd, ENGINE_VERSION, config, examined, selected])
                conn.execute('''INSERT INTO scoring_snapshots
                    (identity,account_id,organization_id,company_id,profile_digest,engine_version,
                     configuration_json,source_counts_json,candidate_count) VALUES(?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(identity) DO NOTHING''',
                    (identity, *scope.values, pd, ENGINE_VERSION, canonical(config), canonical(counts), len(selected)))
                for ordinal, revision in enumerate(selected):
                    conn.execute('''INSERT INTO scoring_candidates(snapshot_id,ordinal,revision) VALUES(?,?,?)
                        ON CONFLICT(snapshot_id,ordinal) DO NOTHING''', (identity, ordinal, revision))
        payload = {'snapshot_id': identity, 'profile_digest': pd, 'engine_version': ENGINE_VERSION}
        return self.jobs.enqueue(JOB_TYPE, payload, scope=scope, idempotency_key=identity)

    def view(self, job_id, *, scope, limit=50, offset=0):
        if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or not 0 <= offset <= MAX_RESULTS:
            raise ScoringInputError('Invalid scoring page.')
        with closing(self.database.connect()) as conn, conn:
            conn.execute('BEGIN IMMEDIATE')
            # Membership/profile checked in the same transaction as the result page.
            self._profile(conn, scope)
            clause, params = self.jobs.repository._scope_filter(scope)
            job = decode_job(conn.execute('SELECT * FROM durable_jobs WHERE id=? AND ' + clause,
                                          (job_id, *params)).fetchone())
            if job is None or job.job_type != JOB_TYPE:
                raise ScoringAccessError('Scoring run not found.')
            snapshot = self._snapshot(conn, scope, job.payload)
            complete = job.state == 'succeeded'
            result_count = 0
            items = []
            if complete:
                result_count = conn.execute('SELECT COUNT(*) FROM scoring_results WHERE job_id=? AND snapshot_id=?',
                                            (job.id, snapshot['identity'])).fetchone()[0]
                if result_count > MAX_RESULTS or not isinstance(job.result, dict) or result_count != job.result.get('result_count'):
                    raise ScoringInputError('Incomplete scoring materialization.')
                rows = conn.execute('''SELECT source_id,external_id,scoring_json FROM scoring_results
                    WHERE job_id=? AND snapshot_id=? ORDER BY score DESC,completeness DESC,ordinal
                    LIMIT ? OFFSET ?''', (job.id, snapshot['identity'], limit, offset)).fetchall()
                items = [{'source_id': row['source_id'], 'external_id': row['external_id'],
                          'scoring': json.loads(row['scoring_json'])} for row in rows]
            counts = json.loads(snapshot['source_counts_json'])
            return {'job_id': job.id, 'status': job.state, 'complete': complete,
                    'engine_version': ENGINE_VERSION, 'profile_digest': snapshot['profile_digest'],
                    'snapshot_id': snapshot['identity'], 'candidate_count': snapshot['candidate_count'],
                    'source_state': {key: 'available' if count else 'empty_or_not_synchronized'
                                     for key, count in counts.items()},
                    'result_count': result_count, 'limit': limit, 'offset': offset, 'items': items}


class ScoringRunHandler:
    def __init__(self, service):
        self.service = service

    def __call__(self, context, payload):
        try:
            job = context.job
            if job.job_type != JOB_TYPE:
                raise ScoringInputError('Invalid scoring type.')
            validate_payload(payload)
            with closing(self.service.database.connect()) as conn:
                snapshot = self.service._snapshot(conn, job.scope, payload)
                config = json.loads(snapshot['configuration_json'])
                expected = validate_configuration(config['sources'], config['limit_per_source'])
                if config != expected:
                    raise ScoringInputError('Invalid scoring configuration.')
                profile = self.service._profile(conn, job.scope)
                if profile_digest(profile) != payload['profile_digest']:
                    raise ScoringInputError('Company profile changed.')
                rows = conn.execute('''SELECT c.ordinal,r.* FROM scoring_candidates c
                    JOIN scoring_public_revisions r ON r.revision=c.revision
                    WHERE c.snapshot_id=? ORDER BY c.ordinal LIMIT 501''', (snapshot['identity'],)).fetchall()
            if len(rows) != snapshot['candidate_count'] or len(rows) > MAX_RESULTS:
                raise ScoringInputError('Invalid scoring candidates.')
            scores = []
            for row in rows:
                if context.should_stop:
                    raise RetryableJobError()
                notice = validate_notice(TenderNotice(**json.loads(row['notice_json'])), row['source_id'])
                if digest([asdict(notice), row['connector_version']]) != row['revision']:
                    raise ScoringInputError('Invalid public revision.')
                if prefilter_notice(notice, profile) is None:
                    continue
                score = score_metadata_preview(analysis_from_notice(notice), profile)
                # Existing explanations are private customer data; no raw profile/name,
                # opportunity body, metadata_analysis or generated report is returned.
                safe = score.model_dump(mode='json', exclude={'profile_name', 'profile_version'})
                encoded = encode_json(safe, 32768)
                scores.append((row, score, encoded))

            def write(conn, now):
                self.service._snapshot(conn, job.scope, payload)
                for row, score, encoded in scores:
                    conn.execute('''INSERT INTO scoring_results
                        (job_id,snapshot_id,ordinal,source_id,external_id,score,completeness,scoring_json,calculated_at)
                        VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(job_id,source_id,external_id) DO UPDATE SET
                        score=excluded.score,completeness=excluded.completeness,
                        scoring_json=excluded.scoring_json,calculated_at=excluded.calculated_at''',
                        (job.id, snapshot['identity'], row['ordinal'], row['source_id'], row['external_id'],
                         score.fit_score, score.completeness_percent, encoded, now))
            if not context.fenced_write(write):
                context.lease_lost.set()
                raise RetryableJobError()
            return {'snapshot_id': snapshot['identity'], 'engine_version': ENGINE_VERSION,
                    'profile_digest': payload['profile_digest'], 'result_count': len(scores)}
        except LeaseLostError:
            context.lease_lost.set()
            raise RetryableJobError() from None
        except (sqlite3.IntegrityError, sqlite3.ProgrammingError, StorageIntegrityError):
            raise PermanentJobError() from None
        except (sqlite3.Error, StorageError):
            raise RetryableJobError() from None
        except (ScoringAccessError, ScoringInputError, JobValueError, ValidationError, ValueError, TypeError, KeyError):
            raise PermanentJobError() from None
