"""Shared public notices only. Tenant analyses and profiles never enter this store."""
import json
import math
import re
from contextlib import closing
from dataclasses import asdict, fields
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qs, urlsplit

from .models import TenderNotice
from .enrichment import validate_enrichment, with_connector


def validate_notice(notice, source_id):
    if not isinstance(notice, TenderNotice) or notice.source != source_id:
        raise ValueError('Invalid normalized notice.')
    if notice.enrichment is not None:
        validate_enrichment(notice.enrichment, notice.source, notice.external_id)
    if type(source_id) is not str or not re.fullmatch('[a-z0-9][a-z0-9_-]{0,63}', source_id):
        raise ValueError('Invalid normalized source identity.')
    limits = {'source': 64, 'external_id': 500, 'title': 1000, 'url': 2000,
              'published_at': 120, 'deadline': 120, 'tender_number': 500,
              'customer': 2000, 'currency': 3, 'region': 2000, 'summary': 4000}
    for name, limit in limits.items():
        value = getattr(notice, name)
        if value is None and name not in {'source', 'external_id', 'title', 'url'}:
            continue
        if (type(value) is not str or not value.strip() or len(value) > limit or '\x00' in value
                or re.search(r'<\s*/?\s*[a-zA-Z][^>]*>', value)):
            raise ValueError('Invalid normalized notice.')
    url = urlsplit(notice.url)
    if (url.scheme not in {'http', 'https'} or not url.hostname or url.username
            or url.password or url.fragment or any(c.isspace() for c in notice.url)):
        raise ValueError('Invalid normalized URL.')
    if any(key.casefold() in {'api_key', 'apikey', 'token', 'access_token', 'password', 'secret'}
           for key in parse_qs(url.query)):
        raise ValueError('Credential-bearing normalized URL.')
    if notice.initial_price is not None and (type(notice.initial_price) not in (int, float)
            or not math.isfinite(notice.initial_price) or not 0 <= notice.initial_price <= 1e18):
        raise ValueError('Invalid normalized amount.')
    if notice.currency is not None and not re.fullmatch('[A-Z]{3}', notice.currency):
        raise ValueError('Invalid normalized currency.')
    for value in (notice.published_at, notice.deadline):
        if value is None:
            continue
        try:
            datetime.fromisoformat(value.replace('Z', '+00:00'))
            continue
        except ValueError:
            pass
        try:
            parsedate_to_datetime(value)
            continue
        except (TypeError, ValueError, OverflowError):
            pass
        # Established EIS human-readable dates retain source-local semantics.
        try:
            datetime.strptime(value, '%d.%m.%Y %H:%M')
        except ValueError:
            datetime.strptime(value, '%d.%m.%Y')
    return notice


class OpportunityRepository:
    def __init__(self, database):
        self.database = database

    def initialize(self):
        self.database.migrate('opportunities')
        # Additive, versioned Russian notice provenance; separate from existing tables.
        self.database.migrate('source_observations')

    @staticmethod
    def _prepare_upsert(notice, connector_version):
        validate_notice(notice, notice.source)
        if (type(connector_version) is not str or not re.fullmatch(
                r'connector-sync-v1:' + re.escape(notice.source) + r':adapter-r[1-9][0-9]{0,3}', connector_version)):
            raise ValueError('Invalid connector provenance.')
        notice = with_connector(notice, connector_version)
        encoded = json.dumps(asdict(notice), ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        now = datetime.now(timezone.utc).isoformat()
        return notice, encoded, now

    @staticmethod
    def _write_prepared(conn, notice, encoded, now, connector_version):
        # Must run within the caller's active transaction. No connection or
        # transaction is opened here, so lease fencing and this write can be atomic.
        inserted = conn.execute('''INSERT INTO source_opportunities
            (source_id,external_id,notice_json,connector_version,first_seen,last_seen)
            VALUES(?,?,?,?,?,?) ON CONFLICT(source_id,external_id) DO NOTHING''',
            (notice.source, notice.external_id, encoded, connector_version, now, now)).rowcount == 1
        if not inserted:
            conn.execute('''UPDATE source_opportunities SET notice_json=?,connector_version=?,last_seen=?
                WHERE source_id=? AND external_id=?''',
                (encoded, connector_version, now, notice.source, notice.external_id))
        if notice.source in {'eis', 'eis_223'}:
            from .observations import record_observation
            record_observation(conn, notice, encoded, now, connector_version)
        return inserted

    def upsert(self, notice, connector_version):
        # Standalone operator/import path retains its existing transaction.
        prepared = self._prepare_upsert(notice, connector_version)
        with closing(self.database.connect()) as conn:
            with conn:
                conn.execute('BEGIN IMMEDIATE')
                return self._write_prepared(conn, *prepared, connector_version)

    def upsert_fenced(self, notice, connector_version, fenced_write):
        """Persist connector notice only within the currently owned job lease.

        The JobRepository callback validates the token and applies this write in
        one transaction. No independent upsert/connection or precheck is allowed.
        """
        from app.jobs.models import LeaseLostError
        if not callable(fenced_write):
            raise LeaseLostError('Connector lease proof unavailable.')
        prepared = self._prepare_upsert(notice, connector_version)
        persisted = []

        def write(conn, _now):
            persisted.append(self._write_prepared(conn, *prepared, connector_version))

        if not fenced_write(write):
            raise LeaseLostError('Connector lease expired before storage.')
        if len(persisted) != 1:
            raise RuntimeError('Invalid fenced connector write callback.')
        return persisted[0]

    def latest_seen_utc(self, source_id):
        """Read-only Worker freshness signal, not tender publication time.

        Empty source snapshots have no proven successful live acquisition and
        must fail closed when used for Telegram delivery. No tenant data enters
        this query.
        """
        if type(source_id) is not str or not re.fullmatch(
                r'[a-z0-9][a-z0-9_-]{0,63}', source_id):
            raise ValueError('Invalid source identity')
        with closing(self.database.connect()) as conn:
            row = conn.execute(
                'SELECT MAX(last_seen) FROM source_opportunities WHERE source_id=?',
                (source_id,),
            ).fetchone()
        if not row or row[0] is None:
            return None
        instant = datetime.fromisoformat(row[0])
        if instant.tzinfo is None:
            raise ValueError('Stored last_seen is not timezone aware')
        return instant.astimezone(timezone.utc)

    def last_succeeded_ingushetia_sync_utc(self, source_id):
        """Read-only durable successful-Worker cutoff for opt-in bot notifications.

        A fenced write can persist some notices before a later job failure.
        A row's last_seen alone cannot certify that the whole lease finished.
        Strict bot delivery must never surface writes newer than the last
        successful job for the same regional source. No network or mutation.
        """
        allowed = {'ru_ingushetia_eis44', 'ru_ingushetia_fabrikant44'}
        if source_id not in allowed or type(source_id) is not str:
            raise ValueError('Only verified regional Worker sources supported')
        # Some environments process many other source jobs. Cap the
        # independent scan to avoid unbounded application-side JSON parsing.
        # If the regional source falls outside this horizon, fail closed.
        with closing(self.database.connect()) as conn:
            rows = conn.execute("""SELECT payload_json,result_json,finished_at
                FROM durable_jobs WHERE job_type='connector.sync.v1'
                AND state='succeeded' AND finished_at IS NOT NULL
                AND account_id IS NULL AND organization_id IS NULL AND company_id IS NULL
                ORDER BY finished_at DESC LIMIT 1000""").fetchall()
        for row in rows:
            try:
                payload, result = json.loads(row[0]), json.loads(row[1])
                stamp = row[2]
                if (type(payload) is dict and payload.get('source_id') == source_id
                        and type(result) is dict and result.get('source_id') == source_id
                        and type(result.get('accepted_count')) is int
                        and result['accepted_count'] > 0
                        and type(result.get('inserted_count')) is int
                        and type(result.get('updated_count')) is int
                        and result['inserted_count'] + result['updated_count'] == result['accepted_count']
                        and type(stamp) is int and stamp > 0):
                    seconds, microseconds = divmod(stamp, 1_000_000)
                    return datetime.fromtimestamp(seconds, timezone.utc).replace(
                        microsecond=microseconds
                    )
            except (TypeError, ValueError, OverflowError, KeyError, OSError):
                continue
        return None

    def read(self, source_id, limit=20, search_terms=(), *, not_before=None,
             not_after=None, _fresh_ingushetia_candidate_scan=False):
        # Most callers may return at most 100 rows. The opt-in source-owned
        # Ingushetia Worker SQL adapter alone may inspect a bounded 1000-row
        # *fresh* candidate pool before applying tenant keyword matching.
        # This cannot trigger upstream HTTP or expose unrelated sources.
        if _fresh_ingushetia_candidate_scan:
            if (source_id not in {'ru_ingushetia_eis44', 'ru_ingushetia_fabrikant44'}
                    or not_before is None or search_terms):
                raise ValueError('Only fresh regional Worker SQL candidate scans are supported')
        limit = max(1, min(int(limit), 1000 if _fresh_ingushetia_candidate_scan else 100))
        # Optional durable Worker freshness cutoff. Legacy callers continue
        # to read historical snapshots unchanged; opt-in notifications must
        # never send arbitrarily old records simply because ONE row was fresh.
        if not_before is not None:
            if (not isinstance(not_before, datetime)
                    or not_before.tzinfo is None
                    or not_before.utcoffset() != timezone.utc.utcoffset(None)):
                raise ValueError('UTC-aware snapshot cutoff required')
            not_before = not_before.astimezone(timezone.utc).isoformat()
        # The strict opt-in bot path can also cap rows to the most recent
        # *completed* durable Worker job. Later partial failed-job writes
        # remain saved for audit, but are not eligible for notifications.
        if not_after is not None:
            if (source_id not in {'ru_ingushetia_eis44', 'ru_ingushetia_fabrikant44'}
                    or not isinstance(not_after, datetime)
                    or not_after.tzinfo or not_after.utcoffset() != timezone.utc.utcoffset(None)):
                raise ValueError('Only UTC regional Worker snapshot upper cutoffs are allowed')
            not_after = not_after.astimezone(timezone.utc).isoformat()
        if not_before is not None and not_after is not None and not_before > not_after:
            return []
        # Bounded local snapshot candidate pool; filtering does not send profile data upstream.
        clause = ' WHERE source_id=?'
        params = [source_id]
        if not_before is not None:
            clause += ' AND last_seen>=?'
            params.append(not_before)
        if not_after is not None:
            clause += ' AND last_seen<=?'
            params.append(not_after)
        with closing(self.database.connect()) as conn:
            rows = conn.execute('SELECT notice_json FROM source_opportunities' + clause +
                                ' ORDER BY last_seen DESC,external_id LIMIT 1000',
                                tuple(params)).fetchall()
        result = []
        terms = tuple(str(term).casefold() for term in search_terms if str(term).strip())[:20]
        for row in rows:
            payload = json.loads(row[0])
            if not isinstance(payload, dict) or payload.get('source') != source_id:
                raise ValueError('Stored source identity mismatch.')
            # Russian adapters may add public law/provenance fields to the
            # frozen TenderNotice dataclass. Recreate only known subclasses
            # when their extra fields are actually present. This keeps the
            # existing normalized base contract for all other sources.
            notice_type = TenderNotice
            if source_id == 'eis_223' and any(key in payload for key in (
                'requested_law', 'observed_law', 'feed_url', 'procurement_signals',
            )):
                from .eis_223_rss import Eis223Notice
                notice_type = Eis223Notice
            elif source_id == 'b2b_center' and any(key in payload for key in (
                'listing_url', 'upstream_url', 'upstream_host', 'origin',
            )):
                from .b2b_center import B2BCenterNotice
                notice_type = B2BCenterNotice
            notice = notice_type(**payload)
            text = ' '.join(str(getattr(notice, field.name) or '') for field in fields(notice)
                            if field.name != 'enrichment').casefold()
            if not terms or any(term in text for term in terms):
                result.append(notice)
            if len(result) >= limit:
                break
        return result
