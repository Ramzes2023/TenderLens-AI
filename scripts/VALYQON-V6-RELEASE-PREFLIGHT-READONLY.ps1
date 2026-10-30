# Exact V6 read-only release preflight: pinned image, isolated volume, settings, disk, legacy signatures.
# Does not write source DB, build images, restart services or send notifications.
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
import inspect
import os
import shutil
import stat
from pathlib import Path

def out(key, value):
    print(key + "=" + value, flush=True)

def fail(code):
    out("V6_PREFLIGHT", code)
    out("TELEGRAM_SEND_AUTHORIZED", "NO")
    out("PRODUCTION_CHANGED", "NO")
    raise SystemExit(2)

EXPECTED = {
    "DATABASE_URL": "sqlite:////app/data/isolated-public-sources.sqlite3",
    "VALYQON_ISOLATED_PUBLIC_SOURCES_ENABLED": "true",
    "STAN_COMMERCIAL_PUBLIC_ENABLED": "true",
    "LENOBL_SMALL_PUBLIC_ENABLED": "true",
    "VALYQON_CONNECTOR_MAX_RECORDS": "30",
    "MONITORING_ENABLED": "false",
    "VALYQON_EMAIL_MODE": "disabled",
    "VALYQON_RESTRICT_PAID_SOURCE_DETAILS": "true",
}
if any(os.environ.get(key) != value for key, value in EXPECTED.items()):
    fail("BLOCKED_UNSAFE_ENV")
if (os.environ.get("TELEGRAM_BOT_TOKEN", "")
        or os.environ.get("OUTBOUND_PROXY_URL", "")
        or os.environ.get("VALYQON_RU_BACKGROUND_CATALOG_ENABLED", "false") != "false"):
    fail("BLOCKED_EXTERNAL_SEND_OR_PROXY")
out("V6_PREFLIGHT_ENV", "ISOLATED_NO_SEND")
out("V6_PREFLIGHT_IMAGE", "PINNED_V6")

path = Path("/app/data/isolated-public-sources.sqlite3")
try:
    if not Path("/app/data").is_mount():
        fail("BLOCKED_NOT_MOUNTED")
    original = path.resolve(strict=True)
    if original != path or not stat.S_ISREG(original.stat().st_mode):
        fail("BLOCKED_UNSAFE_DATABASE_PATH")
    if original.stat().st_size < 4096:
        fail("BLOCKED_DATABASE_TOO_SMALL")
    out("V6_PREFLIGHT_VOLUME", "EXISTING_MOUNTED_DATABASE")
    if shutil.disk_usage("/app/data").free < 536870912:
        fail("BLOCKED_INSUFFICIENT_DISK")
    out("V6_PREFLIGHT_DISK", "ABOVE_512M_FREE")
except SystemExit:
    raise
except (OSError, RuntimeError, ValueError):
    fail("BLOCKED_VOLUME_INSPECTION")

try:
    import app.sources.stan_commercial_public as stan
    import app.sources.lenobl_small_public as lenobl
    if not (
        stan.__file__ == "/app/app/sources/stan_commercial_public.py"
        and stan.MAX_DETAILS == 2
        and 'if len(valid) < MAX_DETAILS:' in inspect.getsource(stan.parse_list)
        and 'listing = await client.get(LIST_URL)' in inspect.getsource(stan.StanCommercialPublicSource.fetch)
        and lenobl.__file__ == "/app/app/sources/lenobl_small_public.py"
        and lenobl.MAX_DETAILS == 6
        and 'remaining_details' not in inspect.getsource(lenobl.LenoblSmallPublicSource.fetch)
    ):
        fail("BLOCKED_UNEXPECTED_SOURCE_IMAGE")
    out("V6_PREFLIGHT_CODE", "LEGACY_PATCHES_REQUIRED")
except SystemExit:
    raise
except (ImportError, AttributeError, OSError, TypeError) as exc:
    name = type(exc).__name__
    if name.isidentifier() and name.isascii() and len(name) <= 64:
        out("V6_PREFLIGHT_EXCEPTION_CLASS", name)
    fail("BLOCKED_SOURCE_INSPECTION")

out("V6_PREFLIGHT", "READONLY_READY_FOR_SEPARATE_STAGE")
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
    if ($line -match '^(?:V6_SHELL_EXECUTED|V6_EXACT_WORKER|V6_SELECTION|V6_PRIMARY_LABEL_MATCH_COUNT|V6_PINNED_IMAGE_WORKER_MATCH_COUNT|V6_LENOBL_EXISTING_IMAGE|V6_SOURCE_IMPORT_CLASS|V6_CANARY_EXCEPTION_CLASS|V6_PREFLIGHT|V6_PREFLIGHT_IMAGE|V6_PREFLIGHT_ENV|V6_PREFLIGHT_VOLUME|V6_PREFLIGHT_DISK|V6_PREFLIGHT_CODE|V6_PREFLIGHT_EXCEPTION_CLASS|TELEGRAM_SEND_AUTHORIZED|PRODUCTION_CHANGED)=[A-Za-z0-9_-]{1,80}$') {
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
