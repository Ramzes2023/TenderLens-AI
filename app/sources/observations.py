"""Atomic public EIS evidence history in the existing database transaction.

A previously seen content revision is a replay, never a new change event.
Missing fields and naive date-times do not establish changes or removals.
"""
import hashlib
import json
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal

from .ru_notice_changes import Observation, ObservationKey, compare_observations


def _observation(stored, instant):
    # Hash arbitrary RSS GUIDs into comparator-compatible identifiers. The exact
    # source identity remains in the database and original JSON.
    key = ObservationKey(stored['source'], hashlib.sha256(
        stored['external_id'].encode('utf-8')).hexdigest())
    values = {}
    for field, original in (('title', 'title'), ('buyer', 'customer')):
        text = stored.get(original)
        if (isinstance(text, str) and text == text.strip()
                and not any(ord(c) < 32 or ord(c) == 127 for c in text)):
            values[field] = text
    if stored.get('initial_price') is not None:
        values['price'] = Decimal(str(stored['initial_price']))
    if stored.get('currency'):
        values['currency'] = stored['currency']
    deadline = stored.get('deadline')
    if deadline:
        try:
            if len(deadline) == 10:
                values['deadline'] = date.fromisoformat(deadline)
            else:
                parsed = datetime.fromisoformat(deadline.replace('Z', '+00:00'))
                if parsed.tzinfo is not None:
                    values['deadline'] = parsed
        except ValueError:
            pass  # Local EIS times have no independent timezone evidence.
    return Observation(key, datetime.fromisoformat(instant), values)


def record_observation(conn, notice, encoded, now, connector_version):
    stored = json.loads(encoded)
    # The metadata observation clock changes on every RSS poll; it is not a
    # procurement revision. Keep the complete original JSON in evidence history,
    # but exclude only this volatile observation timestamp from revision identity.
    fingerprint = {**stored}
    if isinstance(stored.get('enrichment'), dict):
        fingerprint['enrichment'] = {key: value for key, value in stored['enrichment'].items()
                                     if key != 'observed_at'}
    canonical = json.dumps(fingerprint, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    revision = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    if conn.execute('''SELECT 1 FROM source_notice_observations
        WHERE source_id=? AND external_id=? AND revision=?''',
        (*notice.identity, revision)).fetchone() is not None:
        return
    previous = conn.execute('''SELECT notice_json,observed_at FROM source_notice_observations
        WHERE source_id=? AND external_id=? ORDER BY observed_at DESC,revision LIMIT 1''',
        notice.identity).fetchone()
    current = _observation(stored, now)
    before = _observation(json.loads(previous[0]), previous[1]) if previous else None
    result = compare_observations(before, current)
    comparison = json.dumps(asdict(result), default=str, ensure_ascii=False, separators=(',', ':'))
    conn.execute('''INSERT INTO source_notice_observations
        (source_id,external_id,revision,notice_json,connector_version,observed_at,comparison_json)
        VALUES(?,?,?,?,?,?,?) ON CONFLICT(source_id,external_id,revision) DO NOTHING''',
        (*notice.identity, revision, encoded, connector_version, now, comparison))
