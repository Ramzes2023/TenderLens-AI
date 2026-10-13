"""Offline persistence contract using the real repository and temporary SQLite.

The foundation fake pool returns fixed rows rather than persisted notice JSON;
the file-backed SQLite convention from test_connector_workers exercises both
repository SQL and reconstruction without a service or a mocked read result.
"""
import json
from contextlib import closing
from dataclasses import fields

import pytest

from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.sources.eis_223_rss import (
    Eis223Notice, build_eis_223_rss_url, parse_eis_223_feed,
)
from app.sources.models import TenderNotice
from app.sources.opportunities import OpportunityRepository, validate_notice


@pytest.fixture
def repository(tmp_path):
    # Explicit settings avoid environment/configuration loading entirely.
    database = Database(DatabaseSettings('', tmp_path / 'persistence.db'))
    store = OpportunityRepository(database)
    store.initialize()
    try:
        yield store
    finally:
        database.close()


@pytest.fixture
def eis_223_notice():
    payload = """<rss version="2.0"><channel><item>
    <title>Поставка кабеля №32616463738</title>
    <guid>synthetic-223-notice-1</guid>
    <link>https://zakupki.gov.ru/notice/32616463738</link>
    <pubDate>Tue, 13 Oct 2026 09:00:00 +0300</pubDate>
    <description>Поставка кабеля. Размещение выполняется по: 223-ФЗ</description>
    </item></channel></rss>""".encode('utf-8')
    notices = parse_eis_223_feed(payload, feed_url=build_eis_223_rss_url('кабель'))
    assert len(notices) == 1
    notice = notices[0]
    assert isinstance(notice, Eis223Notice)
    assert isinstance(notice, TenderNotice)
    assert notice.observed_law == '223-FZ'
    assert notice.raw_guid == 'synthetic-223-notice-1'
    assert validate_notice(notice, 'eis_223') is notice
    return notice


def test_eis_223_notice_repository_round_trip(repository, eis_223_notice):
    assert repository.upsert(eis_223_notice, 'connector-sync-v1:eis_223:adapter-r1')

    # Inspect the actual committed payload, not a manufactured reconstruction.
    with closing(repository.database.connect()) as conn:
        rows = conn.execute(
            'SELECT notice_json FROM source_opportunities WHERE source_id=? AND external_id=?',
            eis_223_notice.identity,
        ).fetchall()
    assert len(rows) == 1
    stored = json.loads(rows[0][0])
    assert stored['requested_law'] == '223-FZ'
    assert stored['feed_url'] == eis_223_notice.feed_url
    assert stored['raw_description'] == eis_223_notice.raw_description

    # Desired contract: valid subclass notices must be readable as base notices.
    restored, = repository.read('eis_223')
    assert type(restored) is TenderNotice
    assert {field.name for field in fields(TenderNotice)} <= stored.keys()
    for field in fields(TenderNotice):
        assert getattr(restored, field.name) == getattr(eis_223_notice, field.name)
    with closing(repository.database.connect()) as conn:
        unchanged, = conn.execute(
            'SELECT notice_json FROM source_opportunities WHERE source_id=? AND external_id=?',
            eis_223_notice.identity,
        ).fetchone()
    assert unchanged == rows[0][0]


def test_base_notice_repository_round_trip(repository, eis_223_notice):
    # Same core values and source isolate the extra dataclass fields as the cause.
    base = TenderNotice(**{
        field.name: getattr(eis_223_notice, field.name)
        for field in fields(TenderNotice)
    })
    assert repository.upsert(base, 'connector-sync-v1:eis_223:adapter-r1')
    assert repository.read('eis_223') == [base]


@pytest.mark.parametrize('payload,error', [
    ('{"external_id":"one","title":"Synthetic","url":"https://example.invalid"}', TypeError),
    ('{"source":', json.JSONDecodeError),
    ('[]', TypeError),
    ('null', TypeError),
])
def test_repository_read_rejects_invalid_stored_notice(repository, eis_223_notice, payload, error):
    repository.upsert(eis_223_notice, 'connector-sync-v1:eis_223:adapter-r1')
    with closing(repository.database.connect()) as conn:
        with conn:
            conn.execute(
                'UPDATE source_opportunities SET notice_json=? WHERE source_id=? AND external_id=?',
                (payload, *eis_223_notice.identity),
            )
    with pytest.raises(error):
        repository.read('eis_223')
