# VALYQON Chechnya official 44-FZ acceptance from a trusted Windows machine.
# This is an isolated read-only acceptance: temporary SQLite + LOCAL fake Bot.
# It does NOT enable production and does NOT call the Telegram Bot API.
# Example:
#   .\scripts\ru_chechnya_windows_live.ps1 -RegionalRssUrl '<exact official EIS 44-FZ region RSS URL>'
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [ValidateNotNullOrEmpty()]
    [string]$RegionalRssUrl
)

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
    $parsed.AbsolutePath -ne '/epz/order/extendedsearch/rss.html' -or
    -not $parsed.Query) {
    throw 'Only the exact official EIS 44-FZ RSS endpoint is allowed.'
}

$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    $python = (Get-Command 'python' -ErrorAction Stop).Source
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
        if ($LASTEXITCODE -ne 0) { throw 'Chechnya strict live Worker acceptance failed: no merge.' }

        Write-Host 'CHECHNYA_ACCEPTANCE=PASS_LOCAL_ONLY' -ForegroundColor Green
        Write-Host 'REAL_TELEGRAM_DELIVERY=NOT_VERIFIED'
        Write-Host 'PRODUCTION_CHANGED=NO'
    } finally {
        Pop-Location
    }
} finally {
    foreach ($key in $envOverride.Keys) {
        [Environment]::SetEnvironmentVariable($key, $previous[$key], 'Process')
    }
}
