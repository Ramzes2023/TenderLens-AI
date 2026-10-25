# Read-only, main-only operator audit for five blocked Russian sources.
# This script cannot enable production, touch a production DB, or send Telegram.
# Real Worker acceptance is optional, uses disposable SQLite and fixed modules.
[CmdletBinding()]
param(
    [switch]$RunLiveProofs
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$py = $null
foreach ($path in @(
    (Join-Path $repo '.venv\Scripts\python.exe'),
    (Join-Path $repo 'venv\Scripts\python.exe')
)) {
    if (Test-Path -LiteralPath $path -PathType Leaf) { $py = $path; break }
}
if (-not $py) {
    $command = Get-Command python -ErrorAction SilentlyContinue
    if ($command) { $py = $command.Source }
}
if (-not $py) {
    Write-Output 'RU_FIVE_AUDIT=NO_PYTHON'
    exit 2
}

# Do not execute unreviewed PR code on an operator machine or self-hosted RU runner.
$branchLines = @(& git -C $repo branch --show-current 2>$null)
if ($LASTEXITCODE -ne 0 -or $branchLines.Count -ne 1 -or $branchLines[0].Trim() -cne 'main') {
    Write-Output 'RU_FIVE_AUDIT=REJECTED_NOT_REVIEWED_MAIN'
    exit 2
}

# Exact module allowlist: no source name, URL, subprocess or arbitrary endpoint
# accepted from the user or from a network response.
$proofs = @(
    @{ Name = 'ingushetia'; Script = 'ci_ru_ingushetia_live_worker.py'; Module = 'scripts.ci_ru_ingushetia_live_worker'; Marker = 'RU_INGUSHETIA_LIVE_ACCEPTANCE=PASS' },
    @{ Name = 'chechnya'; Script = 'ci_ru_chechnya_eis_real_worker.py'; Module = 'scripts.ci_ru_chechnya_eis_real_worker'; Marker = 'RU_CHECHNYA_EIS_STRICT_LIVE=PASS_LOCAL_CAPTURE_ONLY' },
    @{ Name = 'roseltorg'; Script = 'ci_ru_roseltorg_real_worker.py'; Module = 'scripts.ci_ru_roseltorg_real_worker'; Marker = 'RU_ROSELTORG_REAL_WORKER=PASS' },
    @{ Name = 'gpb'; Script = 'ci_ru_gpb_public_worker.py'; Module = 'scripts.ci_ru_gpb_public_worker'; Marker = 'RU_GPB_REAL_WORKER=PASS' },
    @{ Name = 'tektorg'; Script = 'ci_ru_tektorg_fenced_acceptance.py'; Module = 'scripts.ci_ru_tektorg_fenced_acceptance'; Marker = 'RU_TEKTORG_FENCED_REAL=PASS' }
)

$failures = 0
Push-Location -LiteralPath $repo
try {
    # Existing audited Python routine uses exact first-party hosts, public-IP
    # DNS checks, pinned TLS, no redirects, no credentials and bounded reads.
    $probeOutput = @(& $py -B -m scripts.ru_trusted_live_probe priority_five_network 2>&1 | ForEach-Object { [string]$_ })
    $probeExit = $LASTEXITCODE
    foreach ($line in $probeOutput) {
        # Emit only first-party fixed source status and aggregate counters,
        # never exception messages, response bodies, URLs, tokens or chat IDs.
        if ($line -match '^RU_FIVE_SOURCE=') {
            try {
                $observation = ($line.Substring('RU_FIVE_SOURCE='.Length) | ConvertFrom-Json)
                if ($observation.source -cin @('ingushetia', 'chechnya', 'roseltorg', 'gpb', 'tektorg')) {
                    $status = $observation.status
                    if ($status -cin @('HTTPS_VISIBLE_NOT_INGESTED', 'HTTP_REACHABLE_NON200', 'BLOCKED')) {
                        Write-Output ('RU_FIVE_NETWORK_' + $observation.source.ToUpperInvariant() + '=' + $status)
                    }
                }
            } catch { Write-Output 'RU_FIVE_NETWORK=REDACTED_INVALID_OBSERVATION' }
        } elseif ($line -match '^RU_FIVE_FIRSTPARTY_HTTPS_VISIBLE=[0-5]/5$') {
            Write-Output $line
        }
    }
    if ($probeExit -ne 0) { $failures++ }
    Write-Output ('RU_FIVE_NETWORK_AUDIT=' + $(if ($probeExit -eq 0) { 'PASS_REACHABILITY_ONLY' } else { 'BLOCKED' }))

    if ($RunLiveProofs) {
        foreach ($entry in $proofs) {
            $label = $entry.Name.ToUpperInvariant()
            $modulePath = Join-Path (Join-Path $repo 'scripts') $entry.Script
            if (-not (Test-Path -LiteralPath $modulePath -PathType Leaf)) {
                # Ingushetia/Chechnya/Roseltorg feature PRs may not yet be in main.
                Write-Output ('RU_FIVE_ORIGINAL_' + $label + '=NOT_IN_MAIN')
                $failures++
                continue
            }
            # Explicitly suppress all inherited Chechnya authorized Telegram
            # test credentials; use separate opt-in operator test for real ACK.
            $priorBotToken = [Environment]::GetEnvironmentVariable('RU_CHECHNYA_E2E_TEST_BOT_TOKEN', 'Process')
            $priorChatId = [Environment]::GetEnvironmentVariable('RU_CHECHNYA_E2E_TEST_CHAT_ID', 'Process')
            try {
                [Environment]::SetEnvironmentVariable('RU_CHECHNYA_E2E_TEST_BOT_TOKEN', $null, 'Process')
                [Environment]::SetEnvironmentVariable('RU_CHECHNYA_E2E_TEST_CHAT_ID', $null, 'Process')
                $safeCapture = @(& $py -B -m $entry.Module 2>&1 | ForEach-Object { [string]$_ })
                $proofExit = $LASTEXITCODE
                if ($proofExit -eq 0 -and $safeCapture -ccontains $entry.Marker) {
                    Write-Output ('RU_FIVE_ORIGINAL_' + $label + '=PASS_ISOLATED_WORKER_SQL')
                } else {
                    Write-Output ('RU_FIVE_ORIGINAL_' + $label + '=BLOCKED_NO_ACCEPTED_CURRENT_ORIGINAL')
                    $failures++
                }
            } catch {
                Write-Output ('RU_FIVE_ORIGINAL_' + $label + '=BLOCKED_EXECUTION')
                $failures++
            } finally {
                [Environment]::SetEnvironmentVariable('RU_CHECHNYA_E2E_TEST_BOT_TOKEN', $priorBotToken, 'Process')
                [Environment]::SetEnvironmentVariable('RU_CHECHNYA_E2E_TEST_CHAT_ID', $priorChatId, 'Process')
            }
        }
    } else {
        Write-Output 'RU_FIVE_SOURCE_WORKER_TESTS=NOT_REQUESTED'
    }
} finally {
    Pop-Location
}

Write-Output 'RU_FIVE_CUSTOMER_TELEGRAM_ACK=NOT_VERIFIED'
Write-Output 'PRODUCTION_CHANGED=NO'
if ($failures -gt 0) { Write-Output 'RU_FIVE_AUDIT=BLOCKED'; exit 2 }
Write-Output 'RU_FIVE_AUDIT=PASS_ISOLATED_DIAGNOSTICS_ONLY'
exit 0
