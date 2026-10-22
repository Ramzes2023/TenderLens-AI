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
    [switch]$SendAuthorizedTelegramTest
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
    $RegionalRssUrl = "https://zakupki.gov.ru/epz/order/extendedsearch/rss.html?searchString=$term&morphology=on&pageNumber=1&fz44=on"
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

try {
    $parsed = [uri]$RegionalRssUrl
} catch {
    throw 'RegionalRssUrl must be a full official HTTPS EIS RSS URL.'
}
if ($parsed.Scheme -ne 'https' -or $parsed.Host -ne 'zakupki.gov.ru' -or
    $parsed.AbsolutePath -notin @('/epz/order/extendedsearch/rss.html', '/epz/order/extendedsearch/rss') -or
    -not $parsed.Query) {
    throw 'Only the exact official EIS 44-FZ RSS endpoint is allowed.'
}

# Prefer the project's pinned Python environment before an unrelated
# machine-level python.exe (which can be the Windows Store alias).  VALYQON
# installations have used both .venv and venv on Windows.
$pythonCandidates = @(
    (Join-Path $repo '.venv\Scripts\python.exe'),
    (Join-Path $repo 'venv\Scripts\python.exe')
)
$python = $pythonCandidates |
    Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
    Select-Object -First 1
if (-not $python) {
    $command = Get-Command 'python' -ErrorAction SilentlyContinue
    if ($null -eq $command -or -not $command.Source) {
        throw 'Python 3.12 not found. Activate the project venv or .venv first.'
    }
    $python = $command.Source
}
& $python -c 'import sys; assert sys.version_info >= (3,12) and sys.version_info < (3,13), "VALYQON requires Python 3.12"'
if ($LASTEXITCODE -ne 0) {
    throw 'Use Python 3.12 from the VALYQON project environment.'
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
        & $python -B -m pytest -q tests/test_ru_chechnya_eis_rss.py tests/test_ru_background_telegram_catalog.py tests/test_ru_telegram_original_dedup.py
        if ($LASTEXITCODE -ne 0) { throw 'Chechnya offline contracts failed.' }

        Write-Host 'CHECHNYA_ACCEPTANCE=OFFICIAL_LIVE_EIS_TO_LOCAL_ALERT' -ForegroundColor Cyan
        & $python -B -m scripts.ci_ru_chechnya_eis_real_worker
        if ($LASTEXITCODE -ne 0) {
            Write-Host 'CHECHNYA_LIVE_FAILED=RUNNING_SAFE_NETWORK_DIAGNOSTICS' -ForegroundColor Yellow
            & $python -B -m scripts.ru_chechnya_eis_transport_probe
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
