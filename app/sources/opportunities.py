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


def validate_notice(notice, source_id):
    if not isinstance(notice, TenderNotice) or notice.source != source_id:
        raise ValueError('Invalid normalized notice.')
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

    def upsert(self, notice, connector_version):
        validate_notice(notice, notice.source)
        if (type(connector_version) is not str or not re.fullmatch(
                r'connector-sync-v1:' + re.escape(notice.source) + r':adapter-r[1-9][0-9]{0,3}', connector_version)):
            raise ValueError('Invalid connector provenance.')
        encoded = json.dumps(asdict(notice), ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        now = datetime.now(timezone.utc).isoformat()
        with closing(self.database.connect()) as conn:
            with conn:
                conn.execute('BEGIN IMMEDIATE')
                inserted = conn.execute('''INSERT INTO source_opportunities
                    (source_id,external_id,notice_json,connector_version,first_seen,last_seen)
                    VALUES(?,?,?,?,?,?) ON CONFLICT(source_id,external_id) DO NOTHING''',
                    (notice.source, notice.external_id, encoded, connector_version, now, now)).rowcount == 1
                if not inserted:
                    conn.execute('''UPDATE source_opportunities SET notice_json=?,connector_version=?,last_seen=?
                        WHERE source_id=? AND external_id=?''',
                        (encoded, connector_version, now, notice.source, notice.external_id))
                return inserted

    def read(self, source_id, limit=20, search_terms=()):
        limit = max(1, min(int(limit), 100))
        # Bounded local snapshot candidate pool; filtering does not send profile data upstream.
        with closing(self.database.connect()) as conn:
            rows = conn.execute('''SELECT notice_json FROM source_opportunities WHERE source_id=?
                ORDER BY last_seen DESC,external_id LIMIT 1000''', (source_id,)).fetchall()
        result = []
        terms = tuple(str(term).casefold() for term in search_terms if str(term).strip())[:20]
        for row in rows:
            notice = TenderNotice(**json.loads(row[0]))
            text = ' '.join(str(getattr(notice, field.name) or '') for field in fields(notice)).casefold()
            if not terms or any(term in text for term in terms):
                result.append(notice)
            if len(result) >= limit:
                break
        return result
