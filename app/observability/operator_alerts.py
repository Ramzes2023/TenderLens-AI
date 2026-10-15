"""Fail-closed, opt-in operator alert checks. No request handlers or background work.

Sources: persisted durable-job and opportunity summaries plus explicitly supplied
Caddy JSON access-log path. No tenant identifiers or message content are exposed.
Only a trusted SINGLE instance of this command should be scheduled.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib import request


def _utc(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def inspect_http_log(path, now=None):
    """Count Caddy JSON request statuses in the last and previous 15 minutes.

    Input must be an explicit *local* readable log, never a remote URL or URL
    extracted from a request. Bounded to the most recent 2 MiB.
    """
    if not path:
        return {"status": "not_configured"}
    target = Path(path)
    if not target.is_absolute() or not target.is_file() or target.is_symlink():
        return {"status": "unavailable"}
    now = time.time() if now is None else float(now)
    try:
        with target.open("rb") as stream:
            stream.seek(0, 2)
            size = stream.tell()
            stream.seek(max(0, size - 2 * 1024 * 1024))
            payload = stream.read(2 * 1024 * 1024)
        if size > len(payload):
            payload = payload.partition(b"\n")[2]
    except OSError:
        return {"status": "unavailable"}
    windows = [[0, 0], [0, 0]]
    for line in payload.splitlines():
        if len(line) > 8192:
            continue
        try:
            value = json.loads(line)
            ts = value.get("ts")
            status = value.get("status")
            if type(ts) not in (float, int) or type(status) is not int:
                continue
            age = now - ts
            if not 0 <= age < 1800 or not 100 <= status <= 599:
                continue
            index = 0 if age < 900 else 1
            windows[index][0] += 1
            windows[index][1] += int(status >= 500)
        except (ValueError, TypeError, AttributeError):
            continue
    return {"status": "measured", "current_requests": windows[0][0],
            "current_5xx": windows[0][1], "previous_requests": windows[1][0],
            "previous_5xx": windows[1][1]}


def inspect_database(database, expected_sources=(), now=None):
    """Read only aggregate job counts and freshness, never customer/job payloads."""
    now = time.time() if now is None else float(now)
    if not 0 <= now < 10**11:
        raise ValueError("Invalid clock")
    now_us = int(now * 1_000_000)
    sources = {}
    with closing(database.connect()) as conn:
        failed = conn.execute(
            "SELECT COUNT(*) FROM durable_jobs WHERE state='failed' AND finished_at >= ?",
            (now_us - 15 * 60 * 1_000_000,),
        ).fetchone()[0]
        expired = conn.execute(
            "SELECT COUNT(*) FROM durable_jobs WHERE state='running' AND lease_expires_at <= ?",
            (now_us,),
        ).fetchone()[0]
        for source in expected_sources:
            if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,63}", source):
                raise ValueError("Invalid configured source identifier")
            latest = conn.execute(
                "SELECT MAX(last_seen) FROM source_opportunities WHERE source_id=?",
                (source,),
            ).fetchone()[0]
            parsed = _utc(latest) if latest else None
            sources[source] = None if parsed is None else max(0, now - parsed.timestamp())
    return {"recent_failed_jobs": int(failed), "expired_worker_leases": int(expired),
            "source_last_seen_seconds": sources}


def evaluate(snapshot, http, *, source_stale_seconds=86400, failed_threshold=1):
    """Stable identifiers and messages only. Empty feeds may be legitimate.

    Source alerts indicate missing *freshness evidence*, NOT that a procurement
    portal has failed or that zero tenders proves a fault.
    """
    alerts = []
    if snapshot["expired_worker_leases"] > 0:
        alerts.append(("worker_lease_expired", "Worker lease expired; investigate stopped or stuck workers."))
    if snapshot["recent_failed_jobs"] >= failed_threshold:
        alerts.append(("jobs_recently_failed", "Durable jobs failed in the last 15 minutes."))
    for source, age in sorted(snapshot["source_last_seen_seconds"].items()):
        if age is None or age >= source_stale_seconds:
            alerts.append(("source_stale:" + source, "Source " + source + " has no recent persisted opportunity evidence; check last fetch status."))
    if http.get("status") == "measured":
        current, errors = http["current_requests"], http["current_5xx"]
        previous, past_errors = http["previous_requests"], http["previous_5xx"]
        rate = errors / max(current, 1)
        past_rate = past_errors / max(previous, 1)
        if current >= 20 and errors >= 5 and rate >= 0.05 and (previous < 20 or rate >= past_rate * 1.5):
            alerts.append(("http_5xx_growth", "HTTP 5xx increased in the last 15 minutes; inspect reverse-proxy logs."))
    return alerts


def _telegram_send(token, chat_id, message):
    """Send fixed sanitized text; do not log HTTP errors containing token URL."""
    if not re.fullmatch(r"\d{5,12}:[A-Za-z0-9_-]{20,}", token):
        raise ValueError("Invalid operator bot token format")
    if not re.fullmatch(r"-?\d{5,20}", chat_id):
        raise ValueError("Invalid operator Telegram chat ID")
    body = json.dumps({"chat_id": chat_id, "text": message,
                       "disable_web_page_preview": True}).encode("utf-8")
    req = request.Request("https://api.telegram.org/bot" + token + "/sendMessage",
                          data=body, headers={"Content-Type": "application/json"}, method="POST")
    with request.urlopen(req, timeout=7) as response:
        if response.status != 200:
            raise ValueError("Telegram refused alert")


def _emit_once(alerts, *, token, chat_id, state_file, now):
    """Best-effort rate limit for one scheduled instance on one persistent volume."""
    p = Path(state_file)
    if not p.is_absolute() or p.is_symlink() or not p.parent.is_dir():
        raise ValueError("Absolute existing private alert-state directory required")
    if p.exists() and p.stat().st_size > 32768:
        raise ValueError("Invalid alert state")
    try:
        last = json.loads(p.read_text("utf-8")) if p.exists() else {}
        if not isinstance(last, dict):
            raise ValueError
    except (OSError, ValueError):
        raise ValueError("Unreadable alert state") from None
    last = {k: v for k, v in last.items()
            if isinstance(k, str) and type(v) in (int, float) and 0 <= now - v <= 604800}
    pending = [(key, body) for key, body in alerts if now - last.get(key, 0) >= 3600]
    for key, body in pending:
        _telegram_send(token, chat_id, "VALYQON OPERATOR ALERT\n" + body)
        last[key] = now
        temporary = p.with_name(p.name + ".tmp-" + str(os.getpid()))
        try:
            descriptor = os.open(str(temporary), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(last, stream, separators=(",", ":"), sort_keys=True)
            os.replace(temporary, p)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
    return len(pending)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--send", action="store_true", help="Opt-in to Telegram delivery")
    args = parser.parse_args(argv)
    if os.environ.get("PYTHON_DOTENV_DISABLED") != "1":
        print("OPERATOR_ALERTS=REFUSED: disable project dotenv loading")
        return 2
    from app.database.backend import Database
    from app.database.config import load_database_settings
    database = None
    try:
        sources_raw = os.environ.get("VALYQON_OPERATOR_EXPECTED_SOURCES", "")
        expected = tuple(filter(None, (s.strip() for s in sources_raw.split(","))))
        if len(expected) > 30 or len(set(expected)) != len(expected):
            raise ValueError("Too many or duplicate expected sources")
        database = Database(load_database_settings())
        snapshot = inspect_database(database, expected_sources=expected)
        http = inspect_http_log(os.environ.get("VALYQON_OPERATOR_CADDY_LOG", ""))
        alerts = evaluate(snapshot, http)
        # No customer data, credentials, source links, job IDs or stack traces.
        print(json.dumps({"status": "evaluated", "alert_count": len(alerts),
                          "alert_codes": [key for key, _ in alerts],
                          "http_measurement": http["status"]}, separators=(",", ":")))
        if not args.send:
            print("OPERATOR_ALERTS=DRY_RUN")
            return 0
        if os.environ.get("VALYQON_OPERATOR_ALERTS_ENABLED") != "1":
            print("OPERATOR_ALERTS=REFUSED: delivery disabled")
            return 2
        token = os.environ.get("VALYQON_OPERATOR_TELEGRAM_BOT_TOKEN", "")
        chat = os.environ.get("VALYQON_OPERATOR_TELEGRAM_CHAT_ID", "")
        state = os.environ.get("VALYQON_OPERATOR_ALERT_STATE_FILE", "")
        if not token or not chat or not state:
            print("OPERATOR_ALERTS=REFUSED: delivery credentials/state missing")
            return 2
        sent = _emit_once(alerts, token=token, chat_id=chat, state_file=state, now=time.time())
        print("OPERATOR_ALERTS=DELIVERED; COUNT=" + str(sent))
        return 0
    except Exception:
        print("OPERATOR_ALERTS=UNAVAILABLE; DETAILS_REDACTED")
        return 1
    finally:
        if database is not None:
            database.close()


if __name__ == "__main__":
    sys.exit(main())
