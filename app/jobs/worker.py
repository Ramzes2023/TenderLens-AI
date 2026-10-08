"""Explicit worker runtime. Importing this module never starts threads or opens storage."""
import threading
import time
import uuid
from dataclasses import dataclass

from .models import JobValueError


class RetryableJobError(Exception):
    """Retry with the repository's bounded deterministic backoff; message is never persisted."""


class PermanentJobError(Exception):
    """Fail immediately; message is never persisted."""


class ExecutionContext:
    def __init__(self, job, shutdown_event):
        self.job = job
        self.shutdown_requested = shutdown_event
        self.lease_lost = threading.Event()

    @property
    def should_stop(self):
        # Cancellation invalidates the lease and is detected by the next heartbeat.
        return self.shutdown_requested.is_set() or self.lease_lost.is_set()


class Worker:
    def __init__(self, repository, registry, *, stop_event=None, claim_lock=None, job_types=None):
        self.repository = repository
        self.registry = registry
        self.settings = repository.settings
        self.worker_id = 'worker-' + uuid.uuid4().hex
        self.stop_event = stop_event if stop_event is not None else threading.Event()
        self.claim_lock = claim_lock if claim_lock is not None else threading.Lock()
        self.job_types = job_types

    def run_once(self):
        # Admission occurs under this gate, before the database call. Shutdown
        # refuses subsequent admissions; an already admitted claim can finish.
        # Database transactions enforce cross-process claim correctness.
        with self.claim_lock:
            if self.stop_event.is_set():
                return False
            claim = (self.repository.claim_next(self.worker_id) if self.job_types is None
                     else self.repository.claim_next(self.worker_id, job_types=self.job_types))
        if claim is None:
            return False
        context = ExecutionContext(claim.job, self.stop_event)
        heartbeat_stop = threading.Event()

        def heartbeat_loop():
            while not heartbeat_stop.wait(self.settings.heartbeat_seconds):
                try:
                    owned = self.repository.heartbeat(claim.job.id, claim.token)
                except Exception:
                    owned = False  # Fail closed: uncertainty must not permit stale commits.
                if not owned:
                    context.lease_lost.set()
                    return

        heartbeat = threading.Thread(target=heartbeat_loop, name=self.worker_id + '-heartbeat', daemon=False)
        heartbeat.start()
        try:
            handler = self.registry.resolve(claim.job.job_type)
            if handler is None:
                self.repository.fail(claim.job.id, claim.token, code='unknown_type')
                return True
            try:
                result = handler(context, claim.job.payload)
            except RetryableJobError:
                if not context.lease_lost.is_set():
                    self.repository.fail(claim.job.id, claim.token, retryable=True)
            except PermanentJobError:
                if not context.lease_lost.is_set():
                    self.repository.fail(claim.job.id, claim.token, code='permanent_failure')
            except Exception:
                if not context.lease_lost.is_set():
                    self.repository.fail(claim.job.id, claim.token, code='handler_error')
            else:
                if not context.lease_lost.is_set():
                    try:
                        self.repository.complete(claim.job.id, claim.token, result)
                    except JobValueError:
                        self.repository.fail(claim.job.id, claim.token, code='invalid_result')
            return True
        finally:
            heartbeat_stop.set()
            heartbeat.join()

    def run(self):
        while not self.stop_event.is_set():
            try:
                worked = self.run_once()
            except Exception:
                # Durable lease recovery handles failed DB writes. No exception
                # payload, credentials or traceback is emitted by this foundation.
                worked = False
            if not worked:
                self.stop_event.wait(self.settings.poll_seconds)


@dataclass(frozen=True)
class ShutdownResult:
    completed: bool
    remaining_workers: int


class WorkerPool:
    def __init__(self, repository, registry):
        self.repository = repository
        self.registry = registry
        self._stop = threading.Event()
        self._claim_lock = threading.Lock()
        self._lifecycle_lock = threading.Lock()
        self._threads = []
        self._started = False

    @property
    def worker_count(self):
        return self.repository.settings.worker_count

    @property
    def alive_count(self):
        return sum(thread.is_alive() for thread in self._threads)

    def start(self):
        with self._lifecycle_lock:
            if self._stop.is_set():
                raise RuntimeError('Stopped worker pool cannot restart.')
            if self._started:
                return
            if not len(self.registry):
                raise RuntimeError('No job handlers registered.')
            self.registry.freeze()
            self._started = True
            try:
                for _ in range(self.worker_count):
                    worker = Worker(self.repository, self.registry, stop_event=self._stop, claim_lock=self._claim_lock,
                                    job_types=self.registry.job_types)
                    thread = threading.Thread(target=worker.run, name=worker.worker_id, daemon=False)
                    self._threads.append(thread)
                    thread.start()
            except BaseException:
                self._stop.set()
                raise

    def stop(self, timeout=None):
        timeout = self.repository.settings.shutdown_seconds if timeout is None else timeout
        if type(timeout) not in (int, float) or not 0 <= timeout <= 300:
            raise ValueError('Invalid worker shutdown timeout.')
        deadline = time.monotonic() + timeout
        with self._lifecycle_lock:
            # Set before waiting for any DB claim: timeout is bounded even if a
            # claim is in flight. That previously initiated claim may finish.
            self._stop.set()
            threads = tuple(self._threads)
        for thread in threads:
            if thread is not threading.current_thread():
                thread.join(max(0, deadline - time.monotonic()))
        remaining = self.alive_count
        return ShutdownResult(remaining == 0, remaining)


def main(argv=()):
    # Explicit opt-in preserves the safe no-handler invocation.
    flags = list(argv)
    if not flags or len(set(flags)) != len(flags) or any(flag not in {'--rag', '--connectors'} for flag in flags):
        print('VALYQON AI worker unavailable: no production job handlers selected; use --rag and/or --connectors.')
        return 2
    database = pool = None
    try:
        import signal
        from app.database.backend import Database
        from app.database.config import load_database_settings
        from app.jobs import HandlerRegistry, JobRepository, JobService, load_job_settings
        if '--rag' in flags:
            from app.rag.config import load_rag_settings
            from app.rag.service import RagService
            from app.rag.ingestion import JOB_TYPE, RagIngestionHandler, RagIngestionService, load_ingestion_options
            settings = load_rag_settings()
            if not settings.enabled:
                raise ValueError('RAG disabled.')
            documents, batch = load_ingestion_options()
            rag = RagService(settings)
        job_settings = load_job_settings()
        database = Database(load_database_settings())
        repository = JobRepository(database, job_settings)
        repository.initialize()
        registry = HandlerRegistry()
        if '--rag' in flags:
            service = RagIngestionService(JobService(repository), documents, settings)
            registry.register(JOB_TYPE, RagIngestionHandler(service, rag, batch_size=batch))
        if '--connectors' in flags:
            from app.monitoring.config import load_monitoring_settings
            from app.sources.catalog import build_source_catalog
            from app.sources.ingestion import JOB_TYPE as CONNECTOR_JOB_TYPE, ConnectorSyncHandler, load_max_records
            from app.sources.opportunities import OpportunityRepository
            catalog = build_source_catalog(load_monitoring_settings())
            opportunities = OpportunityRepository(database)
            opportunities.initialize()
            registry.register(CONNECTOR_JOB_TYPE, ConnectorSyncHandler(catalog, opportunities, max_records=load_max_records()))
        pool = WorkerPool(repository, registry)
        shutdown = threading.Event()
        def request_shutdown(signum, frame):
            shutdown.set()
        signal.signal(signal.SIGINT, request_shutdown)
        signal.signal(signal.SIGTERM, request_shutdown)
        pool.start()
        shutdown.wait()
        return 0
    except Exception:
        print('VALYQON AI worker startup/runtime failed; verify configuration.')
        return 2
    finally:
        # Do not close storage under a still-running handler after bounded shutdown.
        stopped = pool.stop().completed if pool is not None else True
        if database is not None and stopped:
            database.close()


if __name__ == '__main__':
    import sys
    raise SystemExit(main(sys.argv[1:]))
