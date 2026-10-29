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
printf 'V6_SHELL_EXECUTED=YES\n'
# Only the reviewed isolated V6 Worker; do not fall back to an arbitrary
# container, V5, production API or the stopped Telegram bot.
# Live operator inventory (2026-10-29) confirmed the ONE running V6 worker:
# project=valyqon-public-sources; service=worker-v6;
# image=valyqon-public-sources:v6-fe4c66bbd553.
# Never fall back to V5, legacy service=worker or production/API containers.
expected_image="valyqon-public-sources:v6-fe4c66bbd553"
if ! ids="$(docker ps --filter 'label=com.docker.compose.project=valyqon-public-sources' --filter 'label=com.docker.compose.service=worker-v6' --format '{{.ID}}' 2>/dev/null)"; then
  printf 'V6_EXACT_WORKER=BLOCKED_DOCKER_ACCESS\nPRODUCTION_CHANGED=NO\n'
  exit 2
fi
count="$(printf '%s\n' "$ids" | awk 'NF{n++} END{print n+0}')"
printf 'V6_PRIMARY_LABEL_MATCH_COUNT=%s\n' "$count"
if [ "$count" -ne 1 ]; then
  if [ "$count" -eq 0 ]; then
    printf 'V6_EXACT_WORKER=BLOCKED_NOT_FOUND\n'
  else
    printf 'V6_EXACT_WORKER=BLOCKED_NOT_UNIQUE\n'
  fi
  printf 'PRODUCTION_CHANGED=NO\n'
  exit 2
fi
if ! image="$(docker inspect --format '{{.Config.Image}}' "$ids" 2>/dev/null)"; then
  printf 'V6_EXACT_WORKER=BLOCKED_DOCKER_ACCESS\nPRODUCTION_CHANGED=NO\n'
  exit 2
fi
if [ "$image" != "$expected_image" ]; then
  printf 'V6_EXACT_WORKER=BLOCKED_IMAGE_NOT_VERIFIED\nPRODUCTION_CHANGED=NO\n'
  exit 2
fi
printf 'V6_SELECTION=EXACT_INVENTORIED_WORKER_V6\n'
printf 'V6_EXACT_WORKER=VERIFIED_UNIQUE_PINNED_IMAGE\n'
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
# Windows PowerShell pipes add CRLF; dash/sh treats CR as an invalid option.
# Send exact LF-only ASCII script over process stdin, not a native pipeline.
$remoteLf = $remote.Replace("`r`n", "`n").Replace("`r", "`n").TrimEnd([char]10) + "`n"
if ($remoteLf.Contains("`r") -or -not $remoteLf.StartsWith("set -eu`n") -or
    -not $remoteLf.EndsWith("`nPY`n")) {
    throw "READONLY_V6_DIAGNOSTIC=BLOCKED_UNSAFE_SHELL_STREAM"
}
if ($IdentityFile.Contains('"')) {
    throw "READONLY_V6_DIAGNOSTIC=BLOCKED_UNSAFE_IDENTITY_PATH"
}
$start = New-Object System.Diagnostics.ProcessStartInfo
$start.FileName = $ssh
$start.Arguments = '-T -i "' + $IdentityFile + '" -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 ' + $Target + ' sh -s'
$start.UseShellExecute = $false
$start.RedirectStandardInput = $true
$start.RedirectStandardOutput = $true
$start.RedirectStandardError = $true
$start.CreateNoWindow = $true
$process = New-Object System.Diagnostics.Process
$process.StartInfo = $start
try {
    if (-not $process.Start()) { throw "READONLY_V6_DIAGNOSTIC=SSH_START_FAILED" }
    # Drain BOTH streams concurrently to avoid SSH/Docker buffer deadlocks.
    # Never show raw stderr, which may contain host details or secrets.
    $outTask = $process.StandardOutput.ReadToEndAsync()
    $errTask = $process.StandardError.ReadToEndAsync()
    try {
        $process.StandardInput.Write($remoteLf)
    } finally {
        $process.StandardInput.Close()
    }
    if (-not $process.WaitForExit(160000)) {
        $process.Kill()
        throw "READONLY_V6_DIAGNOSTIC=SSH_OR_SOURCE_TIMEOUT"
    }
    $status = $process.ExitCode
    $safeStdout = $outTask.GetAwaiter().GetResult()
    $safeStderr = $errTask.GetAwaiter().GetResult()
} finally {
    $process.Dispose()
}
# Only fixed diagnostic markers from the trusted script. No raw stdout,
# shell error, traceback or remote buyer/account data is forwarded.
$printed = 0
foreach ($line in ($safeStdout -split '\r?\n')) {
    if ($line.Length -gt 12000) { continue }
    if ($line -match '^(?:V6_SHELL_EXECUTED|V6_EXACT_WORKER|V6_SELECTION|V6_PRIMARY_LABEL_MATCH_COUNT|V6_PINNED_IMAGE_WORKER_MATCH_COUNT|V6_LENOBL_EXISTING_IMAGE|V6_SOURCE_IMPORT_CLASS|V6_CANARY_EXCEPTION_CLASS|TELEGRAM_SEND_AUTHORIZED|PRODUCTION_CHANGED)=[A-Za-z0-9_-]{1,80}$') {
        Write-Output $line
        $printed++
    } elseif ($line -match '^(V6_WORKER_SIX_SOURCE_AUDIT|V6_LENOBL_CANARY)=(\{[^\r\n]{1,11000}\})$') {
        # Verify valid JSON, then re-emit only the expected strict-shape fields.
        try {
            $record = $Matches[2] | ConvertFrom-Json -ErrorAction Stop
            if ($Matches[1] -eq 'V6_WORKER_SIX_SOURCE_AUDIT') {
                $allowedIds = @('mikroton_tender','stan_commercial_public','south_ural_public','kavkaz_rf_firstparty','lenobl_small_public','ru_samara_public_list')
                $clean = [ordered]@{}
                foreach ($id in $allowedIds) {
                    $entry = $record.PSObject.Properties[$id].Value
                    $state = [string]$entry.state
                    if ($state -notin @('queued','running','succeeded','failed','cancelled','not_found','unknown')) { $state = 'unknown' }
                    $failure = [string]$entry.failure_code
                    if ($failure -notin @('handler_error','permanent_failure','lease_expired','invalid_result','unknown_type','unclassified')) { $failure = $null }
                    $accepted = if ($entry.accepted_count -is [int] -and $entry.accepted_count -ge 0) { $entry.accepted_count } else { $null }
                    $age = if ($entry.age_min -is [double] -and $entry.age_min -ge 0) { $entry.age_min } else { $null }
                    $clean[$id] = @{state=$state;failure_code=$failure;accepted_count=$accepted;age_min=$age}
                }
                Write-Output ('V6_WORKER_SIX_SOURCE_AUDIT=' + ($clean | ConvertTo-Json -Depth 5 -Compress))
                $printed++
            } else {
                $reason = [string]$record.transport_reason
                if ($reason -notin @('network','timeout','policy','tls','dns','http_status','size','redirect','none')) { $reason='none' }
                $class = [string]$record.error_class
                if ($class -notmatch '^[A-Za-z][A-Za-z0-9_]{0,63}$') { $class='UnknownException' }
                $result = [string]$record.result
                if ($result -notin @('CANDIDATE_ONLY','NO_OPEN_CURRENT','BLOCKED_FIRSTPARTY')) { $result='UNKNOWN' }
                $clean = [ordered]@{
                    result=$result
                    error_class=$class
                    transport_reason=$reason
                    http_requests=$record.http_requests
                    originals=$record.originals
                    current_deadlines=$record.current_deadlines
                }
                Write-Output ('V6_LENOBL_CANARY=' + ($clean | ConvertTo-Json -Compress))
                $printed++
            }
        } catch {
            Write-Output 'V6_DIAGNOSTIC_JSON=BLOCKED_INVALID'
            $printed++
        }
    }
}
if ($printed -eq 0) {
    Write-Output 'V6_REMOTE_SAFE_MARKERS=NONE'
}
if ($safeStderr.Length -gt 0) {
    Write-Output 'V6_REMOTE_STDERR_PRESENT=YES_REDACTED'
}
Write-Output "V6_SSH_EXIT_CODE=$status"
if ($status -ne 0) {
    throw "READONLY_V6_DIAGNOSTIC_EXIT=$status (no deployment performed)"
}
