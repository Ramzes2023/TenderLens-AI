"""Opt-in PostgreSQL 16 audit. No dotenv, providers, or existing DB writes; read-only exact-container Docker preflight.

Run with --confirm-local-test-server and VALYQON_PG_TEST_ADMIN_URL.
The URL must explicitly specify a numeric loopback host, port, user, password
and maintenance database postgres; query options and libpq services are rejected.
"""
from __future__ import annotations

import argparse
import ipaddress
import logging
import json
import subprocess
import multiprocessing
import os
from pathlib import Path
import re
import sys
import uuid
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
ENV = "VALYQON_PG_TEST_ADMIN_URL"
PREFIX = "valyqon_p24s2b3_test_"


class HarnessError(RuntimeError):
    """Only fixed, secret-free diagnostics may escape this boundary."""


def connection_parameters(value):
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != "postgresql" or parsed.path != "/postgres"
                or parsed.query or parsed.fragment or not parsed.username
                or not parsed.password or parsed.port is None or not 1 <= parsed.port <= 65535
                or not ipaddress.ip_address(parsed.hostname).is_loopback):
            raise ValueError
        return dict(host=str(ipaddress.ip_address(parsed.hostname)), port=parsed.port,
                    user=unquote(parsed.username), password=unquote(parsed.password),
                    dbname="postgres", connect_timeout=5, application_name="valyqon-p24s2b3-audit",
                    options="-c statement_timeout=15000 -c lock_timeout=10000")
    except Exception:
        raise HarnessError("Explicit numeric loopback test connection required.") from None


CONTAINER_ENV = "VALYQON_PG_TEST_CONTAINER_ID"


def docker_output(arguments):
    try:
        return subprocess.run(
            ["docker", "--host", "npipe:////./pipe/docker_engine"] + arguments,
            check=True, capture_output=True, text=True, timeout=15, shell=False).stdout
    except Exception:
        raise HarnessError("Exact test container verification failed.") from None


def verify_container(parameters, container_id):
    """Read only a full pinned ID on the local Windows Docker engine."""
    try:
        if (not re.fullmatch(r"[a-f0-9]{64}", container_id or "")
                or parameters["host"] != "127.0.0.1" or parameters["port"] != 64628):
            raise ValueError
        records = json.loads(docker_output(["container", "inspect", container_id]))
        if len(records) != 1:
            raise ValueError
        record = records[0]
        config, host, network = record["Config"], record["HostConfig"], record["NetworkSettings"]
        binding = {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "64628"}]}
        auto_binding = {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": ""}]}
        if (record["Id"] != container_id or record["State"]["Running"] is not True
                or record["State"].get("Restarting", False)
                or config["Labels"].get("valyqon.test") != "phase24s2b3"
                or config["Image"] != "postgres:16-alpine"
                or host["NetworkMode"] == "host"
                or host["NetworkMode"].startswith("container:")
                or host.get("Privileged", False) or host.get("PublishAllPorts", False)
                or host["PortBindings"] not in (binding, auto_binding)
                or network["Ports"] != binding):
            raise ValueError
        addresses = {str(ipaddress.ip_address(n["IPAddress"]))
                     for n in network["Networks"].values() if n.get("IPAddress")}
        if not addresses:
            raise ValueError
        control = docker_output(["exec", "--env", "LC_ALL=C", container_id,
                                 "pg_controldata", "/var/lib/postgresql/data"])
        identifiers = re.findall(r"^Database system identifier:\s+(\d+)\s*$", control, re.MULTILINE)
        versions = re.findall(r"^Catalog version number:\s+(\d+)\s*$", control, re.MULTILINE)
        if len(identifiers) != 1 or versions != ["202307071"]:
            raise ValueError
        return {"id": container_id, "addresses": addresses, "system_id": identifiers[0]}
    except Exception:
        raise HarnessError("Exact isolated PostgreSQL 16 container verification failed.") from None


def verify_server(conn, identity):
    row = conn.execute("SELECT host(inet_server_addr()), host(inet_client_addr()), "
                       "current_database(), current_setting('server_version_num')::int, "
                       "(SELECT system_identifier::text FROM pg_control_system())").fetchone()
    if (not row or row[2] != "postgres" or not 160000 <= row[3] < 170000
            or str(ipaddress.ip_address(row[0])) not in identity["addresses"]
            or ipaddress.ip_address(row[1]).is_unspecified
            or ipaddress.ip_address(row[1]).is_multicast
            or row[4] != identity["system_id"]):
        raise HarnessError("Pinned PostgreSQL 16 cluster verification failed.")


def drop_created_database(conn, name, oid, sql):
    # Never discover databases by prefix and never terminate unrelated sessions.
    if not re.fullmatch(PREFIX + r"[a-f0-9]{32}", name) or oid is None:
        raise HarnessError("Cleanup ownership verification failed.")
    row = conn.execute("SELECT oid FROM pg_database WHERE datname=%s", (name,)).fetchone()
    if row != (oid,):
        raise HarnessError("Cleanup identity verification failed.")
    conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def database_for_parameters(parameters):
    from psycopg.conninfo import make_conninfo
    from app.database.backend import Database
    from app.database.config import DatabaseSettings
    return Database(DatabaseSettings(make_conninfo(**parameters), None, "postgresql",
                                     pool_min=0, pool_max=12, pool_timeout=15))


def process_admission(parameters, values, gate, output, limits=(100, 100, 2)):
    """Spawn entry point: credentials travel in IPC, never argv or diagnostics."""
    logging.disable(logging.CRITICAL)
    database = None
    try:
        sys.path.insert(0, str(ROOT))
        from app.jobs import JobScope
        from app.quotas import Limits, QuotaSettings, QuotaExceeded
        from app.quotas.synchronous import SynchronousUsage
        database = database_for_parameters(parameters)
        service = SynchronousUsage(database, QuotaSettings(True, Limits(*limits)))
        output.put("ready")
        if not gate.wait(30):
            raise HarnessError("Process admission barrier timed out.")
        try:
            service.admit(JobScope(*values), "rag")
            output.put("accepted")
        except QuotaExceeded:
            output.put("denied")
    except BaseException:
        output.put("error")
    finally:
        if database is not None:
            database.close()


def run_audit(parameters):
    from tests.postgresql_phase24s2b3_cases import run_cases
    run_cases(parameters)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-local-test-server", action="store_true",
                        help="Attest this local PostgreSQL instance is for tests, not production.")
    args = parser.parse_args(argv)
    if sys.flags.optimize:
        print("REFUSED: Python optimization disables integration assertions.")
        return 2
    if not args.confirm_local_test_server:
        print("REFUSED: explicit local test server confirmation required.")
        return 2
    logging.disable(logging.CRITICAL)
    # Defense in depth for future application imports; never load a dotenv file.
    previous_dotenv_disabled = os.environ.get("PYTHON_DOTENV_DISABLED")
    try:
        os.environ["PYTHON_DOTENV_DISABLED"] = "1"
        admin = None
        created = False
        creation_attempted = False
        oid = None
        name = PREFIX + uuid.uuid4().hex
        result = 1
        try:
            parameters = connection_parameters(os.environ.get(ENV, ""))
            # No environment-derived service/host/password fallback in libpq.
            if any(key.startswith("PG") for key in os.environ):
                raise HarnessError("Remove ambient PG* variables before this isolated audit.")
            import psycopg
            import psycopg_pool  # Dependency preflight before creating resources.
            from psycopg import sql
            sys.path.insert(0, str(ROOT))
            identity = verify_container(parameters, os.environ.get(CONTAINER_ENV, ""))
            admin = psycopg.connect(**parameters, autocommit=True)
            verify_server(admin, identity)
            if verify_container(parameters, identity["id"]) != identity:
                raise HarnessError("Test container changed during verification.")
            creation_attempted = True
            admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(name)))
            created = True
            oid = admin.execute("SELECT oid FROM pg_database WHERE datname=%s", (name,)).fetchone()[0]
            test_parameters = dict(parameters, dbname=name)
            run_audit(test_parameters)
            result = 0
        except BaseException:
            # Driver exceptions, tracebacks and assertion representations can contain DSNs.
            print("FAIL: PostgreSQL audit incomplete; diagnostics intentionally redacted.")
        finally:
            if admin is not None:
                try:
                    if created:
                        drop_created_database(admin, name, oid, sql)
                        print("CLEANUP: isolated database removed.")
                    elif creation_attempted:
                        print("CREATE incomplete: inspect only possible test database " + name + ".")
                except BaseException:
                    result = 1
                    print("CLEANUP FAILED: inspect only test database " + name + ".")
                finally:
                    try:
                        admin.close()
                    except BaseException:
                        result = 1
                        print("FAIL: administrative connection shutdown failed.")
        if result == 0:
            print("PASS: PostgreSQL 16 integration audit and cleanup complete.")
        return result
    finally:
        if previous_dotenv_disabled is None:
            os.environ.pop("PYTHON_DOTENV_DISABLED", None)
        else:
            os.environ["PYTHON_DOTENV_DISABLED"] = previous_dotenv_disabled


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
