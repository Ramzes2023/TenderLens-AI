"""Offline runner contracts; these tests never constitute live evidence."""
import importlib.util
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch

from app.sources.models import TenderNotice
from app.sources import eis_rss, eis_223_rss, b2b_center

spec = importlib.util.spec_from_file_location('ru12_six', Path(__file__).with_name('ru12_six_sources_live_smoke.py'))
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


def test_six_exact_labels():
    assert [label for _, label in smoke.TARGETS.values()] == [
        'EIS 44-FZ', 'EIS 223-FZ', 'B2B-Center', 'TEK-Torg', 'Roseltorg', 'Fabrikant']


def test_failures_continue_and_never_use_manifest(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('VALYQON_RU12_MANIFEST', str(tmp_path/'does-not-exist.json'))
    async def failed(*args, **kwargs):
        raise TimeoutError('synthetic-private-secret')
    with patch.object(eis_rss.EisRssSource, 'fetch', failed), \
         patch.object(eis_223_rss.Eis223RssSource, 'fetch', failed), \
         patch.object(b2b_center.B2BCenterSource, 'fetch', failed):
        result = smoke.run(tmp_path, proof_origin='offline')
    assert len(result['sources']) == 6
    assert all(entry['state'] == 'BLOCKED' for entry in result['sources'].values())
    assert all(entry['records'] == entry['db'] == entry['query'] == 0 for entry in result['sources'].values())
    assert not result['ai_query_verified']
    output = capsys.readouterr().out
    assert all(label in output for _, label in smoke.TARGETS.values())
    assert 'synthetic-private-secret' not in output
    assert list(tmp_path.glob('ru12-six-*/notices.sqlite'))


def test_freshness_requires_observed_recent_date():
    now = datetime(2026, 10, 14, tzinfo=timezone.utc)
    def notice(published=None, deadline=None):
        return TenderNotice('eis', 'test', 'Synthetic', 'https://zakupki.gov.ru/',
                            published_at=published, deadline=deadline)
    assert smoke.fresh(notice('2026-10-14', '2026-10-15'), now)
    assert not smoke.fresh(notice(), now)
    assert not smoke.fresh(notice('2026-01-01'), now)
    assert not smoke.fresh(notice('2026-10-15'), now)
    assert not smoke.fresh(notice('2026-10-14', '2026-10-13'), now)


def test_offline_roundtrip_cannot_claim_live(tmp_path):
    import asyncio
    async def acquired(source, limit=20):
        return [TenderNotice(source.name, 'synthetic-record', 'Synthetic notice',
                             'https://www.b2b-center.ru/search/number/synthetic-record/',
                             published_at=datetime.now(timezone.utc).isoformat())]
    async def detail(*args):
        return None
    with patch.object(eis_rss.EisRssSource, 'fetch', acquired), \
         patch.object(eis_223_rss.Eis223RssSource, 'fetch', acquired), \
         patch.object(b2b_center.B2BCenterSource, 'fetch', acquired), \
         patch.object(smoke, 'verify_detail', detail):
        result = smoke.run(tmp_path, proof_origin='offline')
    for key in ('eis_44fz', 'eis_223fz', 'b2b_center'):
        entry = result['sources'][key]
        assert entry['records'] == entry['db'] == entry['query'] == 1
        assert entry['state'] == 'BLOCKED'
        assert entry['proof_origin'] == 'offline'
    assert result['ai_query_verified'] is False
