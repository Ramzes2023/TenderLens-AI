"""Offline guard, lifecycle and redaction contracts. Never opens a DB socket."""
from contextlib import closing
import logging
import os
from types import SimpleNamespace
from unittest.mock import MagicMock
import sys

import pytest

from scripts import validate_phase24s2b3_postgresql as harness

IDENTITY = {"id": "a" * 64, "addresses": {"127.0.0.1"}, "system_id": "123"}

URL = "postgresql://synthetic:synthetic-secret@127.0.0.1:5432/postgres"


@pytest.fixture(autouse=True)
def restore_logging():
    original = logging.root.manager.disable
    yield
    logging.disable(original)


@pytest.mark.parametrize("value", ["", "postgresql://u:p@localhost:5432/postgres",
    "postgresql://u:p@192.168.0.1:5432/postgres", "postgresql://u:p@127.0.0.1/postgres",
    "postgresql://u:p@127.0.0.1:0/postgres", "postgresql://u:p@127.0.0.1:65536/postgres",
    "postgresql://u:p@127.0.0.1:5432/production", "postgresql://u:p@127.0.0.1:5432/postgres?host=remote",
    "postgresql://u:p@127.0.0.1:5432/postgres?service=production",
    "postgresql://u:p@127.0.0.1:5432/postgres#secret", "postgresql://u@127.0.0.1:5432/postgres",
    "host=127.0.0.1 password=synthetic-secret", "postgresql://u:p@[::ffff:192.168.0.1]:5432/postgres"])
def test_reject_ambiguous_or_nonlocal_connection(value):
    with pytest.raises(harness.HarnessError) as caught:
        harness.connection_parameters(value)
    assert value not in str(caught.value) if value else True
    assert "synthetic-secret" not in str(caught.value)


@pytest.mark.parametrize("host", ["127.0.0.1", "[::1]"])
def test_explicit_loopback_parameters(host):
    params = harness.connection_parameters(f"postgresql://u:p%40ss@{host}:5432/postgres")
    assert params["password"] == "p@ss" and params["dbname"] == "postgres"
    assert params["host"] in {"127.0.0.1", "::1"}


@pytest.mark.parametrize("row", [("127.0.0.1", "127.0.0.1", "postgres", 150000),
    ("127.0.0.1", "127.0.0.1", "postgres", 170000),
    ("10.0.0.1", "127.0.0.1", "postgres", 160001),
    ("127.0.0.1", "0.0.0.0", "postgres", 160001),
    ("127.0.0.1", "127.0.0.1", "production", 160001),
    ("127.0.0.2", "127.0.0.1", "postgres", 160001)])
def test_server_identity_rejected(row):
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = row + ("123",)
    with pytest.raises(harness.HarnessError):
        harness.verify_server(conn, IDENTITY)


def test_server_identity_verified():
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = ("127.0.0.1", "127.0.0.1", "postgres", 160010, "123")
    harness.verify_server(conn, IDENTITY)


def test_server_address_sql_returns_plain_ips():
    """inet::text includes /32; host(inet) supplies ip_address-compatible IPs."""
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = (
        "172.17.0.2", "192.168.65.1", "postgres", 160010, "123")
    harness.verify_server(conn, dict(IDENTITY, addresses={"172.17.0.2"}))
    conn.execute.assert_called_once_with(
        "SELECT host(inet_server_addr()), host(inet_client_addr()), "
        "current_database(), current_setting('server_version_num')::int, "
        "(SELECT system_identifier::text FROM pg_control_system())")


@pytest.mark.parametrize("name,oid,stored", [("postgres", 42, (42,)),
    (harness.PREFIX + "a" * 32, None, (42,)),
    (harness.PREFIX + "a" * 32, 42, (43,)),
    (harness.PREFIX + "a" * 32, 42, None)])
def test_cleanup_never_drops_unowned_database(name, oid, stored):
    conn, sql = MagicMock(), MagicMock()
    conn.execute.return_value.fetchone.return_value = stored
    with pytest.raises(harness.HarnessError):
        harness.drop_created_database(conn, name, oid, sql)
    assert not sql.SQL.called


def fake_driver(monkeypatch):
    for key in list(__import__("os").environ):
        if key.startswith("PG"):
            monkeypatch.delenv(key)
    monkeypatch.setenv(harness.ENV, URL)
    monkeypatch.setattr(harness, "verify_container", MagicMock(return_value=IDENTITY))
    conn = MagicMock()
    def execute(query, params=None):
        cursor = MagicMock()
        cursor.fetchone.return_value = (("127.0.0.1", "127.0.0.1", "postgres", 160001, "123")
                                       if "inet_server_addr" in str(query) else (42,))
        return cursor
    conn.execute.side_effect = execute
    driver = SimpleNamespace(connect=MagicMock(return_value=conn), sql=MagicMock())
    monkeypatch.setitem(sys.modules, "psycopg", driver)
    monkeypatch.setitem(sys.modules, "psycopg_pool", SimpleNamespace())
    return conn, driver


def test_missing_optin_never_connects(monkeypatch, capsys):
    _, driver = fake_driver(monkeypatch)
    assert harness.main([]) == 2
    assert not driver.connect.called
    assert "synthetic-secret" not in capsys.readouterr().out


def test_missing_env_and_ambient_libpq_refused(monkeypatch):
    _, driver = fake_driver(monkeypatch)
    monkeypatch.delenv(harness.ENV)
    assert harness.main(["--confirm-local-test-server"]) == 1
    monkeypatch.setenv(harness.ENV, URL)
    monkeypatch.setenv("PGSERVICE", "synthetic")
    assert harness.main(["--confirm-local-test-server"]) == 1
    assert not driver.connect.called


@pytest.mark.parametrize("failure", [False, True])
def test_success_and_failed_audit_cleanup_without_secret_output(monkeypatch, capsys, failure):
    conn, driver = fake_driver(monkeypatch)
    audit = MagicMock(side_effect=RuntimeError(URL) if failure else None)
    monkeypatch.setattr(harness, "run_audit", audit)
    assert harness.main(["--confirm-local-test-server"]) == (1 if failure else 0)
    assert audit.call_count == 1 and conn.close.call_count == 1
    name = audit.call_args.args[0]["dbname"]
    assert name.startswith(harness.PREFIX) and name != "postgres"
    assert driver.sql.SQL.call_count == 2  # CREATE and owned DROP only
    output = capsys.readouterr().out
    assert URL not in output and "synthetic-secret" not in output
    assert "CLEANUP: isolated database removed." in output
    assert ("PASS: PostgreSQL 16" in output) is (not failure)



@pytest.mark.parametrize("previous", [None, "", "0", "1", "custom"])
@pytest.mark.parametrize("failure", [None, "preflight", "audit", "cleanup", "close", "setup"])
def test_dotenv_disabled_through_audit_and_restored(monkeypatch, previous, failure):
    conn, _driver = fake_driver(monkeypatch)
    if previous is None:
        monkeypatch.delenv("PYTHON_DOTENV_DISABLED", raising=False)
    else:
        monkeypatch.setenv("PYTHON_DOTENV_DISABLED", previous)

    stages = []

    def stage(name):
        def check(*args, **kwargs):
            assert os.environ["PYTHON_DOTENV_DISABLED"] == "1"
            stages.append(name)
            if failure == name:
                raise KeyboardInterrupt("synthetic")
            if name == "preflight":
                return IDENTITY
        return check

    monkeypatch.setattr(harness, "verify_container", stage("preflight"))
    monkeypatch.setattr(harness, "run_audit", stage("audit"))
    monkeypatch.setattr(harness, "drop_created_database", stage("cleanup"))
    conn.close.side_effect = stage("close")
    if failure == "setup":
        monkeypatch.setattr(harness.uuid, "uuid4", stage("setup"))
        with pytest.raises(KeyboardInterrupt):
            harness.main(["--confirm-local-test-server"])
    else:
        assert harness.main(["--confirm-local-test-server"]) == (0 if failure is None else 1)
        assert stages == (["preflight"] if failure == "preflight" else
                          ["preflight", "preflight", "audit", "cleanup", "close"])
    assert os.environ.get("PYTHON_DOTENV_DISABLED") == previous
    assert ("PYTHON_DOTENV_DISABLED" in os.environ) is (previous is not None)


def test_cleanup_failure_is_failure_even_after_success(monkeypatch, capsys):
    _, _driver = fake_driver(monkeypatch)
    monkeypatch.setattr(harness, "run_audit", MagicMock())
    monkeypatch.setattr(harness, "drop_created_database", MagicMock(side_effect=RuntimeError(URL)))
    assert harness.main(["--confirm-local-test-server"]) == 1
    output = capsys.readouterr().out
    assert "CLEANUP FAILED" in output and URL not in output and "PASS: PostgreSQL 16" not in output


def test_creation_failure_does_not_drop_existing_resources(monkeypatch):
    conn, driver = fake_driver(monkeypatch)
    monkeypatch.setattr(harness, "verify_server", MagicMock())
    conn.execute.side_effect = RuntimeError(URL)
    assert harness.main(["--confirm-local-test-server"]) == 1
    assert driver.sql.SQL.call_count == 1 and conn.close.called


def test_server_verification_failure_prevents_creation(monkeypatch):
    conn, driver = fake_driver(monkeypatch)
    monkeypatch.setattr(harness, "verify_server", MagicMock(side_effect=harness.HarnessError("synthetic")))
    assert harness.main(["--confirm-local-test-server"]) == 1
    assert not driver.sql.SQL.called and conn.close.called


def test_close_error_redacted_and_not_success(monkeypatch, capsys):
    conn, _driver = fake_driver(monkeypatch)
    monkeypatch.setattr(harness, "run_audit", MagicMock())
    conn.close.side_effect = RuntimeError(URL)
    assert harness.main(["--confirm-local-test-server"]) == 1
    output = capsys.readouterr().out
    assert URL not in output and "PASS: PostgreSQL 16" not in output


def test_repository_setup_offline_sqlite_smoke(tmp_path, monkeypatch):
    """Check explicit repository configuration and migration 13 without dotenv."""
    from app.database.backend import Database
    from app.database.config import DatabaseSettings
    from app.quotas import Limits, QuotaSettings
    from app.quotas.synchronous import SynchronousUsage
    from app.jobs import JobScope
    from app.auth import AuthRepository
    from app.organizations import OrganizationRepository
    import dotenv
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: pytest.fail("dotenv forbidden"))
    db = Database(DatabaseSettings("", tmp_path / "isolated.db"))
    try:
        db.migrate()
        account = AuthRepository(db).create_account("synthetic@example.test", "synthetic")
        org = OrganizationRepository(db).default_for_account(account.id)
        usage = SynchronousUsage(db, QuotaSettings(True, Limits(2, 2, 1)))
        scope = JobScope(account.id, org.id)
        assert usage.finish(usage.admit(scope, "rag"))
        with closing(db.connect()) as conn:
            assert conn.execute("SELECT MAX(version) FROM app_schema_migrations").fetchone()[0] == 14
    finally:
        db.close()


def test_complete_case_logic_offline_with_sqlite_and_process_doubles(tmp_path, monkeypatch):
    """Catch scenario/API mistakes without claiming PostgreSQL or process coverage."""
    from datetime import datetime, timezone
    import queue
    import threading
    from app.database.backend import Database
    from app.database.config import DatabaseSettings
    from tests import postgresql_phase24s2b3_cases as cases

    class Connection:
        def __init__(self, raw):
            self.raw = raw
        def __getattr__(self, name):
            return getattr(self.raw, name)
        def __enter__(self):
            self.raw.__enter__()
            return self
        def __exit__(self, *args):
            return self.raw.__exit__(*args)
        def execute(self, sql, params=()):
            if sql.startswith("SELECT EXTRACT(DAY"):
                return self.raw.execute("SELECT ?", (datetime.now(timezone.utc).day,))
            if "date_trunc(" in sql:
                now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                if "date_trunc('month'" in sql:
                    now = now.replace(day=1)
                return self.raw.execute("UPDATE synchronous_usage SET admitted_at=? WHERE id=?",
                                        (int(now.timestamp() * 1000000) - 1, *params))
            return self.raw.execute(sql, params)

    def factory(_parameters):
        database = Database(DatabaseSettings("", tmp_path / "scenario.db"))
        original = database.connect
        database.connect = lambda: Connection(original())
        return database

    class Output(queue.Queue):
        def close(self):
            pass
        def join_thread(self):
            pass

    class Process:
        def __init__(self, target, args):
            self.exitcode = None
            def run():
                target(*args)
                self.exitcode = 0
            self.thread = threading.Thread(target=run)
        def start(self):
            self.thread.start()
        def join(self, timeout):
            self.thread.join(timeout)
        def is_alive(self):
            return self.thread.is_alive()
        def terminate(self):
            pytest.fail("Offline scenario worker stalled")

    context = SimpleNamespace(Event=threading.Event, Queue=Output, Process=Process)
    monkeypatch.setattr(cases, "database_for_parameters", factory)
    monkeypatch.setattr(harness, "database_for_parameters", factory)
    monkeypatch.setattr(cases.multiprocessing, "get_context", lambda method: context)
    cases.run_cases({})


@pytest.mark.parametrize("configured_port", ["64628", ""], ids=["explicit-port", "auto-port"])
@pytest.mark.parametrize("section,key", [("HostConfig", "PortBindings"),
                                        ("NetworkSettings", "Ports")])
@pytest.mark.parametrize("mapping", [
    {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "5432"}]},
    {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "64629"}]},
    {"5432/tcp": [{"HostIp": "0.0.0.0", "HostPort": ""}]},
    {"5432/tcp": [{"HostIp": "", "HostPort": ""}]},
    {"5432/tcp": [{"HostIp": "::1", "HostPort": "64628"}]},
    {"5432/tcp": [{"HostIp": "127.0.0.2", "HostPort": "64628"}]},
    {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "64628"},
                  {"HostIp": "127.0.0.1", "HostPort": ""}]},
    {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "64628"}],
     "5433/tcp": [{"HostIp": "127.0.0.1", "HostPort": ""}]},
    {},
])
def test_spoofed_port_mappings_rejected(monkeypatch, configured_port, section, key, mapping):
    import json
    record = container_record(configured_port)
    record[section][key] = mapping
    output = MagicMock(return_value=json.dumps([record]))
    monkeypatch.setattr(harness, "docker_output", output)
    with pytest.raises(harness.HarnessError):
        harness.verify_container({"host": "127.0.0.1", "port": 64628}, "a" * 64)
    output.assert_called_once_with(["container", "inspect", "a" * 64])


def test_auto_port_requires_resolved_runtime_port(monkeypatch):
    import json
    record = container_record("")
    record["NetworkSettings"]["Ports"]["5432/tcp"][0]["HostPort"] = ""
    output = MagicMock(return_value=json.dumps([record]))
    monkeypatch.setattr(harness, "docker_output", output)
    with pytest.raises(harness.HarnessError):
        harness.verify_container({"host": "127.0.0.1", "port": 64628}, "a" * 64)
    output.assert_called_once_with(["container", "inspect", "a" * 64])


def container_record(configured_port="64628"):
    binding = {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "64628"}]}
    return {"Id": "a" * 64, "State": {"Running": True},
            "Config": {"Labels": {"valyqon.test": "phase24s2b3"}, "Image": "postgres:16-alpine"},
            "HostConfig": {"NetworkMode": "bridge", "PortBindings": {
                "5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": configured_port}]}},
            "NetworkSettings": {"Ports": binding,
                                "Networks": {"bridge": {"IPAddress": "172.17.0.2"}}}}


@pytest.mark.parametrize("forgery", [None, "id", "label", "binding", "runtime_binding",
                                    "image", "stopped", "host", "cluster", "version"])
@pytest.mark.parametrize("configured_port", ["64628", ""], ids=["explicit-port", "auto-port"])
def test_docker_nat_and_forged_identity(monkeypatch, forgery, configured_port):
    import json
    record = container_record(configured_port)
    if forgery == "id":
        record["Id"] = "b" * 64
    elif forgery == "label":
        record["Config"]["Labels"]["valyqon.test"] = "production"
    elif forgery in ("binding", "runtime_binding"):
        target = record["HostConfig"] if forgery == "binding" else record["NetworkSettings"]
        target["PortBindings" if forgery == "binding" else "Ports"] = {
            "5432/tcp": [{"HostIp": "0.0.0.0", "HostPort": "64628"}]}
    elif forgery == "image":
        record["Config"]["Image"] = "postgres:15"
    elif forgery == "stopped":
        record["State"]["Running"] = False
    elif forgery == "host":
        record["HostConfig"]["NetworkMode"] = "host"
    output = MagicMock(side_effect=[json.dumps([record]),
        "Database system identifier: 123\nCatalog version number: 202307071\n"])
    monkeypatch.setattr(harness, "docker_output", output)
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = (
        "172.17.0.2", "192.168.65.1", "postgres",
        150001 if forgery == "version" else 160010,
        "999" if forgery == "cluster" else "123")
    def verify():
        identity = harness.verify_container({"host": "127.0.0.1", "port": 64628}, "a" * 64)
        harness.verify_server(conn, identity)
    if forgery:
        with pytest.raises(harness.HarnessError):
            verify()
    else:
        verify()
        assert output.call_args_list[0].args[0] == ["container", "inspect", "a" * 64]
        assert output.call_args_list[1].args[0][3] == "a" * 64


@pytest.mark.parametrize("identifier", ["", "postgres", "a" * 12, "--all"])
def test_invalid_container_id_never_invokes_docker(monkeypatch, identifier):
    output = MagicMock()
    monkeypatch.setattr(harness, "docker_output", output)
    with pytest.raises(harness.HarnessError):
        harness.verify_container({"host": "127.0.0.1", "port": 64628}, identifier)
    output.assert_not_called()


@pytest.mark.parametrize("image", ["postgres:16", "postgres:15-alpine",
                                  "postgres:16-alpine3.20", "postgres:16-alpine-custom",
                                  "custom/postgres:16-alpine"])
def test_only_exact_alpine_image_allowed(monkeypatch, image):
    import json
    record = container_record()
    record["Config"]["Image"] = image
    output = MagicMock(return_value=json.dumps([record]))
    monkeypatch.setattr(harness, "docker_output", output)
    with pytest.raises(harness.HarnessError):
        harness.verify_container({"host": "127.0.0.1", "port": 64628}, "a" * 64)
    output.assert_called_once_with(["container", "inspect", "a" * 64])
