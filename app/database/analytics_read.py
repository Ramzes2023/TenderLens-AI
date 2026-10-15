"""Opt-in SQLite analytics read limits; legacy repository reads are unchanged."""
from contextlib import contextmanager
from dataclasses import dataclass
import math
import sqlite3
import time

from .backend import StorageError


@dataclass(frozen=True)
class AnalyticsReadLimits:
    deadline: float
    events: int
    bytes: int
    snapshot_bytes: int

    def __post_init__(self):
        if (not math.isfinite(self.deadline)
                or any(type(v) is not int or v < 1 for v in
                       (self.events, self.bytes, self.snapshot_bytes))):
            raise ValueError('Invalid analytics read limits.')


@contextmanager
def bounded_read(conn, limits):
    if limits is None:
        yield
        return
    # Do not claim a portable execution budget before PostgreSQL runtime proof.
    if not isinstance(conn, sqlite3.Connection):
        raise StorageError('Bounded analytics reads are not verified on this backend.')
    remaining = limits.deadline - time.monotonic()
    if remaining <= 0:
        raise StorageError('Analytics database read budget exceeded.')
    conn.execute('PRAGMA query_only=ON')
    conn.execute('PRAGMA busy_timeout=' + str(max(1, int(remaining * 1000))))
    conn.set_progress_handler(lambda: int(time.monotonic() >= limits.deadline), 1000)
    try:
        yield
    finally:
        conn.set_progress_handler(None, 0)


def preflight(conn, clause, params, limits):
    """Return only scalar sizes before fetching any stored bodies, in one txn.

    LIMIT stops at events+1. BLOB length counts UTF-8 bytes (including embedded
    NUL), not characters. SQL work is interruptible by bounded_read's handler.
    """
    sizes = [f'length(CAST({field} AS BLOB))' for field in
             ('snapshot_json', 'attempted_sources_json', 'successful_sources_json', 'failed_sources_json')]
    row = conn.execute(
        'SELECT COUNT(*), COALESCE(SUM(body_bytes),0), COALESCE(MAX(snapshot_bytes),0) FROM ('
        'SELECT ' + '+'.join(sizes) + ' AS body_bytes, ' + sizes[0] +
        ' AS snapshot_bytes FROM discovery_search_history WHERE ' + clause + ' LIMIT ?)',
        (*params, limits.events + 1)).fetchone()
    if row[0] > limits.events or row[1] > limits.bytes or row[2] > limits.snapshot_bytes:
        raise StorageError('Analytics persisted population exceeds read limits.')
    return row[0]
