"""Real disposable PostgreSQL-16 pg_dump/pg_restore rehearsal in GitHub Actions.

Tests schema plus two synthetic tenants. Archive restore is to a DIFFERENT empty
database. No production credentials, public sources or existing databases.
All command diagnostics are redacted; the two owned databases are removed.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from contextlib import closing


PREFIX = "valyqon_restoreci_"
PASSWORD = "only-for-disposable-github-postgres16-ci"
MARKER = "valyqon-phase24-postgres16-ephemeral-ci-v1"


def _run_docker(container_id, args, *, data=None):
    try:
        result = subprocess.run(["docker", "exec", "-i", container_id, *args],
                                input=data, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=90, check=False)
    except Exception:
        raise RuntimeError("PostgreSQL archive command unavailable") from None
    if result.returncode:
        raise RuntimeError("PostgreSQL archive command failed")
    return result.stdout


def _snapshot(database):
    """Compare actual identity, authorization, queue and schema content."""
    tables = ("app_schema_migrations", "auth_accounts", "organizations",
              "organization_members", "durable_jobs", "source_opportunities",
              "quota_admissions", "synchronous_usage")
    result = {}
    with closing(database.connect()) as conn:
        for table in tables:
            # Static allowlisted table names only; never interpolate a user value.
            rows = conn.execute("SELECT * FROM " + table).fetchall()
            canonical = [dict(row) for row in rows]
            stable = sorted(json.dumps(item, ensure_ascii=True, sort_keys=True,
                                       separators=(",", ":"), default=str)
                            for item in canonical)
            result[table] = (len(stable), hashlib.sha256(
                ("\n".join(stable)).encode("utf-8")).hexdigest())
    return result


def _database(params, name):
    from app.database.backend import Database
    from app.database.config import DatabaseSettings
    from psycopg.conninfo import make_conninfo
    return Database(DatabaseSettings(make_conninfo(**{**params, "dbname": name}),
                                     None, "postgresql", pool_min=0, pool_max=8,
                                     pool_timeout=10))


def _seed(database):
    from app.auth import AuthRepository
    from app.organizations import OrganizationRepository
    from app.jobs import JobRepository, JobScope
    from app.quotas import Limits, QuotaSettings
    from app.quotas.synchronous import SynchronousUsage
    database.migrate()
    users = []
    for i in range(2):
        user = AuthRepository(database).create_account(
            "restore-" + uuid.uuid4().hex + "@example.test", "synthetic-only")
        organization = OrganizationRepository(database).default_for_account(user.id)
        scope = JobScope(user.id, organization.id)
        job = JobRepository(database).enqueue("fixture.restore", {"synthetic": i}, scope=scope)
        assert job.id
        usage = SynchronousUsage(database, QuotaSettings(True, Limits(100, 100, 4)))
        assert usage.finish(usage.admit(scope, "rag"))
        users.append((user.id, organization.id))
    assert users[0] != users[1]
    with closing(database.connect()) as conn:
        assert conn.execute("SELECT COUNT(*) FROM auth_accounts").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM durable_jobs").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM app_schema_migrations").fetchone()[0] == 19
    print("RESTORE_DRILL=TWO_SYNTHETIC_TENANTS_SEEDED")


def main() -> int:
    if (sys.flags.optimize or os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("GITHUB_REPOSITORY") != "Ramzes2023/TenderLens-AI"
            or os.environ.get("CI") != "true"
            or os.environ.get("PYTHON_DOTENV_DISABLED") != "1"
            or os.environ.get("VALYQON_PG_CI_CONTEXT") != MARKER
            or os.environ.get("VALYQON_PG_CI_TEST_PASSWORD") != PASSWORD):
        print("RESTORE_DRILL=REFUSED: explicit isolated CI context required")
        return 2
    container_id = os.environ.get("VALYQON_PG_RESTORE_CONTAINER_ID", "")
    if not re.fullmatch(r"[a-f0-9]{64}", container_id):
        print("RESTORE_DRILL=REFUSED: pinned ephemeral service ID absent")
        return 2
    try:
        check = subprocess.run(["docker", "inspect", "--format",
                                "{{.Config.Image}}|{{.State.Running}}", container_id],
                               capture_output=True, text=True, timeout=10, check=True).stdout.strip()
        if check != "postgres:16-alpine|true":
            raise ValueError
    except Exception:
        print("RESTORE_DRILL=REFUSED: unverified PostgreSQL service container")
        return 2
    if any(key.startswith("PG") for key in os.environ):
        print("RESTORE_DRILL=REFUSED: inherited libpq settings")
        return 2
    # scripts/*.py executes with scripts/ on sys.path; add the exact repo root.
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    if not (root / "app" / "database" / "backend.py").is_file():
        print("RESTORE_DRILL=REFUSED: project root not verified")
        return 2
    sys.path.insert(0, str(root))
    from psycopg import connect, sql

    params = dict(host="127.0.0.1", port=5432, dbname="postgres", user="valyqon_ci",
                  password=PASSWORD, connect_timeout=5, application_name="valyqon-restore-drill",
                  options="-c statement_timeout=30000 -c lock_timeout=15000")
    conn = None
    owned = {}
    succeeded = False
    stage = "connect"
    cleanup = True
    try:
        conn = connect(**params, autocommit=True)
        identity = conn.execute(
            "SELECT current_user, current_database(), current_setting('server_version_num')::int"
        ).fetchone()
        if identity[0:2] != ("valyqon_ci", "postgres") or not 160000 <= identity[2] < 170000:
            raise RuntimeError("Unexpected disposable service identity")
        source_name = PREFIX + uuid.uuid4().hex
        restore_name = PREFIX + uuid.uuid4().hex
        stage = "create_test_databases"
        for name in (source_name, restore_name):
            conn.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(name)))
            row = conn.execute("SELECT oid FROM pg_database WHERE datname=%s", (name,)).fetchone()
            if row is None:
                raise RuntimeError("Created database lost")
            owned[name] = row[0]
        stage = "seed_source"
        source = _database(params, source_name)
        try:
            _seed(source)
            source_snapshot = _snapshot(source)
        finally:
            source.close()
        print("RESTORE_DRILL=SOURCE_MIGRATIONS_AND_DATA_VERIFIED")
        stage = "archive"
        archive = _run_docker(container_id, [
            "pg_dump", "-U", "valyqon_ci", "-d", source_name, "--format=custom",
            "--no-owner", "--no-acl", "--compress=6",
        ])
        if len(archive) < 1000 or len(archive) > 20 * 1024 * 1024 or not archive.startswith(b"PGDMP"):
            raise RuntimeError("Invalid or oversized PG custom archive")
        digest = hashlib.sha256(archive).hexdigest()
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise RuntimeError("Archive hash invalid")
        print("RESTORE_DRILL=PG_DUMP_CUSTOM_ARCHIVE_SHA256_VERIFIED")
        stage = "restore_archive"
        _run_docker(container_id, [
            "pg_restore", "-U", "valyqon_ci", "-d", restore_name,
            "--single-transaction", "--exit-on-error", "--no-owner", "--no-acl",
        ], data=archive)
        stage = "verify_restored"
        restored = _database(params, restore_name)
        try:
            assert _snapshot(restored) == source_snapshot
            from app.auth import AuthRepository
            from app.organizations import OrganizationRepository
            new = AuthRepository(restored).create_account(
                "restored-" + uuid.uuid4().hex + "@example.test", "synthetic-only")
            org = OrganizationRepository(restored).default_for_account(new.id)
            assert org.id
        finally:
            restored.close()
        print("RESTORE_DRILL=RESTORED_SCHEMA_TENANTS_QUOTAS_JOBS_AND_WRITE_VERIFIED")
        succeeded = True
    except BaseException:
        print("RESTORE_DRILL=FAILED_STAGE:" + stage + "; DETAILS_REDACTED")
    finally:
        if conn is not None:
            for name, oid in reversed(list(owned.items())):
                try:
                    if not re.fullmatch(PREFIX + r"[0-9a-f]{32}", name):
                        raise RuntimeError
                    row = conn.execute("SELECT oid FROM pg_database WHERE datname=%s",
                                       (name,)).fetchone()
                    if row != (oid,):
                        raise RuntimeError
                    conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
                        sql.Identifier(name)))
                    if conn.execute("SELECT oid FROM pg_database WHERE datname=%s",
                                    (name,)).fetchone():
                        raise RuntimeError
                except BaseException:
                    cleanup = False
            try:
                conn.close()
            except BaseException:
                cleanup = False
        print("RESTORE_DRILL=OWNED_DATABASES_REMOVED" if cleanup
              else "RESTORE_DRILL=CLEANUP_FAILED")
    if succeeded and cleanup and len(owned) == 2:
        print("PHASE24_POSTGRES16_BACKUP_RESTORE=PASS")
        return 0
    print("PHASE24_POSTGRES16_BACKUP_RESTORE=FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
