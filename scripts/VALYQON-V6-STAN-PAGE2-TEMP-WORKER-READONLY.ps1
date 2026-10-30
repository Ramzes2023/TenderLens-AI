# Existing V6 STAN second-page leased Worker acceptance in disposable /tmp database. Writes only a disposable /tmp SQLite DB, never the live source DB or deploy.
# Example: .\scripts\VALYQON-V6-STAN-PAGE2-TEMP-WORKER-READONLY.ps1 -Target 'ubuntu@<your-vps-host>'
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
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

SOURCE = "stan_commercial_public"
DB_PATH = "/app/data/isolated-public-sources.sqlite3"

def out(key, value):
    print(key + "=" + str(value), flush=True)

def fail(reason):
    out("V6_STAN_TEMP_WORKER", reason)
    out("TELEGRAM_SEND_AUTHORIZED", "NO")
    out("PRODUCTION_CHANGED", "NO")
    raise SystemExit(2)

EXPECTED = {
    "DATABASE_URL": "sqlite:////app/data/isolated-public-sources.sqlite3",
    "VALYQON_ISOLATED_PUBLIC_SOURCES_ENABLED": "true",
    "STAN_COMMERCIAL_PUBLIC_ENABLED": "true",
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
    import app.sources.stan_commercial_public as stan_runtime
    from app.sources.stan_commercial_public import StanCommercialPublicSource
    from app.api.public_source_deadline import eligible_published_deadline
    from app.database.backend import Database
    from app.database.config import DatabaseSettings
    from app.jobs import HandlerRegistry, JobRepository, JobSettings
    from app.jobs.models import JobScope
    from app.jobs.worker import Worker
    from app.monitoring.config import MonitoringSettings
    from app.sources.catalog import build_source_catalog
    from app.sources.ingestion import JOB_TYPE, ConnectorSyncHandler, ConnectorSyncService, connector_version
    from app.sources.opportunities import OpportunityRepository
    from app.sources.snapshots import snapshot_catalog
except Exception as exc:
    out("V6_STAN_TEMP_EXCEPTION_CLASS", type(exc).__name__)
    fail("BLOCKED_IMPORT")

try:
    old_fetch = inspect.getsource(StanCommercialPublicSource.fetch)
    old_list = inspect.getsource(stan_runtime.parse_list)
    if not (
        stan_runtime.__file__ == "/app/app/sources/stan_commercial_public.py"
        and stan_runtime.HOST == "stantorgi.ru"
        and stan_runtime.LIST_URL == "https://stantorgi.ru/etp"
        and stan_runtime.MAX_DETAILS == 2
        and 'if len(valid) < MAX_DETAILS:' in old_list
        and 'if not c["eis"] and len(c["numbers"])==1 and len(c["titles"])==1:' in old_list
        and "listing = await client.get(LIST_URL)" in old_fetch
        and "for number,title,url in parse_list(listing.content)[:cap]:" in old_fetch
        and "if _policy.get() is None else nullcontext()" in old_fetch
    ):
        fail("BLOCKED_UNEXPECTED_LEGACY_CODE")
except (AttributeError, OSError, TypeError):
    fail("BLOCKED_LEGACY_INTROSPECTION")

# This one-off Python process routes ONLY the old module's first official
# listing GET to the publisher's literal official page 2, while leaving
# canonical detail URLs and all original-source verification unchanged.
# The daemon process and installed image are NOT patched or restarted.
real_client = stan_runtime.source_client
if not getattr(real_client, "__module__", "").startswith("app.sources.http"):
    fail("BLOCKED_UNEXPECTED_HTTP_CLIENT")
stan_runtime.MAX_DETAILS = 1
@asynccontextmanager
async def page_two_only_client(**kwargs):
    if kwargs.get("trust_env") is not False or kwargs.get("follow_redirects") is not False:
        raise ValueError("Unsupported STAN outbound client settings")
    async with real_client(**kwargs) as client:
        class Restrained:
            listing_requests = 0
            detail_requests = 0
            async def get(self, url):
                if url == "https://stantorgi.ru/etp":
                    self.listing_requests += 1
                    if self.listing_requests != 1:
                        raise ValueError("Unexpected repeated STAN listing")
                    return await client.get("https://stantorgi.ru/etp?page=2")
                if stan_runtime.canonical(url) != url:
                    raise ValueError("Invalid STAN original detail URL")
                self.detail_requests += 1
                if self.detail_requests > 1:
                    raise ValueError("Unexpected STAN detail count")
                return await client.get(url)
        yield Restrained()
stan_runtime.source_client = page_two_only_client
out("V6_STAN_PAGE", "2")
out("V6_STAN_ROUTE", "EPHEMERAL_OFFICIAL_PAGE_TWO")

try:
    catalog = build_source_catalog(MonitoringSettings(
        enabled=False, interval_seconds=600, max_items=3,
        max_notifications_per_cycle=5, request_timeout=25,
        eis_rss_urls=(), ca_bundle_file=None, profile_feeds_enabled=False,
        stan_commercial_public_enabled=True,
    ))
    if SOURCE not in catalog.enabled_keys:
        fail("BLOCKED_CATALOG")

    # Only disposable isolated SQLite; no SQL connection to DB_PATH.
    with tempfile.TemporaryDirectory(prefix="valyqon-stan-page2-", dir="/tmp") as folder:
        root = Path(folder).resolve()
        path = (root / "stan-page2-proof.sqlite3").resolve()
        if root.parent != Path("/tmp") or path.parent != root:
            fail("BLOCKED_TEMP_DB_PATH")
        db = Database(DatabaseSettings("isolated-stan-temp-proof", path))
        try:
            jobs = JobRepository(db, JobSettings(lease_seconds=240, heartbeat_seconds=10))
            jobs.initialize()
            store = OpportunityRepository(db)
            store.initialize()
            job = ConnectorSyncService(jobs, catalog).enqueue(SOURCE)
            handlers = HandlerRegistry()
            handlers.register(JOB_TYPE, ConnectorSyncHandler(catalog, store, max_records=3))
            claimed = Worker(jobs, handlers, job_types=(JOB_TYPE,)).run_once()
            completed = jobs.get(job.id, scope=JobScope())
            if not claimed or completed is None or completed.state != "succeeded":
                state = completed.state if completed is not None else "missing"
                out("V6_STAN_TEMP_JOB_STATE", state if state in (
                    "failed", "queued", "running", "cancelled", "missing") else "unknown")
                fail("BLOCKED_LEASED_WORKER")
            stats = completed.result
            fetched = stats.get("fetched_count")
            accepted = stats.get("accepted_count")
            inserted = stats.get("inserted_count")
            if (type(accepted) is not int or fetched != 1 or accepted != 1
                    or inserted != 1 or stats.get("skipped_count") != 0):
                fail("BLOCKED_JOB_COUNTS")
            rows = store.read(SOURCE, limit=3)
            if len(rows) != 1:
                fail("BLOCKED_TEMP_SQL")
            notice = rows[0]
            if not notice.customer or not eligible_published_deadline(
                    SOURCE, notice.deadline, now=datetime.now(timezone.utc)):
                fail("BLOCKED_NO_VERIFIED_CURRENT_DEADLINE")
            look = asyncio.run(snapshot_catalog(catalog, store).fetch(
                source_keys=(SOURCE,),
                search_terms=(notice.external_id,),
                limit_per_source=3,
            ))
            if look.failures or not any(
                x.identity == notice.identity and x.url == notice.url
                for x in look.notices
            ):
                fail("BLOCKED_TEMP_USER_SEARCH")
            if store.upsert(notice, connector_version(SOURCE)):
                fail("BLOCKED_NONIDEMPOTENT_REPLAY")
            out("V6_STAN_TEMP_WORKER_COUNTS", json.dumps({
                "fetched": 1, "accepted": 1, "inserted": 1,
                "searchable": 1, "current_deadlines": 1,
                "idempotent": True, "temporary_database_only": True
            }, separators=(",", ":"), sort_keys=True))
            out("V6_STAN_TEMP_WORKER", "PASS")
        finally:
            db.close()
except SystemExit:
    raise
except Exception as exc:
    name = type(exc).__name__
    if name.isascii() and name.isidentifier() and len(name) <= 64:
        out("V6_STAN_TEMP_EXCEPTION_CLASS", name)
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
    if ($line -match '^(?:V6_SHELL_EXECUTED|V6_EXACT_WORKER|V6_SELECTION|V6_PRIMARY_LABEL_MATCH_COUNT|V6_PINNED_IMAGE_WORKER_MATCH_COUNT|V6_LENOBL_EXISTING_IMAGE|V6_SOURCE_IMPORT_CLASS|V6_CANARY_EXCEPTION_CLASS|V6_STAN_PAGE|V6_STAN_TEMP_WORKER|V6_STAN_TEMP_EXCEPTION_CLASS|V6_STAN_TEMP_JOB_STATE|V6_STAN_ROUTE|TELEGRAM_SEND_AUTHORIZED|PRODUCTION_CHANGED)=[A-Za-z0-9_-]{1,80}$') {
        Write-Output $line
        $printed++
    } elseif ($line -match '^V6_STAN_TEMP_WORKER_COUNTS=(\{[^\r\n]{1,1000}\})$') {
        try {
            $record = $Matches[1] | ConvertFrom-Json -ErrorAction Stop
            $safe = [ordered]@{}
            foreach ($key in @('fetched','accepted','inserted','searchable','current_deadlines')) {
                $value = $record.$key
                if (($value -isnot [int] -and $value -isnot [long]) -or $value -lt 0 -or $value -gt 3) {
                    throw 'UNSAFE_TEMP_COUNT'
                }
                $safe[$key] = $value
            }
            if ($record.idempotent -ne $true -or $record.temporary_database_only -ne $true) {
                throw 'UNSAFE_TEMP_PROOF'
            }
            $safe['idempotent'] = $true
            $safe['temporary_database_only'] = $true
            Write-Output ('V6_STAN_TEMP_WORKER_COUNTS=' + ($safe | ConvertTo-Json -Compress))
            $printed++
        } catch {
            Write-Output 'V6_STAN_TEMP_WORKER_COUNTS=BLOCKED_INVALID'
            $printed++
        }
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
