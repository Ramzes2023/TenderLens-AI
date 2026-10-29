# Read-only existing V6 Lenobl canary. No rebuild/deploy/restart or DB writes.
# Example: .\scripts\VALYQON-V6-LENOBL-EXISTING-IMAGE-READONLY.ps1 -Target 'ubuntu@<your-vps-host>'
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-zA-Z][a-zA-Z0-9_-]{0,31}@[A-Za-z0-9.-]+$')]
    [string]$Target,
    [string]$IdentityFile = (Join-Path $HOME '.ssh\tenderlens_vps_ed25519')
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $IdentityFile -PathType Leaf)) {
    throw 'Existing SSH identity not found; no remote action.'
}
$ssh = (Get-Command ssh.exe -ErrorAction Stop).Source
# Single-quoted here-string: remote shell and Python receive literal content.
$remote = @'
set -eu
# Only the reviewed isolated V6 Worker; do not fall back to an arbitrary
# container, V5, production API or the stopped Telegram bot.
ids="$(docker ps --filter 'label=com.docker.compose.project=valyqon-public-sources' --filter 'label=com.docker.compose.service=worker-v6' --format '{{.ID}}')"
count="$(printf '%s\n' "$ids" | awk 'NF{n++} END{print n+0}')"
if [ "$count" -ne 1 ]; then
  printf 'V6_EXACT_WORKER=BLOCKED_NOT_UNIQUE\nPRODUCTION_CHANGED=NO\n'
  exit 2
fi
docker exec -i "$ids" python - <<'PY'
import asyncio
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

SOURCE_IDS = (
    "mikroton_tender", "stan_commercial_public", "south_ural_public",
    "kavkaz_rf_firstparty", "lenobl_small_public", "ru_samara_public_list",
)
DB_PATH = "/app/data/isolated-public-sources.sqlite3"
EXPECTED = {
    "DATABASE_URL": "sqlite:////app/data/isolated-public-sources.sqlite3",
    "VALYQON_ISOLATED_PUBLIC_SOURCES_ENABLED": "true",
    "LENOBL_SMALL_PUBLIC_ENABLED": "true",
    "VALYQON_CONNECTOR_MAX_RECORDS": "30",
    "MONITORING_ENABLED": "false",
    "VALYQON_EMAIL_MODE": "disabled",
    "VALYQON_RESTRICT_PAID_SOURCE_DETAILS": "true",
}
def fail(status, code=2):
    print("V6_LENOBL_EXISTING_IMAGE=" + status, flush=True)
    print("TELEGRAM_SEND_AUTHORIZED=NO", flush=True)
    print("PRODUCTION_CHANGED=NO", flush=True)
    raise SystemExit(code)
if any(os.environ.get(key) != value for key, value in EXPECTED.items()):
    fail("BLOCKED_UNSAFE_ENV")
if (os.environ.get("TELEGRAM_BOT_TOKEN", "")
        or os.environ.get("OUTBOUND_PROXY_URL", "")
        or os.environ.get("VALYQON_RU_BACKGROUND_CATALOG_ENABLED", "false") != "false"):
    fail("BLOCKED_NOTIFICATION_OR_PROXY")
try:
    # The existing isolated SQLite volume is opened exclusively in read-only
    # mode; only safe aggregate source-state fields are printed.
    uri = "file:" + DB_PATH + "?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=5) as conn:
        conn.execute("PRAGMA query_only=ON")
        rows = conn.execute(
            "SELECT payload_json,state,result_json,finished_at,failure_code "
            "FROM durable_jobs WHERE job_type='connector.sync.v1' "
            "ORDER BY created_at DESC LIMIT 600"
        ).fetchall()
    now_us = int(datetime.now(timezone.utc).timestamp() * 1_000_000)
    statuses = {}
    for payload, state, result, finished, failure in rows:
        try:
            source = json.loads(payload).get("source_id")
            if source not in SOURCE_IDS or source in statuses:
                continue
            accepted = json.loads(result).get("accepted_count") if result else None
            if type(accepted) is not int or accepted < 0:
                accepted = None
            age = round((now_us - finished) / 60_000_000, 1) if type(finished) is int and 0 < finished <= now_us else None
            safe_failure = failure if failure in {"handler_error", "permanent_failure", "lease_expired", "invalid_result", "unknown_type"} else "unclassified" if failure else None
            statuses[source] = {
                "state": state if state in {"queued","running","succeeded","failed","cancelled"} else "unknown",
                "age_min": age,
                "accepted_count": accepted,
                "failure_code": safe_failure if state == "failed" else None,
            }
        except (ValueError, TypeError, AttributeError):
            continue
    print("V6_WORKER_SIX_SOURCE_AUDIT=" + json.dumps(
        {key: statuses.get(key, {"state":"not_found"}) for key in SOURCE_IDS},
        separators=(",",":"), sort_keys=True), flush=True)
except (OSError, sqlite3.Error, ValueError, TypeError):
    fail("BLOCKED_STORAGE")
try:
    # Run source import from the CURRENT deployed image. This deliberately
    # does not import the newly merged canary from a not-yet-deployed image.
    from app.sources.http import FetchPolicy, bounded_fetch
    from app.sources.lenobl_small_public import HOST, LenoblSmallPublicSource
    from app.api.public_source_deadline import eligible_published_deadline
except Exception as exc:
    print("V6_SOURCE_IMPORT_CLASS=" + type(exc).__name__, flush=True)
    fail("BLOCKED_SOURCE_IMPORT")

async def probe():
    policy = FetchPolicy(frozenset({HOST}), max_requests=4)
    output = {
        "source": "lenobl_small_public",
        "limit": 4,
        "originals": 0,
        "current_deadlines": 0,
        "error_class": "none",
        "transport_reason": "none",
        "sql_write": False,
        "send": False,
    }
    try:
        with bounded_fetch(policy):
            items = await asyncio.wait_for(LenoblSmallPublicSource().fetch(30), timeout=125)
        if type(items) is not list or len(items) > 3:
            raise ValueError("Invalid bounded source result")
        output["originals"] = len(items)
        output["current_deadlines"] = sum(
            bool(eligible_published_deadline("lenobl_small_public", item.deadline,
                                              now=datetime.now(timezone.utc)))
            for item in items)
        output["result"] = "CANDIDATE_ONLY" if output["current_deadlines"] else "NO_OPEN_CURRENT"
    except Exception as exc:
        # Exception text, URLs and traceback must never be shown or persisted.
        name = type(exc).__name__
        output["error_class"] = name if name.isascii() and name.isidentifier() and len(name) <= 64 else "UnknownException"
        reason = getattr(exc, "reason", None)
        output["transport_reason"] = reason if reason in {"network","timeout","policy","tls","dns","http_status","size","redirect"} else "none"
        output["result"] = "BLOCKED_FIRSTPARTY"
    output["http_requests"] = policy.requests
    return output

try:
    data = asyncio.run(probe())
except Exception as exc:
    print("V6_CANARY_EXCEPTION_CLASS=" + type(exc).__name__, flush=True)
    fail("BLOCKED_PROBE_RUNTIME")
print("V6_LENOBL_CANARY=" + json.dumps(data, separators=(",",":"), sort_keys=True), flush=True)
print("V6_LENOBL_EXISTING_IMAGE=READONLY_DIAGNOSED", flush=True)
print("TELEGRAM_SEND_AUTHORIZED=NO", flush=True)
print("PRODUCTION_CHANGED=NO", flush=True)
PY
'@
$remote | & $ssh -T -i $IdentityFile -o 'BatchMode=yes' -o 'IdentitiesOnly=yes' -o 'StrictHostKeyChecking=yes' -o 'ConnectTimeout=10' $Target 'sh -s'
if ($LASTEXITCODE -ne 0) {
    throw "READONLY_V6_DIAGNOSTIC_EXIT=$LASTEXITCODE (no deployment performed)"
}
