# Read-only exact V6 STAN first-party publisher canary. No rebuild/deploy/restart or DB writes.
# Example: .\scripts\VALYQON-V6-STAN-EXISTING-IMAGE-READONLY.ps1 -Target 'ubuntu@<your-vps-host>'
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
from datetime import datetime, timezone

EXPECTED = {
    "DATABASE_URL": "sqlite:////app/data/isolated-public-sources.sqlite3",
    "VALYQON_ISOLATED_PUBLIC_SOURCES_ENABLED": "true",
    "STAN_COMMERCIAL_PUBLIC_ENABLED": "true",
    "VALYQON_CONNECTOR_MAX_RECORDS": "30",
    "MONITORING_ENABLED": "false",
    "VALYQON_EMAIL_MODE": "disabled",
    "VALYQON_RESTRICT_PAID_SOURCE_DETAILS": "true",
}
def status(label):
    print("V6_STAN_STATUS=" + label, flush=True)
    print("TELEGRAM_SEND_AUTHORIZED=NO", flush=True)
    print("PRODUCTION_CHANGED=NO", flush=True)

if any(os.environ.get(k) != v for k, v in EXPECTED.items()):
    status("BLOCKED_UNSAFE_ENV")
    raise SystemExit(2)
if (os.environ.get("TELEGRAM_BOT_TOKEN", "")
        or os.environ.get("OUTBOUND_PROXY_URL", "")
        or os.environ.get("VALYQON_RU_BACKGROUND_CATALOG_ENABLED", "false") != "false"):
    status("BLOCKED_NOTIFICATION_OR_PROXY")
    raise SystemExit(2)

try:
    import httpx
    import app.sources.stan_commercial_public as stan_runtime
    from app.sources.http import FetchPolicy, bounded_fetch, source_client
    from app.sources.stan_commercial_public import (
        HOST, LIST_URL, MAX_DETAILS, MAX_BYTES,
        parse_list, independently_verified_commercial_metadata,
    )
    from app.sources.models import TenderNotice
    from app.sources.opportunities import validate_notice
    from app.api.public_source_deadline import eligible_published_deadline
except Exception as exc:
    print("V6_STAN_EXCEPTION_CLASS=" + type(exc).__name__, flush=True)
    status("BLOCKED_IMPORT")
    raise SystemExit(2)

if HOST != "stantorgi.ru" or LIST_URL != "https://stantorgi.ru/etp" or MAX_DETAILS != 2:
    status("BLOCKED_UNEXPECTED_ADAPTER")
    raise SystemExit(2)
# The existing pinned image requires TWO commercial entries in its listing.
# A mixed first-party 223-FZ/commercial page may legitimately have just ONE.
# Change only this disposable docker-exec process; never change real Worker.
try:
    legacy_code = inspect.getsource(stan_runtime.parse_list)
    legacy_shape = (
        stan_runtime.__file__ == "/app/app/sources/stan_commercial_public.py"
        and 'if len(valid) < MAX_DETAILS:' in legacy_code
        and 'if not c["eis"] and len(c["numbers"])==1 and len(c["titles"])==1:' in legacy_code
    )
except (AttributeError, OSError, TypeError):
    legacy_shape = False
if not legacy_shape:
    status("BLOCKED_UNEXPECTED_LEGACY_PARSER")
    raise SystemExit(2)
stan_runtime.MAX_DETAILS = 1
print("V6_STAN_LISTING_MODE=LEGACY_SINGLE_INPROCESS", flush=True)

async def canary():
    policy = FetchPolicy(frozenset({HOST}), max_requests=3, max_bytes=MAX_BYTES)
    counts = {"valid_listing": 0, "valid_details": 0, "detail_rejected": 0,
              "current_deadlines": 0, "http_requests": 0}
    phase = "listing"
    label = "UNKNOWN"
    error_class = "none"
    reason = "none"
    try:
        with bounded_fetch(policy):
            async with source_client(
                timeout=20, trust_env=False, follow_redirects=False,
                headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0"},
            ) as client:
                page = await client.get(LIST_URL)
                page.raise_for_status()
                if "html" not in page.headers.get("content-type", "").lower():
                    raise ValueError("Non-HTML publisher listing")
                phase = "parse_list"
                cards = parse_list(page.content)
                counts["valid_listing"] = len(cards)
                phase = "detail"
                for number, title, url in cards[:2]:
                    try:
                        detail = await client.get(url)
                        detail.raise_for_status()
                        if "html" not in detail.headers.get("content-type", "").lower():
                            raise ValueError("Non-HTML official detail")
                        metadata = independently_verified_commercial_metadata(
                            detail.content, number, title, url)
                        notice = TenderNotice(
                            source="stan_commercial_public", external_id=number,
                            tender_number=number, title=title, url=url, **metadata)
                        validate_notice(notice, "stan_commercial_public")
                        counts["valid_details"] += 1
                        counts["current_deadlines"] += bool(
                            eligible_published_deadline(
                                "stan_commercial_public", notice.deadline,
                                now=datetime.now(timezone.utc)))
                    except (ValueError, httpx.HTTPStatusError):
                        counts["detail_rejected"] += 1
                label = ("CANDIDATE_ONLY" if counts["valid_details"] > 0
                         else "BLOCKED_NO_VERIFIED_DETAILS")
    except Exception as exc:
        name = type(exc).__name__
        error_class = name if (name.isascii() and name.isidentifier()
                               and len(name) <= 64) else "UnknownException"
        value = getattr(exc, "reason", None)
        reason = value if value in (
            "network", "timeout", "policy", "http_status", "public_ip",
            "tls_certificate", "response_size", "http_transient") else "none"
        label = "BLOCKED_FIRSTPARTY"
    counts["http_requests"] = policy.requests
    print("V6_STAN_CANARY=" + json.dumps({
        "result": label, "failure_stage": phase,
        "exception_class": error_class, "transport_reason": reason,
        **counts,
        "worker_sql_verified": False, "telegram_sent": False,
    }, sort_keys=True, separators=(",", ":")), flush=True)
    status("READONLY_DIAGNOSED")

asyncio.run(asyncio.wait_for(canary(), timeout=95))
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
    if ($line -match '^(?:V6_SHELL_EXECUTED|V6_EXACT_WORKER|V6_SELECTION|V6_PRIMARY_LABEL_MATCH_COUNT|V6_PINNED_IMAGE_WORKER_MATCH_COUNT|V6_LENOBL_EXISTING_IMAGE|V6_SOURCE_IMPORT_CLASS|V6_CANARY_EXCEPTION_CLASS|V6_LENOBL_BUDGET_MODE|V6_STAN_STATUS|V6_STAN_EXCEPTION_CLASS|V6_STAN_LISTING_MODE|TELEGRAM_SEND_AUTHORIZED|PRODUCTION_CHANGED)=[A-Za-z0-9_-]{1,80}$') {
        Write-Output $line
        $printed++
    } elseif ($line -match '^V6_STAN_CANARY=(\{[^\r\n]{1,2500}\})$') {
        try {
            $json = $Matches[1] | ConvertFrom-Json -ErrorAction Stop
            $clean = [ordered]@{}
            foreach ($key in @('valid_listing','valid_details','detail_rejected','current_deadlines','http_requests')) {
                $number = $json.$key
                if (($number -isnot [int] -and $number -isnot [long]) -or
                    $number -lt 0 -or $number -gt 3) {
                    throw 'INVALID_STAN_COUNT'
                }
                $clean[$key] = $number
            }
            foreach ($key in @('result','failure_stage','exception_class','transport_reason')) {
                $value = [string]$json.$key
                if ($value -notmatch '^[a-zA-Z][a-zA-Z0-9_]{0,63}$') { throw 'INVALID_STAN_STATUS' }
                $clean[$key] = $value
            }
            if ($json.worker_sql_verified -ne $false -or $json.telegram_sent -ne $false) {
                throw 'UNSAFE_STAN_STATUS'
            }
            $clean['worker_sql_verified'] = $false
            $clean['telegram_sent'] = $false
            Write-Output ('V6_STAN_CANARY=' + ($clean | ConvertTo-Json -Compress))
            $printed++
        } catch {
            Write-Output 'V6_STAN_CANARY=BLOCKED_INVALID'
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
