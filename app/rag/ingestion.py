"""Versioned durable ingestion; SQL jobs are the fenced completion manifest."""
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

import httpx

from app.jobs import JobScope, JobValueError
from app.auth import AuthRepository
from app.organizations import OrganizationRepository, OrganizationService, OrganizationError
from app.jobs.worker import PermanentJobError, RetryableJobError
from app.parsers.pdf import MAX_BYTES, PdfSummary
from .chunking import chunk_pages
from .config import PROJECT_ROOT, RagConfigurationError
from .documents import DocumentError, RagDocumentStore, StorageQuotaExceeded, document_reference
from .embedding import EmbeddingError, TransientEmbeddingError
from .qdrant_store import QdrantStoreError, QdrantSchemaError

JOB_TYPE = 'rag.ingest.v1'
PIPELINE_VERSION = 'rag-ingest-v1'
MAX_CHUNKS = 20_000


def embedding_identity(settings):
    """Non-secret configured identity. Bump revision when adapter semantics change."""
    return [settings.embedding_provider, settings.embedding_model, 'embedding-adapter-v1']


def pipeline_identity(settings):
    # Material extraction/chunking/payload revision is the explicit version.
    # Model/chunk configuration changes automatically create a new generation.
    material = [PIPELINE_VERSION, embedding_identity(settings),
                settings.chunk_size, settings.chunk_overlap, settings.qdrant_collection, 'page-payload-v1']
    return PIPELINE_VERSION + ':' + hashlib.sha256(json.dumps(material, separators=(',', ':')).encode()).hexdigest()


def vector_scope(scope):
    return hashlib.sha256(json.dumps(scope.values, separators=(',', ':')).encode()).hexdigest()


def load_ingestion_options():
    raw = os.environ.get('VALYQON_RAG_DOCUMENT_DIR', '').strip()
    directory = Path(raw) if raw else Path(os.environ.get('DATA_DIR') or PROJECT_ROOT / 'data') / 'rag-documents'
    if not directory.is_absolute():
        directory = PROJECT_ROOT / directory
    try:
        batch = int(os.environ.get('VALYQON_RAG_EMBED_BATCH_SIZE', '16'))
        if not 1 <= batch <= 64:
            raise ValueError
    except ValueError:
        raise RagConfigurationError('Invalid RAG embedding batch size.') from None
    try:
        limit = int(os.environ.get('VALYQON_RAG_MAX_TENANT_DOCUMENTS', '1000'))
        return RagDocumentStore(directory, max_tenant_documents=limit), batch
    except (ValueError, DocumentError):
        raise RagConfigurationError('Invalid tenant document limit.') from None


def extract_staged_pdf(data):
    # Same isolated parser as interactive analysis, synchronous subprocess adapter.
    # Owns no asyncio event loop; worker handlers are synchronous.
    try:
        process = subprocess.run([sys.executable, '-m', 'app.parsers.pdf_worker'], input=data,
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                 cwd=PROJECT_ROOT, timeout=30, check=False)
        if process.returncode != 0:
            raise PermanentJobError()
        return PdfSummary(**json.loads(process.stdout))
    except (subprocess.TimeoutExpired, ValueError, TypeError):
        raise PermanentJobError() from None


class RagIngestionService:
    def __init__(self, jobs, documents, settings):
        self.jobs, self.documents, self.settings = jobs, documents, settings
        self.pipeline = pipeline_identity(settings)

    def stage_and_enqueue(self, data, *, scope):
        if not isinstance(scope, JobScope) or scope.account_id is None or scope.organization_id is None:
            raise JobValueError('Authorized organization scope required.')
        self.validate_scope(scope)
        reference, digest = self.documents.identity(data, scope, self.pipeline)
        payload = {'schema': 1, 'document_ref': reference, 'sha256': digest, 'pipeline_version': self.pipeline}
        repository = self.jobs.repository
        created = False

        def references(conn, exclude=None):
            # All states retained, including failed/cancelled and old pipelines.
            rows = conn.execute("SELECT payload_json FROM durable_jobs WHERE job_type=? AND organization_id=? AND id<>?",
                                (JOB_TYPE, scope.organization_id, exclude or '')).fetchall()
            return {json.loads(row['payload_json']).get('document_ref') for row in rows}

        def prepare(conn, row, inserted):
            nonlocal created
            retained = references(conn, row['id'] if inserted else None)
            if reference not in retained and len(retained) >= self.documents.max_tenant_documents:
                raise StorageQuotaExceeded()
            path = self.documents._path(reference)
            created = not path.exists()
            self.documents.stage(data, scope, self.pipeline)

        try:
            return self.jobs.enqueue(JOB_TYPE, payload, scope=scope,
                                     idempotency_key=digest + ':' + self.pipeline, _prepare=prepare)
        except BaseException:
            if created:
                # Reconcile after rollback, including an ambiguous commit outcome.
                # Never delete on unavailable DB: retain for operator reconciliation.
                with repository._transaction() as conn:
                    repository.lock_rag_storage(conn, scope)
                    if reference not in references(conn):
                        self.documents.delete(reference)
            raise

    def validate_scope(self, scope):
        database = self.jobs.repository.database
        account = AuthRepository(database).find_account_by_id(scope.account_id)
        try:
            OrganizationService(OrganizationRepository(database)).require_membership(
                account, scope.organization_id, {'owner', 'admin', 'member'})
        except OrganizationError:
            raise JobValueError('Ingestion authorization unavailable.') from None
        self.jobs.repository.validate_scope(scope)

    def get(self, job_id, *, scope):
        job = self.jobs.get(job_id, scope=scope)
        return job if job is not None and job.job_type == JOB_TYPE else None

    @staticmethod
    def public_status(job):
        return {'job_id': job.id, 'document_ref': job.payload['document_ref'], 'state': job.state,
                'ready': job.state == 'succeeded', 'result': job.result if job.state == 'succeeded' else None,
                'failure_code': job.failure_code}


class RagIngestionHandler:
    def __init__(self, service, rag, *, batch_size=16, extract=extract_staged_pdf):
        if type(batch_size) is not int or not 1 <= batch_size <= 64:
            raise RagConfigurationError('Invalid RAG embedding batch size.')
        if service.pipeline != pipeline_identity(rag.settings):
            raise RagConfigurationError('Ingestion configuration mismatch.')
        self.service, self.rag, self.batch_size, self.extract = service, rag, batch_size, extract

    def __call__(self, context, payload):
        try:
            return self._ingest(context, payload)
        except (TransientEmbeddingError, httpx.RequestError, TimeoutError):
            raise RetryableJobError() from None
        except QdrantSchemaError:
            raise PermanentJobError() from None
        except QdrantStoreError:
            raise RetryableJobError() from None
        except (DocumentError, EmbeddingError, RagConfigurationError, JobValueError, ValueError, TypeError):
            raise PermanentJobError() from None

    def _ingest(self, context, payload):
        scope = context.job.scope
        if scope.account_id is None or scope.organization_id is None:
            raise PermanentJobError()
        if type(payload) is not dict or set(payload) != {'schema', 'document_ref', 'sha256', 'pipeline_version'}:
            raise PermanentJobError()
        if type(payload['schema']) is not int or payload['schema'] != 1 or payload['pipeline_version'] != self.service.pipeline:
            raise PermanentJobError()
        digest = payload['sha256']
        if type(digest) is not str or not re.fullmatch('[0-9a-f]{64}', digest):
            raise PermanentJobError()
        if payload['document_ref'] != document_reference(scope, digest, self.service.pipeline):
            raise PermanentJobError()
        self.service.validate_scope(scope)
        data = self.service.documents.read(payload['document_ref'])
        if len(data) > MAX_BYTES or hashlib.sha256(data).hexdigest() != digest:
            raise PermanentJobError()
        summary = self.extract(data)
        if summary.status != 'ok':
            raise PermanentJobError()
        chunks = chunk_pages(summary.page_texts or (summary.text,), self.rag.settings.chunk_size,
                             self.rag.settings.chunk_overlap, max_chunks=MAX_CHUNKS)
        if not chunks:
            raise PermanentJobError()
        dimensions = None
        for start in range(0, len(chunks), self.batch_size):
            if context.should_stop:
                raise RetryableJobError()
            batch = chunks[start:start + self.batch_size]
            vectors = self.rag.embedder.embed_many([chunk.text for chunk in batch])
            if len(vectors) != len(batch):
                raise PermanentJobError()
            for vector in vectors:
                if not vector or any(not math.isfinite(value) for value in vector):
                    raise PermanentJobError()
                dimensions = dimensions or len(vector)
                if len(vector) != dimensions:
                    raise PermanentJobError()
            if context.should_stop:
                raise RetryableJobError()
            self.rag.store.upsert_ingestion(vector_scope(scope), digest, self.service.pipeline,
                                           payload['document_ref'], list(zip(batch, vectors, strict=True)))
        # Only the job repository's lease-fenced completion makes this generation ready.
        return {'schema': 1, 'document_ref': payload['document_ref'], 'status': 'complete',
                'chunk_count': len(chunks), 'vector_count': len(chunks), 'pipeline_version': self.service.pipeline}
