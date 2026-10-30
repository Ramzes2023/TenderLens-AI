# Operator-only separate STAN/Lenobl RC build and guest boot; NOT a public deployment.
# Fresh pinned checkout and isolated Compose project, no source jobs, no sends.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-zA-Z][a-zA-Z0-9_-]{0,31}@[A-Za-z0-9.-]+$')]
    [string]$Target,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}    [string]$IdentityFile = (Join-Path $HOME '.ssh\tenderlens_vps_ed25519')
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $IdentityFile -PathType Leaf)) {
    throw 'Existing SSH identity not found; no remote action.'
}
$ssh = (Get-Command ssh.exe -ErrorAction Stop).Source
# Single-quoted here-string: remote shell and Python receive literal content.
)]
    [string]$ReviewedCommit,
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
umask 077
printf 'V6_SHELL_EXECUTED=YES\n'
fail() {
  printf 'RC_STAGE=%s\nTELEGRAM_SEND_AUTHORIZED=NO\nPRODUCTION_CHANGED=NO\n' "$1"
  exit 2
}
pin="__REVIEWED_COMMIT__"
project=valyqon-stan-lenobl-rc
tag=valyqon-stan-lenobl-rc:reviewed
stage="$HOME/valyqon-stan-lenobl-rc-stage"
case "$pin" in ''|*[!0-9a-f]*) fail BLOCKED_BAD_SHA ;; esac
[ "$(printf '%s' "$pin" | wc -c | tr -d ' ')" -eq 40 ] || fail BLOCKED_BAD_SHA
for tool in git docker python3; do command -v "$tool" >/dev/null 2>&1 || fail BLOCKED_MISSING_TOOL; done
docker compose version >/dev/null 2>&1 || fail BLOCKED_NO_COMPOSE
if ! worker="$(docker ps --filter 'label=com.docker.compose.project=valyqon-public-sources' --filter 'label=com.docker.compose.service=worker-v6' --format '{{.ID}}' 2>/dev/null)"; then fail BLOCKED_OLD_WORKER_ACCESS; fi
count="$(printf '%s\n' "$worker" | awk 'NF{n++} END{print n+0}')"
printf 'V6_PRIMARY_LABEL_MATCH_COUNT=%s\n' "$count"
[ "$count" -eq 1 ] || fail BLOCKED_OLD_WORKER_COUNT
original="$(docker inspect -f '{{.Config.Image}}' "$worker" 2>/dev/null)" || fail BLOCKED_OLD_WORKER_IMAGE
[ "$original" = valyqon-public-sources:v6-fe4c66bbd553 ] || fail BLOCKED_OLD_WORKER_IMAGE
printf 'V6_EXACT_WORKER=VERIFIED_UNIQUE_PINNED_IMAGE\n'
[ ! -e "$stage" ] && [ ! -L "$stage" ] || fail BLOCKED_STAGE_ALREADY_EXISTS
[ -z "$(docker ps -aq --filter "label=com.docker.compose.project=$project" 2>/dev/null)" ] || fail BLOCKED_PROJECT_EXISTS
if docker volume inspect "$project"_stan_lenobl_rc_data >/dev/null 2>&1; then fail BLOCKED_VOLUME_EXISTS; fi
if docker image inspect "$tag" >/dev/null 2>&1; then fail BLOCKED_IMAGE_EXISTS; fi
for filesystem in "$HOME" /; do
  available="$(df -Pk "$filesystem" 2>/dev/null | awk 'NR==2{print $4}')"
  case "$available" in ''|*[!0-9]*) fail BLOCKED_DISK_QUERY ;; esac
  [ "$available" -ge 3145728 ] || fail BLOCKED_DISK_LT_3G
done
mkdir -m 700 "$stage" || fail BLOCKED_STAGE_CREATE
if ! git -c credential.helper= clone --quiet --filter=blob:none --no-checkout \
  'https://github.com/Ramzes2023/TenderLens-AI.git' "$stage/repo" >"$stage/clone.log" 2>&1; then fail BLOCKED_GIT_FETCH; fi
if ! git -C "$stage/repo" checkout --quiet --detach "$pin" >"$stage/checkout.log" 2>&1; then fail BLOCKED_PIN_CHECKOUT; fi
[ "$(git -C "$stage/repo" rev-parse HEAD)" = "$pin" ] || fail BLOCKED_WRONG_PIN
[ -z "$(git -C "$stage/repo" status --porcelain)" ] || fail BLOCKED_DIRTY_CHECKOUT
manifest="$stage/repo/ops/public_sources/compose.stan-lenobl-rc.yaml"
[ -f "$manifest" ] || fail BLOCKED_NO_MANIFEST
grep -q 'VALYQON_STAN_LENOBL_RC_MODE: "true"' "$manifest" || fail BLOCKED_NO_EXPLICIT_RC_MODE
if ! docker compose -p "$project" -f "$manifest" config --format json >"$stage/config.json" 2>"$stage/config.log"; then fail BLOCKED_COMPOSE_CONFIG; fi
if ! python3 - "$stage/config.json" <<'PY'
import json,sys
from pathlib import Path
try:
    m=json.loads(Path(sys.argv[1]).read_text())
    s=m["services"]; env=s["guest-sources"]["environment"]
    assert set(s)=={"guest-sources","worker","enqueue"}
    assert set(m["volumes"])=={"stan_lenobl_rc_data"}
    assert set(m["networks"])=={"private_guest","publisher_outbound"}
    assert m["networks"]["private_guest"]["internal"] is True
    assert set(s["guest-sources"]["networks"])=={"private_guest"}
    assert set(s["worker"]["networks"])=={"publisher_outbound"}
    assert s["enqueue"]["network_mode"]=="none"
    assert all(not x.get("ports") and x.get("restart")=="no" for x in s.values())
    assert all(x["image"]=="valyqon-stan-lenobl-rc:reviewed" for x in s.values())
    assert all(len(x["volumes"])==1 and x["volumes"][0]["source"]=="stan_lenobl_rc_data" and x["volumes"][0]["target"]=="/app/data" for x in s.values())
    required={"DATABASE_URL":"sqlite:////app/data/isolated-public-sources.sqlite3",
        "VALYQON_STAN_LENOBL_RC_MODE":"true",
        "MIKROTON_TENDER_ENABLED":"false",
        "STAN_COMMERCIAL_PUBLIC_ENABLED":"true","LENOBL_SMALL_PUBLIC_ENABLED":"true",
        "MONITORING_ENABLED":"false","VALYQON_EMAIL_MODE":"disabled",
        "TELEGRAM_BOT_TOKEN":"","OUTBOUND_PROXY_URL":"",
        "VALYQON_RU_BACKGROUND_CATALOG_ENABLED":"false"}
    assert all(env[k]==v for k,v in required.items())
except (AssertionError,KeyError,TypeError,ValueError):
    raise SystemExit(2)
PY
then fail BLOCKED_ISOLATION_CONFIG; fi
printf 'RC_STAGE_PROJECT=VERIFIED_SEPARATE\n'
if ! docker compose -p "$project" -f "$manifest" build --quiet worker >"$stage/build.log" 2>&1; then fail BLOCKED_BUILD; fi
printf 'RC_STAGE_IMAGE=SEPARATE_BUILT\n'
if ! docker compose -p "$project" -f "$manifest" up --no-build --no-deps -d guest-sources worker >"$stage/boot.log" 2>&1; then fail BLOCKED_BOOT; fi
guest="$(docker compose -p "$project" -f "$manifest" ps -q guest-sources)"
worker_rc="$(docker compose -p "$project" -f "$manifest" ps -q worker)"
[ -n "$guest" ] && [ -n "$worker_rc" ] || fail BLOCKED_STAGE_CONTAINERS
healthy=NO
n=0
while [ "$n" -lt 40 ]; do
  status="$(docker inspect -f '{{.State.Health.Status}}' "$guest" 2>/dev/null || :)"
  if [ "$status" = healthy ]; then healthy=YES; break; fi
  n=$((n+1))
  sleep 2
done
[ "$healthy" = YES ] || fail BLOCKED_GUEST_HEALTH
[ "$(docker inspect -f '{{.State.Running}}' "$worker_rc" 2>/dev/null)" = true ] || fail BLOCKED_WORKER_STOPPED
if ! docker exec "$guest" python -c "import json;from urllib.request import urlopen;r=urlopen('http://127.0.0.1:8101/_internal/health',timeout=4);d=json.load(r);assert r.status==200 and d.get('database')=='isolated' and d.get('status')=='ready'" >"$stage/health.log" 2>&1; then fail BLOCKED_PRIVATE_HTTP; fi
printf 'RC_STAGE_GUEST=HEALTHY_PRIVATE_ONLY\nRC_STAGE_WORKER=RUNNING_ISOLATED_ONLY\nRC_STAGE_E2E=NOT_RUN\nRC_STAGE=BOOT_PASS\n'
printf 'TELEGRAM_SEND_AUTHORIZED=NO\nPRODUCTION_CHANGED=NO\n'
: # RC_STAGE_END
'@
# Windows PowerShell pipes add CRLF; dash/sh treats CR as an invalid option.
# Send exact LF-only ASCII script over process stdin, not a native pipeline.
$remote = $remote.Replace('__REVIEWED_COMMIT__', $ReviewedCommit)
$remoteLf = $remote.Replace("`r`n", "`n").Replace("`r", "`n").TrimEnd([char]10) + "`n"
if ($remoteLf.Contains("`r") -or -not $remoteLf.StartsWith("set -eu`n") -or
    -not $remoteLf.EndsWith("`n: # RC_STAGE_END`n")) {
    throw "RC_STAGE_OPERATOR=BLOCKED_UNSAFE_SHELL_STREAM"
}
if ($IdentityFile.Contains('"')) {
    throw "RC_STAGE_OPERATOR=BLOCKED_UNSAFE_IDENTITY_PATH"
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
    if (-not $process.Start()) { throw "RC_STAGE_OPERATOR=SSH_START_FAILED" }
    # Drain BOTH streams concurrently to avoid SSH/Docker buffer deadlocks.
    # Never show raw stderr, which may contain host details or secrets.
    $outTask = $process.StandardOutput.ReadToEndAsync()
    $errTask = $process.StandardError.ReadToEndAsync()
    try {
        $process.StandardInput.Write($remoteLf)
    } finally {
        $process.StandardInput.Close()
    }
    if (-not $process.WaitForExit(900000)) {
        $process.Kill()
        throw "RC_STAGE_OPERATOR=SSH_OR_SOURCE_TIMEOUT"
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
    if ($line -match '^(?:V6_SHELL_EXECUTED|V6_EXACT_WORKER|V6_PRIMARY_LABEL_MATCH_COUNT|RC_STAGE|RC_STAGE_PROJECT|RC_STAGE_IMAGE|RC_STAGE_GUEST|RC_STAGE_WORKER|RC_STAGE_E2E|TELEGRAM_SEND_AUTHORIZED|PRODUCTION_CHANGED)=[A-Za-z0-9_-]{1,80}$') {
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
    throw "RC_STAGE_OPERATOR_EXIT=$status (no deployment performed)"
}
