"""Real PostgreSQL 16 acceptance in a disposable GitHub Actions runner only.

Executes the existing Phase24 migration, quota, thread/process concurrency,
tenant-isolation and durable-job scenarios against one generated database.
Never reads a project .env or connects to production.
"""
from __future__ import annotations

import logging
import os
import re
import sys
import uuid

PREFIX = "valyqon_p24ci_"
MARKER = "valyqon-phase24-postgres16-ephemeral-ci-v1"


def main() -> int:
    if (
        sys.flags.optimize
        or os.environ.get("GITHUB_ACTIONS") != "true"
        or os.environ.get("GITHUB_REPOSITORY") != "Ramzes2023/TenderLens-AI"
        or os.environ.get("CI") != "true"
        or os.environ.get("VALYQON_PG_CI_CONTEXT") != MARKER
        or os.environ.get("PYTHON_DOTENV_DISABLED") != "1"
        or os.environ.get("VALYQON_DATABASE_REQUIRE_POSTGRES") != "true"
    ):
        print("PG_CI=REFUSED: ephemeral GitHub runner and explicit opt-in required")
        return 2

    user = "valyqon_ci"
    password = os.environ.get("VALYQON_PG_CI_TEST_PASSWORD", "")
    if password != "only-for-disposable-github-postgres16-ci":
        print("PG_CI=REFUSED: test-only service identity mismatch")
        return 2
    if any(key.startswith("PG") for key in os.environ):
        print("PG_CI=REFUSED: inherited libpq overrides")
        return 2

    # Running a scripts/*.py file sets sys.path[0] to scripts/, not repo root.
    # Keep imports anchored to this exact checked-out repository.
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    if not (root / "tests" / "postgresql_phase24s2b3_cases.py").is_file():
        print("PG_CI=REFUSED: expected in-repository integration cases missing")
        return 2
    sys.path.insert(0, str(root))
    from psycopg import connect, sql
    from tests.postgresql_phase24s2b3_cases import run_cases

    logging.disable(logging.CRITICAL)
    params = dict(
        host="127.0.0.1",
        port=5432,
        user=user,
        password=password,
        dbname="postgres",
        connect_timeout=5,
        application_name="valyqon-p24-ephemeral-ci",
        options="-c statement_timeout=30000 -c lock_timeout=15000",
    )
    database = PREFIX + uuid.uuid4().hex
    created = False
    db_oid = None
    success = False
    cleanup_ok = False
    connection = None
    try:
        connection = connect(**params, autocommit=True)
        row = connection.execute(
            "SELECT current_user, current_database(), "
            "current_setting('server_version_num')::int, "
            "host(inet_client_addr()), inet_server_port(), "
            "(SELECT system_identifier::text FROM pg_control_system())"
        ).fetchone()
        if (
            not row or row[0] != user or row[1] != "postgres"
            or not 160000 <= row[2] < 170000 or row[3] is None
            or row[4] != 5432 or not re.fullmatch(r"[0-9]+", row[5] or "")
        ):
            raise RuntimeError("Unrecognized test service identity")
        print("PG_CI=POSTGRES16_IDENTITY_VERIFIED")
        connection.execute(
            sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(database))
        )
        created = True
        found = connection.execute(
            "SELECT oid FROM pg_database WHERE datname=%s", (database,)
        ).fetchone()
        if not found or not isinstance(found[0], int):
            raise RuntimeError("Test database identity missing")
        db_oid = found[0]
        print("PG_CI=ISOLATED_DATABASE_CREATED")
        run_cases({**params, "dbname": database})
        success = True
    except BaseException:
        # Driver exception text can expose connection information. Fixed output only.
        print("PG_CI=FAILED: inspect safe stage markers, not exception details")
    finally:
        if connection is not None:
            try:
                if created:
                    if not re.fullmatch(PREFIX + r"[a-f0-9]{32}", database):
                        raise RuntimeError("Owned database name guard")
                    existing = connection.execute(
                        "SELECT oid FROM pg_database WHERE datname=%s", (database,)
                    ).fetchone()
                    if db_oid is None or existing != (db_oid,):
                        raise RuntimeError("Owned database OID guard")
                    connection.execute(
                        sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database))
                    )
                    if connection.execute(
                        "SELECT 1 FROM pg_database WHERE datname=%s", (database,)
                    ).fetchone() is not None:
                        raise RuntimeError("Owned database not removed")
                    print("PG_CI=OWNED_DATABASE_REMOVED")
                cleanup_ok = True
            except BaseException:
                print("PG_CI=CLEANUP_FAILED: a disposable CI database may remain")
            finally:
                try:
                    connection.close()
                except BaseException:
                    cleanup_ok = False
                    print("PG_CI=CONNECTION_CLOSE_FAILED")
    if success and cleanup_ok:
        print("PHASE24_REAL_POSTGRESQL_16=PASS")
        return 0
    print("PHASE24_REAL_POSTGRESQL_16=FAIL")
    return 1


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    raise SystemExit(main())
