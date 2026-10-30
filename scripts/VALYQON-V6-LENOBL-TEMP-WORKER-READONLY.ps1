# Existing V6 Lenobl leased Worker acceptance in disposable /tmp database. No live database writes or deploy.
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
import inspect
import json
import os
import tempfile
from pathlib import Path
from datetime import datetime, timezone

def out(key, value):
    print(key + "=" + value, flush=True)

def fail(reason):
    out("V6_LENOBL_TEMP_WORKER", reason)
    out("TELEGRAM_SEND_AUTHORIZED", "NO")
    out("PRODUCTION_CHANGED", "NO")
    raise SystemExit(2)

EXPECTED = {
    "DATABASE_URL": "sqlite:////app/data/isolated-public-sources.sqlite3",
    "VALYQON_ISOLATED_PUBLIC_SOURCES_ENABLED": "true",
    "LENOBL_SMALL_PUBLIC_ENABLED": "true",
    "VALYQON_CONNECTOR_MAX_RECORDS": "30",
    "MONITORING_ENABLED": "false",
    "VALYQON_EMAIL_MODE": "disabled",
    "VALYQON_RESTRICT_PAID_SOURCE_DETAILS": "true",
}
if any(os.environ.get(k) != v for k, v in EXPECTED.items()):
    fail("BLOCKED_UNSAFE_ENV")
if (os.environ.get("TELEGRAM_BOT_TOKEN", "")
        or os.environ.get("OUTBOUND_PROXY_URL", "")
        or os.environ.get("VALYQON_RU_BACKGROUND_CATALOG_ENABLED", "false") != "false"):
    fail("BLOCKED_UNSAFE_NOTIFICATIONS")

try:
    import app.sources.lenobl_small_public as lenobl_runtime
    from app.sources.lenobl_small_public import LenoblSmallPublicSource
    from app.api.public_source_deadline import eligible_published_deadline
    from app.database.backend import Database
    from app.database.config import DatabaseSettings
    from app.jobs import HandlerRegistry, JobRepository, JobSettings
    from app.jobs.models import JobScope
    from app.jobs.worker import Worker
    from app.monitoring.config import MonitoringSettings
    from app.sources.catalog import build_source_catalog
    from app.sources.ingestion import (JOB_TYPE, ConnectorSyncHandler,
                                      ConnectorSyncService, connector_version)
    from app.sources.opportunities import OpportunityRepository
    from app.sources.snapshots import snapshot_catalog
except Exception as exc:
    out("V6_LENOBL_TEMP_EXCEPTION_CLASS", type(exc).__name__)
    fail("BLOCKED_IMPORT")

try:
    legacy = inspect.getsource(LenoblSmallPublicSource.fetch)
    assert lenobl_runtime.__file__ == "/app/app/sources/lenobl_small_public.py"
    assert lenobl_runtime.HOST == "zakupki.lenreg.ru"
    assert lenobl_runtime.MAX_DETAILS == 6
    assert "cap = min(limit, MAX_DETAILS)" in legacy
    assert "remaining_details" not in legacy
    assert "if _policy.get() is None else nullcontext()" in legacy
except (AssertionError, AttributeError, OSError, TypeError):
    fail("BLOCKED_LEGACY_FINGERPRINT")
# Only this ephemeral docker-exec process; NEVER mutate the actual worker.
lenobl_runtime.MAX_DETAILS = 3
out("V6_LENOBL_BUDGET_MODE", "LEGACY_INPROCESS_THREE_DETAILS")
try:
    catalog = build_source_catalog(MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=3,
        max_notifications_per_cycle=5, request_timeout=25,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
        lenobl_small_public_enabled=True,
    ))
    if "lenobl_small_public" not in catalog.enabled_keys:
        fail("BLOCKED_CATALOG")

    # Disposable SQLite is created ONLY in a fresh /tmp directory.
    # The live /app/data/isolated-public-sources.sqlite3 DB is never written.
    with tempfile.TemporaryDirectory(prefix="valyqon-v6-proof-", dir="/tmp") as folder:
        root = Path(folder).resolve()
        path = (root / "lenobl-proof.sqlite3").resolve()
        if root.parent != Path("/tmp") or path.parent != root:
            fail("BLOCKED_TEMP_STORAGE_PATH")
        db = Database(DatabaseSettings("isolated-lenobl-temp-proof", path))
        try:
            jobs = JobRepository(db, JobSettings(lease_seconds=240, heartbeat_seconds=10))
            jobs.initialize()
            store = OpportunityRepository(db)
            store.initialize()
            claim = ConnectorSyncService(jobs, catalog).enqueue("lenobl_small_public")
            handlers = HandlerRegistry()
            handlers.register(JOB_TYPE, ConnectorSyncHandler(catalog, store, max_records=3))
            claimed = Worker(jobs, handlers, job_types=(JOB_TYPE,)).run_once()
            completed = jobs.get(claim.id, scope=JobScope())
            if not claimed or completed is None or completed.state != "succeeded":
                state = completed.state if completed is not None else "missing"
                out("V6_LENOBL_TEMP_JOB_STATE", state if state in
                    ("failed", "queued", "running", "cancelled", "missing") else "unknown")
                fail("BLOCKED_LEASED_WORKER")
            stats = completed.result
            accepted = stats.get("accepted_count")
            fetched = stats.get("fetched_count")
            inserted = stats.get("inserted_count")
            if (type(accepted) is not int or not 1 <= accepted <= 3
                    or fetched != accepted or inserted != accepted
                    or stats.get("skipped_count") != 0):
                fail("BLOCKED_JOB_COUNTS")
            notices = store.read("lenobl_small_public", limit=3)
            if len(notices) != accepted:
                fail("BLOCKED_TEMP_STORAGE")
            snapshots = snapshot_catalog(catalog, store)
            found = 0
            open_count = 0
            for notice in notices:
                open_count += bool(eligible_published_deadline(
                    "lenobl_small_public", notice.deadline, now=datetime.now(timezone.utc)))
                lookup = asyncio.run(snapshots.fetch(
                    source_keys=("lenobl_small_public",),
                    search_terms=(notice.external_id,),
                    limit_per_source=3,
                ))
                if lookup.failures or not any(
                    x.identity == notice.identity and x.url == notice.url
                    for x in lookup.notices
                ):
                    fail("BLOCKED_TEMP_SEARCH")
                found += 1
                if store.upsert(notice, connector_version("lenobl_small_public")):
                    fail("BLOCKED_NONIDEMPOTENT_REPLAY")
            out("V6_LENOBL_TEMP_WORKER_COUNTS", json.dumps({
                "fetched": fetched, "accepted": accepted,
                "inserted": inserted, "searchable": found,
                "current_deadlines": open_count, "idempotent": True,
                "temporary_database_only": True
            }, sort_keys=True, separators=(",", ":")))
            out("V6_LENOBL_TEMP_WORKER", "PASS")
        finally:
            db.close()
except SystemExit:
    raise
except Exception as exc:
    name = type(exc).__name__
    if name.isascii() and name.isidentifier() and len(name) <= 64:
        out("V6_LENOBL_TEMP_EXCEPTION_CLASS", name)
    fail("BLOCKED_RUNTIME")
out("TELEGRAM_SEND_AUTHORIZED", "NO")
out("PRODUCTION_CHANGED", "NO")
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
    if ($line -match '^(?:V6_SHELL_EXECUTED|V6_EXACT_WORKER|V6_SELECTION|V6_PRIMARY_LABEL_MATCH_COUNT|V6_PINNED_IMAGE_WORKER_MATCH_COUNT|V6_LENOBL_EXISTING_IMAGE|V6_SOURCE_IMPORT_CLASS|V6_CANARY_EXCEPTION_CLASS|V6_LENOBL_BUDGET_MODE|V6_LENOBL_TEMP_WORKER|V6_LENOBL_TEMP_EXCEPTION_CLASS|V6_LENOBL_TEMP_JOB_STATE|TELEGRAM_SEND_AUTHORIZED|PRODUCTION_CHANGED)=[A-Za-z0-9_-]{1,80}$') {
        Write-Output $line
        $printed++
    } elseif ($line -match '^V6_LENOBL_TEMP_WORKER_COUNTS=(\{[^\r\n]{1,1000}\})
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
) {
        try {
            $record = $Matches[1] | ConvertFrom-Json -ErrorAction Stop
            $safe = [ordered]@{}
            foreach ($key in @('fetched','accepted','inserted','searchable','current_deadlines')) {
                $value = $record.$key
                if ($value -isnot [int] -or $value -lt 0 -or $value -gt 3) {
                    throw 'UNSAFE_TEMP_COUNT'
                }
                $safe[$key] = $value
            }
            if ($record.idempotent -ne $true -or $record.temporary_database_only -ne $true) {
                throw 'UNSAFE_TEMP_PROOF'
            }
            $safe['idempotent'] = $true
            $safe['temporary_database_only'] = $true
            Write-Output ('V6_LENOBL_TEMP_WORKER_COUNTS=' + ($safe | ConvertTo-Json -Compress))
            $printed++
        } catch {
            Write-Output 'V6_LENOBL_TEMP_WORKER_COUNTS=BLOCKED_INVALID'
            $printed++
        }
    } elseif ($line -match '^(V6_WORKER_SIX_SOURCE_AUDIT|V6_LENOBL_CANARY)=(\{[^\r\n]{1,11000}\})
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
) {
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
