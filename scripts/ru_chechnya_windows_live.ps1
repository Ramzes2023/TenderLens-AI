# VALYQON Chechnya official 44-FZ acceptance from a trusted Windows machine.
# This is an isolated read-only acceptance: temporary SQLite + LOCAL fake Bot.
# Production is never enabled. Real Telegram API is disabled unless both
# -SendAuthorizedTelegramTest and explicit operator test-only credentials exist.
# Example:
#   .\scripts\ru_chechnya_windows_live.ps1 -RegionalRssUrl '<exact official EIS 44-FZ region RSS URL>'
#   .\scripts\ru_chechnya_windows_live.ps1 -TryOfficialSearchCandidate
[CmdletBinding()]
param(
    [string]$RegionalRssUrl,
    [switch]$TryOfficialSearchCandidate,
    [switch]$SendAuthorizedTelegramTest,
    [switch]$ValidateUrlOnly
)

# A conservative official EIS search-form shape from the existing EIS adapter.
# This is not equivalent to a verified advanced-search customer-region filter.
# The strict Worker only accepts notices whose original EIS card and customer
# or geographic metadata independently prove Chechnya.
if ($TryOfficialSearchCandidate) {
    if ($RegionalRssUrl) {
        throw 'Use either a copied RegionalRssUrl or TryOfficialSearchCandidate, not both.'
    }
    $term = [Uri]::EscapeDataString('Чеченская Республика')
    $RegionalRssUrl = "https://zakupki.gov.ru/epz/order/extendedsearch/rss.html?searchString=${term}&morphology=on&pageNumber=1&fz44=on"
    Write-Host 'EIS_REGION_QUERY=UNVERIFIED_TEXT_SEARCH_CANDIDATE' -ForegroundColor Yellow
}
if (-not $RegionalRssUrl) {
    throw 'Provide -RegionalRssUrl or -TryOfficialSearchCandidate.'
}

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$expectedBranch = 'feat/ru-chechnya-eis-rss-20261022'
$branch = (& git -C $repo branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $branch -ne $expectedBranch) {
    throw "Check out $expectedBranch before live acceptance; refusing to test another branch."
}

# Prefer the project's pinned Python environment before an unrelated
# machine-level python.exe (which can be the Windows Store alias).  VALYQON
# installations have used both .venv and venv on Windows.
$pythonCandidates = @(
    (Join-Path $repo '.venv\Scripts\python.exe'),
    (Join-Path $repo 'venv\Scripts\python.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
    (Join-Path $env:ProgramFiles 'Python312\python.exe')
)
# Reject the Windows Store App Execution Alias: Get-Command python can resolve
# python.exe even when there is no installed interpreter behind it.
$python = $null
$pythonArgs = @()
foreach ($candidate in $pythonCandidates) {
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
    & $candidate -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)' 2>$null
    if ($LASTEXITCODE -eq 0) {
        $python = $candidate
        break
    }
}
if (-not $python) {
    $launcher = Get-Command 'py' -ErrorAction SilentlyContinue
    if ($launcher -and $launcher.Source) {
        & $launcher.Source -3.12 -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)' 2>$null
        if ($LASTEXITCODE -eq 0) {
            $python = $launcher.Source
            $pythonArgs = @('-3.12')
        }
    }
}
if (-not $python) {
    throw 'Python 3.12 not found. Install Python 3.12, create .venv or venv, then rerun. Windows Store python.exe alias is not an interpreter.'
}
& $python @pythonArgs -c 'import sys; assert sys.version_info[:2] == (3, 12), "VALYQON requires Python 3.12"'
if ($LASTEXITCODE -ne 0) {
    throw 'Use Python 3.12 from the VALYQON project environment.'
}

# One source of truth for EIS URL validation. The old PowerShell [uri]
# precheck rejected an automatically generated official RSS candidate on a
# real operator's Windows PowerShell, before any source/network test ran.
# Keep the actual app-level strict HTTPS host, RSS route, 44-FZ and Chechnya
# scope checks; never open an arbitrary URL or disable TLS verification.
$previousCandidate = [Environment]::GetEnvironmentVariable('VALYQON_CHECHNYA_URL_VALIDATE', 'Process')
try {
    [Environment]::SetEnvironmentVariable('VALYQON_CHECHNYA_URL_VALIDATE', $RegionalRssUrl, 'Process')
    $urlValidation = @'
import os
from app.sources.ru_chechnya_eis_rss import validate_chechnya_feed_urls
validate_chechnya_feed_urls((os.environ["VALYQON_CHECHNYA_URL_VALIDATE"],))
'@
    & $python @pythonArgs -c $urlValidation 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw 'Official Chechnya RSS URL rejected: required HTTPS zakupki.gov.ru, allowlisted RSS path, 44-FZ and Chechnya scope.'
    }
} finally {
    [Environment]::SetEnvironmentVariable('VALYQON_CHECHNYA_URL_VALIDATE', $previousCandidate, 'Process')
}
Write-Host 'CHECHNYA_EIS_OFFICIAL_URL=VALIDATED' -ForegroundColor Green
if ($ValidateUrlOnly) {
    Write-Host 'CHECHNYA_URL_SMOKE=PASS_NO_NETWORK' -ForegroundColor Green
    return
}
$envOverride = @{
    'RU_CHECHNYA_EIS_ENABLED' = 'true'
    'RU_CHECHNYA_EIS_RSS_URLS' = $RegionalRssUrl
    'EIS_DIRECT_ENABLED' = 'true'
    'EIS_SYSTEM_TRUST_ENABLED' = 'true'
    'EIS_CA_BUNDLE_FILE' = ''
    'GIGACHAT_CA_BUNDLE_FILE' = ''
    'EIS_PROFILE_FEEDS_ENABLED' = 'false'
    'MONITORING_ENABLED' = 'false'
}
# No external Telegram sends unless the operator additionally passes an
# explicit switch AND has preconfigured the authorized test-only credentials.
# Clearing is PROCESS-LOCAL, restored by the existing finally block.
if (-not $SendAuthorizedTelegramTest) {
    $envOverride['RU_CHECHNYA_E2E_TEST_BOT_TOKEN'] = ''
    $envOverride['RU_CHECHNYA_E2E_TEST_CHAT_ID'] = ''
} elseif (-not $env:RU_CHECHNYA_E2E_TEST_BOT_TOKEN -or -not $env:RU_CHECHNYA_E2E_TEST_CHAT_ID) {
    throw 'Authorized Telegram test requires both test-only environment variables.'
}
$previous = @{}
foreach ($key in $envOverride.Keys) {
    $previous[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
}
try {
    foreach ($key in $envOverride.Keys) {
        [Environment]::SetEnvironmentVariable($key, $envOverride[$key], 'Process')
    }
    Push-Location $repo
    try {
        Write-Host 'CHECHNYA_ACCEPTANCE=OFFLINE_CONTRACTS' -ForegroundColor Cyan
        & $python @pythonArgs -B -m pytest -q tests/test_ru_chechnya_eis_rss.py tests/test_ru_background_telegram_catalog.py tests/test_ru_telegram_original_dedup.py
        if ($LASTEXITCODE -ne 0) { throw 'Chechnya offline contracts failed.' }

        Write-Host 'CHECHNYA_ACCEPTANCE=OFFICIAL_LIVE_EIS_TO_LOCAL_ALERT' -ForegroundColor Cyan
        & $python @pythonArgs -B -m scripts.ci_ru_chechnya_eis_real_worker
        if ($LASTEXITCODE -ne 0) {
            Write-Host 'CHECHNYA_LIVE_FAILED=RUNNING_SAFE_NETWORK_DIAGNOSTICS' -ForegroundColor Yellow
            & $python @pythonArgs -B -m scripts.ru_chechnya_eis_transport_probe
            throw 'Chechnya strict live Worker acceptance failed: no merge.'
        }

        if ($SendAuthorizedTelegramTest) {
            # The strict Python acceptance exits nonzero unless the test Bot
            # API returns an acknowledged message in the exact target chat.
            Write-Host 'CHECHNYA_ACCEPTANCE=PASS_LOCAL_AND_TEST_BOT_ACK' -ForegroundColor Green
        } else {
            Write-Host 'CHECHNYA_ACCEPTANCE=PASS_LOCAL_ONLY' -ForegroundColor Green
        }
        Write-Host 'PRODUCTION_USER_DELIVERY=NOT_VERIFIED'
        Write-Host 'PRODUCTION_CHANGED=NO'
    } finally {
        Pop-Location
    }
} finally {
    foreach ($key in $envOverride.Keys) {
        [Environment]::SetEnvironmentVariable($key, $previous[$key], 'Process')
    }
}
