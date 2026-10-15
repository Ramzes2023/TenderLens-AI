"""Offline morphology and embedded-storage concurrency regressions."""
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import multiprocessing
import builtins
import os
from pathlib import Path
import threading
from unittest.mock import patch

import pytest

from app.monitoring.service import _term_match, prefilter_notice
from app.scoring.models import CompanyProfile
from app.sources.models import TenderNotice
from app.rag.models import DocumentChunk
from app.rag.qdrant_store import QdrantVectorStore, QdrantStoreError, _path_lock


@pytest.mark.parametrize('term,text', [
    ('алюминиевый профиль', 'Поставка алюминиевого профиля'),
    ('кабель', 'Поставка кабеля'),
    ('профиль', 'профилей'),
    ('оборудование', 'оборудования'),
    ('насосы', 'насосов'),
    ('подшипники', 'подшипников'),
    ('чёрный кабель', 'ЧЕРНОГО КАБЕЛЯ'),
])
def test_inflections_are_symmetric(term, text):
    assert _term_match(text, term)
    # Symmetry applies to tokens/phrases, excluding surrounding notice prose.
    assert _term_match(term, text.removeprefix('Поставка '))


@pytest.mark.parametrize('term,text', [
    ('gold', 'golden goldhofer'), ('профиль', 'профильный'),
    ('насос', 'насосный'), ('кабель', 'кабельный'),
    ('алюминиевый профиль', 'профиль алюминиевый'),
    ('алюминиевый профиль', 'алюминиевый новый профиль'),
    ('', 'профиль'), ('!!!', 'профиль'), ('ель', 'ели'),
])
def test_boundaries_and_conservative_stems(term, text):
    assert not _term_match(text, term)


def test_monitoring_search_vocabulary_and_exclusions():
    profile = CompanyProfile(profile_version='1', company_name='Test',
                             product_keywords=['gold'], search_keywords=['алюминиевый профиль'])
    notice = TenderNotice(source='eis', external_id='1',
                          title='Поставка алюминиевого профиля', url='https://example.test')
    match = prefilter_notice(notice, profile)
    assert match and match.reasons == ('Направление: алюминиевый профиль',)
    assert profile.product_keywords == ['gold']
    assert prefilter_notice(notice, profile.model_copy(update={'excluded_keywords': ['профиль']})) is None


def _write_process(path, index, barrier):
    barrier.wait(timeout=30)
    store = QdrantVectorStore(Path(path), 'stability')
    store.initialize()
    store.replace_document(index, 'digest', [(DocumentChunk(0, 1, f'owner {index}'), (1., 0.))])
    assert store.search(index, 'digest', (1., 0.))[0].text == f'owner {index}'


def test_fresh_storage_concurrent_processes_preserve_owners(tmp_path):
    context = multiprocessing.get_context('spawn')
    with context.Manager() as manager:
        barrier = manager.Barrier(3)
        with ProcessPoolExecutor(3, mp_context=context) as pool:
            futures = [pool.submit(_write_process, str(tmp_path / 'vectors'), i, barrier) for i in range(3)]
            for future in futures:
                future.result(timeout=60)
    store = QdrantVectorStore(tmp_path / 'vectors', 'stability')
    for index in range(3):
        assert [item.text for item in store.search(index, 'digest', (1., 0.))] == [f'owner {index}']
    assert store.search(99, 'digest', (1., 0.)) == []


def test_thread_lock_covers_constructor_and_close_and_aliases(tmp_path):
    barrier = threading.Barrier(8)
    active = 0
    events = []
    class Client:
        def __init__(self, **kwargs):
            nonlocal active
            assert _path_lock(Path(kwargs['path'])).locked()
            assert active == 0
            active += 1
            events.append('open')
        def close(self):
            nonlocal active
            assert active == 1
            events.append('close')
            active -= 1
    def run(index):
        barrier.wait(timeout=10)
        path = tmp_path / 'vectors' if index % 2 else tmp_path / 'alias' / '..' / 'vectors'
        QdrantVectorStore(path, f'collection{index}').initialize()
    with patch('app.rag.qdrant_store.QdrantClient', Client):
        with ThreadPoolExecutor(8) as pool:
            list(pool.map(run, range(8)))
    assert events == ['open', 'close'] * 8


def test_operation_failure_closes_client_and_releases_lock(tmp_path):
    store = QdrantVectorStore(tmp_path / 'vectors', 'stability')
    with pytest.raises(RuntimeError, match='synthetic'):
        with store._client():
            raise RuntimeError('synthetic')
    store.initialize()
    assert not store.has_document(1, 'digest')


def test_empty_lock_file_is_written_only_after_os_acquisition(tmp_path):
    store = QdrantVectorStore(tmp_path, 'stability')
    acquired = False
    original_open = builtins.open
    class Handle:
        def __init__(self, handle):
            self.handle = handle
        def __getattr__(self, name):
            return getattr(self.handle, name)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.handle.close()
        def write(self, value):
            assert acquired, 'lock-file write preceded OS lock acquisition'
            return self.handle.write(value)
    def open_handle(path, *args, **kwargs):
        handle = original_open(path, *args, **kwargs)
        return Handle(handle) if Path(path).name == '.valyqon.lock' else handle
    if os.name == 'nt':
        import msvcrt
        target, original, acquire_flag = 'msvcrt.locking', msvcrt.locking, msvcrt.LK_NBLCK
    else:
        import fcntl
        target, original, acquire_flag = 'fcntl.flock', fcntl.flock, fcntl.LOCK_EX | fcntl.LOCK_NB
    def locking(fd, flag, *args):
        nonlocal acquired
        result = original(fd, flag, *args)
        acquired = flag == acquire_flag
        return result
    with patch('builtins.open', open_handle), patch(target, locking):
        with store._local_lock():
            assert acquired
    assert not acquired


def test_constructor_failure_releases_both_locks(tmp_path):
    store = QdrantVectorStore(tmp_path / 'vectors', 'stability')
    with patch('app.rag.qdrant_store.QdrantClient', side_effect=RuntimeError('synthetic')):
        with pytest.raises(QdrantStoreError):
            store.initialize()
    store.initialize()
