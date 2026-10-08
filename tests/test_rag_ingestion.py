"""Offline durable ingestion fixtures; all embeddings deterministic, no service calls."""
import asyncio
import hashlib
import json
import os
import threading
import uuid
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pymupdf
import pytest
from fastapi.testclient import TestClient
from gigachat.exceptions import ResponseError

from app.api.config import ApiSettings
from app.api.main import create_app
from app.api.runtime import ApiRuntime
from app.api.security import SESSION_COOKIE
from app.auth import AuthRepository, AuthService
from app.companies import CompanyRepository, CompanyService
from app.database.backend import Database
from app.database.config import DatabaseSettings
from app.jobs import HandlerRegistry, JobRepository, JobScope, JobService
from app.jobs.worker import ExecutionContext, Worker, PermanentJobError, main
from app.llm.config import GigaChatSettings
from app.llm.models import LLMResponse
from app.organizations import OrganizationRepository, OrganizationService
from app.parsers.pdf import MAX_BYTES, parse_pdf
from app.rag.config import RagSettings
from app.rag.chunking import chunk_pages
from app.rag.documents import DocumentError, RagDocumentStore
from app.rag.embedding import EmbeddingError, TransientEmbeddingError, GigaChatEmbeddingProvider
from app.rag.ingestion import (JOB_TYPE, RagIngestionService, RagIngestionHandler,
                               pipeline_identity, vector_scope, extract_staged_pdf, load_ingestion_options)
from app.rag.models import RetrievedChunk
from app.rag.qdrant_store import QdrantVectorStore, QdrantStoreError, QdrantSchemaError
from app.rag.service import RagService
from app.scoring.models import CompanyProfile


def pdf(text='Private document content. Delivery in thirty days. ' * 20):
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_textbox(pymupdf.Rect(40, 40, 550, 800), text)
        return document.tobytes()


class Embedder:
    def __init__(self):
        self.calls = []
        self.failure = None

    def embed_many(self, texts):
        self.calls.append(tuple(texts))
        if self.failure is not None:
            error, self.failure = self.failure, None
            raise error
        return [(1., 0., 0.) for _ in texts]

    def embed(self, text):
        return (1., 0., 0.)


class Vectors:
    def __init__(self):
        self.points = {}
        self.failure = None

    def initialize(self):
        pass

    def upsert_ingestion(self, scope, digest, pipeline, ref, items):
        for chunk, vector in items:
            key = QdrantVectorStore.ingestion_point_id(scope, digest, pipeline, chunk.chunk_index)
            self.points[key] = (scope, digest, pipeline, chunk)
        if self.failure:
            error, self.failure = self.failure, None
            raise error  # simulate committed batch, lost acknowledgement
        return len(items)

    def search(self, owner, digest, vector, limit, *, ingestion_scope, pipeline_version):
        chunks = [value[3] for value in self.points.values() if value[:3] == (ingestion_scope, digest, pipeline_version)]
        return [RetrievedChunk(c.chunk_index, c.page_number, c.text, 1.) for c in chunks[:limit]]


@pytest.fixture
def setup(tmp_path):
    database = Database(DatabaseSettings('', tmp_path / 'jobs.db'))
    now = [1800000000.]
    jobs = JobRepository(database, clock=lambda: now[0])
    jobs.initialize()
    auth_repo = AuthRepository(database)
    account = auth_repo.create_account('rag-a@example.test', 'fake-password-hash')
    other = auth_repo.create_account('rag-b@example.test', 'fake-password-hash')
    organizations = OrganizationRepository(database)
    org = organizations.create('Fixture A', account.id)
    org_b = organizations.create('Fixture B', other.id)
    settings = RagSettings(True, tmp_path / 'vectors', 'rag_fixture', 'fake-model', 300, 40, 5, 2000)
    documents = RagDocumentStore(tmp_path / 'staged')
    service = RagIngestionService(JobService(jobs), documents, settings)
    embedder, vectors = Embedder(), Vectors()
    rag = RagService(settings, embedder=embedder, store=vectors)
    handler = RagIngestionHandler(service, rag, batch_size=2, extract=parse_pdf)
    registry = HandlerRegistry()
    registry.register(JOB_TYPE, handler)
    yield SimpleNamespace(database=database, now=now, jobs=jobs, service=service, documents=documents,
                          rag=rag, embedder=embedder, vectors=vectors, handler=handler, registry=registry,
                          scope=JobScope(account.id, org.id), scope_b=JobScope(other.id, org_b.id),
                          auth_repo=auth_repo, organizations=organizations, account=account)
    database.close()


def enqueue(fixture, data=None, scope=None):
    return fixture.service.stage_and_enqueue(pdf() if data is None else data, scope=scope or fixture.scope)


def execute(fixture):
    assert Worker(fixture.jobs, fixture.registry).run_once()


def test_durable_enqueue_reuse_and_safe_wire_contract(setup):
    data = pdf()
    job = enqueue(setup, data)
    assert enqueue(setup, data).id == job.id
    assert job.payload['sha256'] == hashlib.sha256(data).hexdigest()
    assert set(job.payload) == {'schema', 'document_ref', 'sha256', 'pipeline_version'}
    assert 'Private document' not in json.dumps(job.payload)
    # New store/repository instances, no request memory required.
    reopened = RagDocumentStore(setup.documents.directory)
    assert reopened.read(job.payload['document_ref']) == data
    assert JobRepository(setup.database).get(job.id, scope=setup.scope).payload == job.payload
    execute(setup)
    completed = setup.service.get(job.id, scope=setup.scope)
    assert completed.state == 'succeeded'
    assert completed.result['chunk_count'] == len(setup.vectors.points)
    assert max(map(len, setup.embedder.calls)) <= 2
    calls = len(setup.embedder.calls)
    assert enqueue(setup, data).id == job.id
    assert not Worker(setup.jobs, setup.registry).run_once()
    assert len(setup.embedder.calls) == calls
    assert 'Private document' not in json.dumps(completed.result)
    assert reopened.read(job.payload['document_ref']) == data


@pytest.mark.parametrize('location,error', [
    ('embedder', TransientEmbeddingError('fake secret document text')),
    ('vectors', QdrantStoreError('fake secret document text')),
])
def test_transient_partial_failure_retry_does_not_duplicate(setup, location, error):
    job = enqueue(setup)
    getattr(setup, location).failure = error
    execute(setup)
    failed = setup.service.get(job.id, scope=setup.scope)
    assert failed.state == 'queued'
    assert failed.result is None and failed.failure_code == 'handler_error'
    if location == 'vectors':
        assert setup.vectors.points  # committed partial batch before failure
    setup.now[0] += 2
    execute(setup)
    result = setup.service.get(job.id, scope=setup.scope)
    assert result.state == 'succeeded'
    assert len(setup.vectors.points) == result.result['vector_count']


def test_expired_lease_replay_and_stale_completion_fencing(setup):
    job = enqueue(setup)
    stale = setup.jobs.claim_next('worker-' + uuid.uuid4().hex)
    context = ExecutionContext(stale.job, threading.Event())
    result = setup.handler(context, stale.job.payload)
    original_ids = set(setup.vectors.points)
    setup.now[0] += 61
    assert setup.jobs.recover_expired() == 1
    assert not setup.jobs.complete(job.id, stale.token, result)
    assert not setup.jobs.fail(job.id, stale.token, retryable=True)
    execute(setup)
    assert set(setup.vectors.points) == original_ids
    assert setup.service.get(job.id, scope=setup.scope).state == 'succeeded'


@pytest.mark.parametrize('error', [EmbeddingError('credential secret'), QdrantSchemaError('schema secret'),
                                 ValueError('invalid configuration secret')])
def test_provider_auth_configuration_and_schema_errors_permanent(setup, error):
    job = enqueue(setup)
    setup.embedder.failure = error
    execute(setup)
    result = setup.service.get(job.id, scope=setup.scope)
    assert result.state == 'failed' and result.attempt_count == 1
    assert result.failure_code == 'permanent_failure' and result.result is None
    assert 'secret' not in json.dumps(setup.service.public_status(result))


@pytest.mark.parametrize('data', [b'%PDF-corrupt', pdf('')])
def test_invalid_or_empty_document_permanent(setup, data):
    job = enqueue(setup, data)
    execute(setup)
    assert setup.service.get(job.id, scope=setup.scope).state == 'failed'
    assert not setup.embedder.calls


def test_encrypted_document_permanent(setup):
    with pymupdf.open(stream=pdf(), filetype='pdf') as document:
        data = document.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw='fake', user_pw='fake')
    job = enqueue(setup, data)
    execute(setup)
    assert setup.service.get(job.id, scope=setup.scope).failure_code == 'permanent_failure'


@pytest.mark.parametrize('reference', ['../file', '/absolute', 'C:\\absolute', 'a' * 63, 'A' * 64, 'a' * 64 + '/..'])
def test_reference_path_policy(setup, reference):
    for operation in (setup.documents.read, setup.documents.delete):
        with pytest.raises(DocumentError):
            operation(reference)


def test_oversize_and_integrity_rejected(setup):
    with pytest.raises(DocumentError):
        enqueue(setup, b'%PDF-' + b'x' * MAX_BYTES)
    job = enqueue(setup)
    path = setup.documents.directory / (job.payload['document_ref'] + '.pdf')
    path.write_bytes(b'%PDF-tampered')
    execute(setup)
    assert setup.service.get(job.id, scope=setup.scope).failure_code == 'permanent_failure'


def test_symlink_escape(setup, tmp_path):
    reference = 'a' * 64
    target = tmp_path / 'outside.pdf'
    target.write_bytes(pdf())
    path = setup.documents.directory / (reference + '.pdf')
    try:
        path.symlink_to(target)
    except OSError:
        pytest.skip('Windows symlink privilege unavailable')
    with pytest.raises(DocumentError):
        setup.documents.read(reference)
    with pytest.raises(DocumentError):
        setup.documents.delete(reference)
    assert target.exists()


def test_scope_tampering_and_cross_tenant_retrieval(setup):
    data = pdf()
    one, two = enqueue(setup, data), enqueue(setup, data, setup.scope_b)
    assert one.id != two.id and one.payload['document_ref'] != two.payload['document_ref']
    assert setup.service.get(one.id, scope=setup.scope_b) is None
    assert setup.service.get(one.id, scope=JobScope(setup.scope_b.account_id, setup.scope.organization_id)) is None
    with pytest.raises(PermanentJobError):
        setup.handler(ExecutionContext(replace(one, scope=setup.scope_b), threading.Event()), one.payload)
    execute(setup)
    execute(setup)
    a = setup.rag.retrieve(0, one.payload['sha256'], 'delivery', ingestion_scope=vector_scope(setup.scope),
                           pipeline_version=one.payload['pipeline_version'])
    b = setup.rag.retrieve(0, two.payload['sha256'], 'delivery', ingestion_scope=vector_scope(setup.scope_b),
                           pipeline_version=two.payload['pipeline_version'])
    assert a and b
    assert len(setup.vectors.points) == len(a) + len(b)
    assert setup.rag.retrieve(0, one.payload['sha256'], 'delivery', ingestion_scope='unauthorized',
                              pipeline_version=one.payload['pipeline_version']) == []


def test_pipeline_configuration_change_reindexes(setup):
    data = pdf()
    one = enqueue(setup, data)
    changed = replace(setup.rag.settings, embedding_model='fake-model-v2')
    service = RagIngestionService(setup.service.jobs, setup.documents, changed)
    two = service.stage_and_enqueue(data, scope=setup.scope)
    assert one.id != two.id
    assert pipeline_identity(changed) != setup.service.pipeline
    assert QdrantVectorStore.ingestion_point_id('scope', 'a' * 64, setup.service.pipeline, 0) != \
        QdrantVectorStore.ingestion_point_id('scope', 'a' * 64, pipeline_identity(changed), 0)


def test_worker_adapter_owns_no_event_loop(setup):
    data = pdf()
    # Same synchronous isolated parser works even when caller owns an event loop.
    async def run():
        job = enqueue(setup, data)
        assert extract_staged_pdf(data).status == 'ok'
        result = setup.handler(ExecutionContext(job, threading.Event()), job.payload)
        assert result['status'] == 'complete'
    asyncio.run(run())


def test_excessive_chunk_work_is_bounded():
    with pytest.raises(ValueError, match='chunk limit'):
        chunk_pages(['x' * 10000], 300, 299, max_chunks=8)


@pytest.mark.parametrize('status,retryable', [(401, False), (403, False), (400, False), (429, True), (503, True)])
def test_gigachat_error_classification_has_no_body(status, retryable):
    from unittest.mock import MagicMock
    client = MagicMock()
    client.__enter__.return_value.embeddings.side_effect = ResponseError('https://fake.invalid', status,
                                                                       b'credential PDF text', None)
    with patch('app.rag.embedding.GigaChat', return_value=client):
        provider = GigaChatEmbeddingProvider(GigaChatSettings('fake-key', 'fake-model'))
        with pytest.raises(EmbeddingError) as raised:
            provider.embed_many(['customer text'])
    assert isinstance(raised.value, TransientEmbeddingError) is retryable
    assert 'credential' not in str(raised.value) and 'PDF' not in str(raised.value)


@pytest.mark.parametrize('vectors', [[(float('nan'),)], [], [(1.,), (1., 2.)]])
def test_invalid_embedding_payload_permanent(setup, vectors):
    job = enqueue(setup)
    with patch.object(setup.embedder, 'embed_many', return_value=vectors):
        execute(setup)
    assert setup.service.get(job.id, scope=setup.scope).failure_code == 'permanent_failure'
    assert not setup.vectors.points


def test_revoked_authorization_prevents_worker_processing(setup):
    setup.organizations.add_membership(setup.scope.organization_id, setup.scope_b.account_id, 'member')
    member_scope = JobScope(setup.scope_b.account_id, setup.scope.organization_id)
    job = enqueue(setup, scope=member_scope)
    setup.organizations.remove_membership(member_scope.organization_id, member_scope.account_id)
    execute(setup)
    assert setup.service.get(job.id, scope=member_scope).failure_code == 'permanent_failure'
    assert not setup.embedder.calls


def test_symlink_policy_without_os_privilege(setup):
    reference = 'a' * 64
    original = Path.is_symlink
    def is_symlink(path):
        return path.name == reference + '.pdf' or original(path)
    with patch.object(Path, 'is_symlink', is_symlink):
        with pytest.raises(DocumentError):
            setup.documents.read(reference)
        with pytest.raises(DocumentError):
            setup.documents.delete(reference)


def test_explicit_worker_cli_registers_and_executes_production_handler(setup):
    from app.jobs.worker import ShutdownResult
    job = enqueue(setup)
    class ControlledPool:
        def __init__(self, repository, registry):
            assert isinstance(registry.resolve(JOB_TYPE), RagIngestionHandler)
            self.repository, self.registry = repository, registry
        def start(self):
            assert Worker(self.repository, self.registry).run_once()
        def stop(self):
            return ShutdownResult(True, 0)
    with patch('app.rag.config.load_rag_settings', return_value=setup.rag.settings), \
         patch('app.rag.ingestion.load_ingestion_options', return_value=(setup.documents, 2)), \
         patch('app.rag.service.RagService', return_value=setup.rag), \
         patch('app.database.config.load_database_settings', return_value=setup.database.settings), \
         patch('app.jobs.JobRepository', return_value=setup.jobs), \
         patch('app.jobs.worker.WorkerPool', ControlledPool), \
         patch('signal.signal', side_effect=lambda signum, callback: callback(signum, None)):
        assert main(['--rag']) == 0
    assert setup.service.get(job.id, scope=setup.scope).state == 'succeeded'


def test_local_vector_lock_serializes_independent_instances(setup):
    from concurrent.futures import ThreadPoolExecutor
    def open_store(index):
        QdrantVectorStore(setup.rag.settings.qdrant_path, 'lock_fixture').initialize()
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(open_store, range(8)))


def test_worker_configuration_failure_is_safe(tmp_path):
    with patch.dict(os.environ, {'RAG_ENABLED': 'false'}):
        assert main(['--rag']) == 2
    with patch.dict(os.environ, {'VALYQON_RAG_EMBED_BATCH_SIZE': '999'}):
        with pytest.raises(ValueError):
            load_ingestion_options()


def test_real_local_vector_upsert_is_idempotent_and_scoped(setup):
    # Qdrant embedded/local mode only, no server.
    store = QdrantVectorStore(setup.rag.settings.qdrant_path, 'durable_fixture')
    setup.rag.store = store
    one = enqueue(setup)
    two = enqueue(setup, scope=setup.scope_b)
    execute(setup)
    execute(setup)
    claim_job = setup.service.get(one.id, scope=setup.scope)
    setup.handler(ExecutionContext(claim_job, threading.Event()), claim_job.payload)
    with store._client() as client:
        count = client.count(collection_name=store.collection, exact=True).count
    assert count == sum(setup.service.get(j.id, scope=j.scope).result['vector_count'] for j in (one, two))
    result = setup.rag.retrieve(0, one.payload['sha256'], 'delivery', ingestion_scope=vector_scope(one.scope),
                                pipeline_version=one.payload['pipeline_version'])
    assert result and result[0].page_number == 1


def test_application_upload_status_ask_and_company_isolation(setup):
    auth = AuthService(setup.auth_repo)
    companies = CompanyRepository(setup.database)
    profile = CompanyProfile(profile_version='fixture', company_name='Fixture', business_mode='sell',
                             product_keywords=['test'], search_keywords=['test'])
    company = companies.create_for_organization(account_id=setup.account.id, organization_id=setup.scope.organization_id,
                                                name='One', profile=profile)
    other_company = companies.create_for_organization(account_id=setup.account.id, organization_id=setup.scope.organization_id,
                                                      name='Two', profile=profile)
    class Provider:
        async def generate(self, prompt, *, max_tokens):
            assert 'semantic search' in prompt
            return LLMResponse('Delivery in thirty days [стр. 1].', 'fake', 'fake')
    runtime = ApiRuntime(auth_service=auth, organization_service=OrganizationService(setup.organizations),
                         company_service=CompanyService(companies), rag_service=setup.rag,
                         rag_ingestion_service=setup.service, provider=Provider())
    prefix = f'/api/v1/organizations/{setup.scope.organization_id}/companies/{company.id}/rag'
    other_prefix = f'/api/v1/organizations/{setup.scope.organization_id}/companies/{other_company.id}/rag'
    data = pdf()
    with TestClient(create_app(runtime=runtime, settings=ApiSettings('127.0.0.1', 8000, False))) as client:
        client.cookies.set(SESSION_COOKIE, auth.create_session(setup.account))
        response = client.post(prefix + '/documents', files={'file': ('../../customer-email.pdf', data, 'application/pdf')})
        assert response.status_code == 202, response.text
        body = response.json()
        job_id = body['job_id']
        assert not body['ready']
        assert client.post(prefix + f'/jobs/{job_id}/ask', json={'question': 'delivery?'}).status_code == 409
        execute(setup)
        assert client.get(prefix + f'/jobs/{job_id}').json()['ready']
        assert client.get(other_prefix + f'/jobs/{job_id}').status_code == 404
        assert client.post(other_prefix + f'/jobs/{job_id}/ask', json={'question': 'delivery?'}).status_code == 404
        answer = client.post(prefix + f'/jobs/{job_id}/ask', json={'question': 'delivery?'})
        assert answer.status_code == 200, answer.text
        assert answer.json()['sources'][0]['page_number'] == 1
        original_settings = setup.rag.settings
        setup.rag.settings = replace(original_settings, embedding_model='changed-model')
        assert client.post(prefix + f'/jobs/{job_id}/ask', json={'question': 'delivery?'}).status_code == 409
        setup.rag.settings = original_settings
        assert client.post(prefix + '/documents', files={'file': ('renamed.pdf', data, 'application/pdf')}).json()['job_id'] == job_id
        assert 'customer-email' not in ' '.join(p.name for p in setup.documents.directory.iterdir())
        blocked = client.post(prefix + '/documents', files={'file': ('a.pdf', pdf(), 'application/pdf')},
                              headers={'Origin': 'https://evil.invalid', 'Sec-Fetch-Site': 'cross-site'})
        assert blocked.status_code == 403
        client.cookies.clear()
        client.cookies.set(SESSION_COOKIE, auth.create_session(setup.auth_repo.find_account_by_id(setup.scope_b.account_id)))
        assert client.get(prefix + f'/jobs/{job_id}').status_code == 403


def test_upload_quota_denial_does_not_enqueue(setup):
    from app.quotas import QuotaSettings, Limits
    setup.jobs.quotas = QuotaSettings(True, Limits(0, 0, 0))
    auth = AuthService(setup.auth_repo)
    runtime = ApiRuntime(auth_service=auth, organization_service=OrganizationService(setup.organizations),
                         rag_ingestion_service=setup.service)
    prefix = f'/api/v1/organizations/{setup.scope.organization_id}/rag'
    with TestClient(create_app(runtime=runtime, settings=ApiSettings('127.0.0.1', 8000, False))) as client:
        client.cookies.set(SESSION_COOKIE, auth.create_session(setup.account))
        denied = client.post(prefix + '/documents', files={'file': ('fixture.pdf', pdf(), 'application/pdf')})
        assert denied.status_code == 429, denied.text
        assert denied.headers['Cache-Control'] == 'no-store'
        assert int(denied.headers['Retry-After']) >= 1
        client.cookies.clear()
        assert client.post(prefix + '/documents', files={'file': ('fixture.pdf', pdf(), 'application/pdf')}).status_code == 401
    with setup.database.connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM durable_jobs').fetchone()[0] == 0
