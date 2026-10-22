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

    def read(self, source_id, limit=20, search_terms=()):
        limit = max(1, min(int(limit), 100))
        # Bounded local snapshot candidate pool; filtering does not send profile data upstream.
        with closing(self.database.connect()) as conn:
            rows = conn.execute('''SELECT notice_json FROM source_opportunities WHERE source_id=?
                ORDER BY last_seen DESC,external_id LIMIT 1000''', (source_id,)).fetchall()
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
