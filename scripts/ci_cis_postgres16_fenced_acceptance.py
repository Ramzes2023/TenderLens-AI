"""PostgreSQL 16 gate for real fenced CIS connector storage.

Runs ONLY against a verified ephemeral GitHub Actions PostgreSQL 16 service.
Creates a unique owned database, runs real migration/worker/fencing checks,
and destroys that database. No production credentials, environment files,
HTTP transport, AI provider or deployed services are accessed.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import secrets
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

CONTEXT = "valyqon-cis-postgres16-ephemeral-ci-v1"
PASSWORD = "only-for-disposable-github-cis16"
PREFIX = "valyqon_cisci_"


def check_environment():
    return (
        sys.flags.optimize == 0
        and os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("GITHUB_REPOSITORY") == "Ramzes2023/TenderLens-AI"
        and os.environ.get("CI") == "true"
        and os.environ.get("PYTHON_DOTENV_DISABLED") == "1"
        and os.environ.get("VALYQON_DATABASE_REQUIRE_POSTGRES") == "true"
        and os.environ.get("VALYQON_CIS_PG16_CONTEXT") == CONTEXT
        and os.environ.get("VALYQON_CIS_PG16_PASSWORD") == PASSWORD
        and not any(key.startswith("PG") for key in os.environ)
    )


def run_acceptance(database_url):
    from app.database.backend import Database
    from app.database.config import parse_database_settings
    from app.jobs import HandlerRegistry, JobRepository, JobService
    from app.jobs.config import JobSettings
    from app.jobs.models import LeaseLostError
    from app.jobs.worker import Worker
    from app.sources.catalog import SourceCatalog
    from app.sources.ingestion import (
        ConnectorSyncHandler, ConnectorSyncService, JOB_TYPE, SYSTEM_SCOPE,
        connector_version,
    )
    from app.sources.models import TenderNotice
    from app.sources.multi import MultiSourceFetcher
    from app.sources.opportunities import OpportunityRepository
    from app.sources.registry import SourceRegistration, SourceRegistry
    from app.sources.snapshots import snapshot_catalog

    db = Database(parse_database_settings(database_url, require_postgres=True,
                                          pool_min=1, pool_max=5, pool_timeout=10))

    from dataclasses import dataclass

    @dataclass(frozen=True)
    class LocalFixtureSource:
        name: str
        host: str
        max_pages: int = 2

        async def fetch(self, limit=20):
            return [TenderNotice(
                self.name, "123456789", "Test Pump Насос Equipment",
                f"https://{self.host}/public/item/123456789",
                deadline="2026-12-31T12:00:00",
            )][:limit]

    originals = {
        "am_armeps": "eauction.armeps.am",
        "tj_eprocurement": "eprocurement.gov.tj",
    }

    try:
        print("CIS_PG16_STAGE=JOBS_MIGRATION", flush=True)
        jobs = JobRepository(db)
        jobs.initialize()
        print("CIS_PG16_STAGE=OPPORTUNITIES_MIGRATION", flush=True)
        store = OpportunityRepository(db)
        store.initialize()
        registry = SourceRegistry(
            SourceRegistration(
                key, key, LocalFixtureSource(key, host), official=True,
            )
            for key, host in originals.items()
        )
        catalog = SourceCatalog(registry, MultiSourceFetcher(registry, concurrency=1))
        print("CIS_PG16_STAGE=CONNECTOR_CATALOG", flush=True)
        service = ConnectorSyncService(JobService(jobs), catalog)
        handlers = HandlerRegistry()
        handlers.register(JOB_TYPE, ConnectorSyncHandler(catalog, store, max_records=20))

        # Real registered Worker, PostgreSQL durable queue, real migrations and
        # per-notice fenced SQL, independent connections for saved searches.
        for source in originals:
            print("CIS_PG16_STAGE=WORKER_" + source.upper(), flush=True)
            claimable = service.enqueue(source)
            if not Worker(jobs, handlers, job_types=(JOB_TYPE,)).run_once():
                raise AssertionError("Worker failed to claim")
            end = jobs.get(claimable.id, scope=SYSTEM_SCOPE)
            if end is None or end.state != "succeeded" or end.result["accepted_count"] != 1:
                raise AssertionError("Durable connector did not succeed")
            persisted = store.read(source, 10)
            if len(persisted) != 1 or persisted[0].identity != (source, "123456789"):
                raise AssertionError("Missing persisted notice")
            result = asyncio.run(snapshot_catalog(catalog, store).fetch(
                source_keys=(source,), limit_per_source=10, search_terms=("Pump",),
            ))
            if len(result.notices) != 1 or result.notices[0].identity != persisted[0].identity:
                raise AssertionError("PostgreSQL saved-search mismatch")
            print("CIS_PG16_" + source.upper() + "=FENCED_STORED_AND_SEARCHABLE")

        # Two independent PostgreSQL connections compete for a single queued
        # connector job. The single global connector lane must allow only one.
        print("CIS_PG16_STAGE=CONCURRENT_CLAIM", flush=True)
        concurrent_job = service.enqueue(
            "tj_eprocurement", now=datetime.now(timezone.utc) + timedelta(hours=3))

        def compete(_index):
            independent_jobs = JobRepository(db)
            return independent_jobs.claim_next(
                "worker-" + uuid.uuid4().hex, job_types=(JOB_TYPE,))

        with ThreadPoolExecutor(max_workers=2) as executor:
            claims = list(executor.map(compete, range(2)))
        winners = [claim for claim in claims if claim is not None]
        if len(winners) != 1 or winners[0].job.id != concurrent_job.id:
            raise AssertionError("Connector lane allowed duplicate worker claims")
        if not jobs.fail(winners[0].job.id, winners[0].token,
                         retryable=False, code="permanent_failure"):
            raise AssertionError("Unable to close claimed concurrency probe")
        print("CIS_PG16_CONCURRENT_CLAIM=ONE_WINNER", flush=True)

        # Real authoritative DB time: un-heartbeated old claim expires and
        # another connection/worker takes over. Old token cannot overwrite.
        print("CIS_PG16_STAGE=STALE_LEASE_TEST", flush=True)
        rapid = JobRepository(db, JobSettings(lease_seconds=0.8, heartbeat_seconds=0.1))
        next_slot = datetime.now(timezone.utc) + timedelta(hours=2)
        job = ConnectorSyncService(JobService(rapid), catalog).enqueue("am_armeps", now=next_slot)
        old = rapid.claim_next("worker-" + uuid.uuid4().hex, job_types=(JOB_TYPE,))
        if old is None or old.job.id != job.id:
            raise AssertionError("No initial lease")
        time.sleep(1.2)
        fresh = rapid.claim_next("worker-" + uuid.uuid4().hex, job_types=(JOB_TYPE,))
        if fresh is None or fresh.job.id != old.job.id or fresh.token == old.token:
            raise AssertionError("Expired job was not reclaimed")
        current = TenderNotice("am_armeps", "123456789", "Fresh Pump correct",
                               "https://eauction.armeps.am/public/item/123456789")
        stale = TenderNotice("am_armeps", "123456789", "Stale Pump wrong",
                             "https://eauction.armeps.am/public/item/123456789")
        from_old = lambda write: rapid.fenced_write(old.job.id, old.token, write)
        from_fresh = lambda write: rapid.fenced_write(fresh.job.id, fresh.token, write)
        if store.upsert_fenced(current, connector_version("am_armeps"), from_fresh) is not False:
            raise AssertionError("Expected existing notice to be updated")
        try:
            store.upsert_fenced(stale, connector_version("am_armeps"), from_old)
        except LeaseLostError:
            pass
        else:
            raise AssertionError("Expired connector worker overwrote notice")
        if store.read("am_armeps", 10)[0].title != "Fresh Pump correct":
            raise AssertionError("Stale worker corruption")

        # Mid-write expiration must reject the transaction and roll back the
        # persisted row. A synthetic RuntimeError does not prove expiry fencing.
        print("CIS_PG16_STAGE=EXPIRY_ROLLBACK", flush=True)
        if not rapid.heartbeat(fresh.job.id, fresh.token):
            raise AssertionError("Fresh worker lease expired before rollback test")

        def delayed_write(conn, _now):
            store._write_prepared(conn, *store._prepare_upsert(
                TenderNotice("am_armeps", "rollback-probe", "Rollback Pump",
                             "https://eauction.armeps.am/public/item/rollback-probe"),
                connector_version("am_armeps"),
            ), connector_version("am_armeps"))
            # The live PostgreSQL server clock advances while this transaction
            # holds its lease row lock. Repo post-write lease check must abort.
            time.sleep(1.1)

        try:
            from_fresh(delayed_write)
        except LeaseLostError:
            pass
        else:
            raise AssertionError("Expired fenced transaction unexpectedly committed")
        if any(n.external_id == "rollback-probe" for n in store.read("am_armeps", 20)):
            raise AssertionError("Expired fenced write did not roll back")
        print("CIS_PG16_STALE_LEASE=REJECTED")
        print("CIS_PG16_EXPIRY_ROLLBACK=VERIFIED")
    finally:
        db.close()


def main():
    if not check_environment():
        print("CIS_PG16=REFUSED: must use disposable GitHub PostgreSQL 16 service")
        return 2
    from psycopg import connect, sql
    logging.disable(logging.CRITICAL)
    args = dict(
        host="127.0.0.1", port=5432, dbname="postgres", user="valyqon_ci",
        password=PASSWORD, connect_timeout=5,
        application_name="valyqon-cis-pg16-ci",
        options="-c statement_timeout=30000 -c lock_timeout=15000",
    )
    database = PREFIX + uuid.uuid4().hex
    created = False
    oid = None
    complete = False
    cleaned = False
    connection = None
    try:
        connection = connect(**args, autocommit=True)
        identity = connection.execute(
            "SELECT current_user,current_database(),current_setting('server_version_num')::int,"
            "host(inet_client_addr()), inet_server_port(),"
            "(SELECT system_identifier::text FROM pg_control_system())"
        ).fetchone()
        if (not identity or identity[0] != "valyqon_ci" or identity[1] != "postgres"
                or not 160000 <= identity[2] < 170000 or identity[3] != "127.0.0.1"
                or identity[4] != 5432 or not re.fullmatch(r"[0-9]+", identity[5] or "")):
            raise RuntimeError("Unrecognized disposable PostgreSQL service")
        print("CIS_PG16=SERVER_IDENTITY_VERIFIED")
        connection.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(database)))
        created = True
        oid = connection.execute("SELECT oid FROM pg_database WHERE datname=%s", (database,)).fetchone()[0]
        import urllib.parse
        url = "postgresql://valyqon_ci:" + urllib.parse.quote(PASSWORD, safe="") + "@127.0.0.1:5432/" + database
        run_acceptance(url)
        complete = True
    except BaseException as exc:
        # no DSN, upstream request, stored payload or raw database exceptions in logs
        print("CIS_PG16=FAILED; FAILURE_TYPE=" + type(exc).__name__)
    finally:
        if connection is not None:
            try:
                if created:
                    if not re.fullmatch(PREFIX + r"[a-f0-9]{32}", database):
                        raise RuntimeError("Database ownership check failed")
                    found = connection.execute(
                        "SELECT oid FROM pg_database WHERE datname=%s", (database,)
                    ).fetchone()
                    if found != (oid,):
                        raise RuntimeError("Database identity mismatch")
                    connection.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))
                    print("CIS_PG16=OWNED_DATABASE_DESTROYED")
                cleaned = True
            except BaseException:
                print("CIS_PG16=CLEANUP_FAILED")
            finally:
                connection.close()
    if complete and cleaned:
        print("CIS_PG16_ACCEPTANCE=PASS")
        return 0
    print("CIS_PG16_ACCEPTANCE=FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
