"""Exercise a real connector worker job, durable claim and fenced SQL writes.

This reusable acceptance helper never fabricates a lease. Each caller must own
a disposable database and an explicitly configured public source catalog.
"""
from app.jobs import HandlerRegistry, JobRepository, JobSettings
from app.jobs.models import JobScope
from app.jobs.worker import Worker
from app.sources.ingestion import ConnectorSyncHandler, ConnectorSyncService, JOB_TYPE


def run_leased_connector(db, catalog, opportunities, source_id, *, max_records):
    jobs = JobRepository(db, JobSettings(lease_seconds=240, heartbeat_seconds=10))
    jobs.initialize()
    queued = ConnectorSyncService(jobs, catalog).enqueue(source_id)
    handlers = HandlerRegistry()
    handlers.register(JOB_TYPE, ConnectorSyncHandler(catalog, opportunities, max_records=max_records))
    if not Worker(jobs, handlers, job_types=(JOB_TYPE,)).run_once():
        raise AssertionError("No real durable connector job was claimed")
    completed = jobs.get(queued.id, scope=JobScope())
    if completed is None or completed.state != "succeeded" or type(completed.result) is not dict:
        raise AssertionError("Durable connector job did not succeed: " +
                             str(completed.failure_code if completed else "job missing"))
    if completed.result.get("source_id") != source_id:
        raise AssertionError("Durable connector result source mismatch")
    return completed.result
