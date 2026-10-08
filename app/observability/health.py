"""Local operator command: read-only relational diagnostics; never probes providers."""
from contextlib import closing
import json
import time

def runtime_snapshot(runtime):
    """Trusted in-process operator view, never mounted on a public HTTP route."""
    from app.observability import telemetry
    # Only known status values survive even custom runtime implementations.
    try:
        statuses = runtime.component_status()
    except Exception:
        statuses = {}
    components = {key: statuses.get(key) if statuses.get(key) in {"ready", "disabled", "unavailable"}
                  else "unavailable" for key in ("database", "cache", "llm", "rag", "sources", "auth")}
    result = {"components": components, "metrics": telemetry.snapshot(), "provider_connectivity": "not_probed"}
    try:
        result["queue"] = queue_snapshot(runtime.database)
    except Exception:
        result["queue"] = "unavailable"
    return result


STATES = ("queued", "running", "succeeded", "failed", "cancelled")


def queue_snapshot(database, now=None):
    now = int(time.time() * 1000000) if now is None else now
    with closing(database.connect()) as conn:
        counts = {state: conn.execute("SELECT COUNT(*) FROM durable_jobs WHERE state=?", (state,)).fetchone()[0]
                  for state in STATES}
        oldest = conn.execute("SELECT MIN(created_at) FROM durable_jobs WHERE state='queued'").fetchone()[0]
        expired = conn.execute("SELECT COUNT(*) FROM durable_jobs WHERE state='running' AND lease_expires_at<=?", (now,)).fetchone()[0]
        retried = conn.execute("SELECT COUNT(*) FROM durable_jobs WHERE (state='queued' AND attempt_count>0) OR (state='running' AND attempt_count>1)").fetchone()[0]
        from app.jobs.repository import FAILURE_CODES
        failures = {code: conn.execute("SELECT COUNT(*) FROM durable_jobs WHERE failure_code=?", (code,)).fetchone()[0]
                    for code in sorted(FAILURE_CODES)}
    return {"states": counts, "oldest_queued_seconds": None if oldest is None else max(0, (now-oldest)/1000000),
            "expired_leases": expired, "active_retried_jobs": retried, "failure_codes": failures}


def main():
    from app.database.backend import Database
    from app.database.config import load_database_settings
    database = None
    try:
        database = Database(load_database_settings())
        output = {"database": "ready", "queue": queue_snapshot(database),
                  "provider_connectivity": "not_probed"}
        print(json.dumps(output, separators=(",", ":")))
        return 0
    except Exception:
        print('{"database":"unavailable","queue":"unavailable","provider_connectivity":"not_probed"}')
        return 1
    finally:
        if database is not None:
            database.close()


if __name__ == "__main__":
    raise SystemExit(main())
