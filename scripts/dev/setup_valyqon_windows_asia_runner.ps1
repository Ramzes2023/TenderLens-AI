#Requires -Version 5.1
<#
  Dedicated, non-admin, Windows 11 Home-compatible GitHub Actions runner.
  Run only with -Install from a locally authenticated GitHub CLI session.
  No edits to existing WSL/Linux runner installations, no Windows service.
#>
[CmdletBinding()]
param([switch]$Install)

$ErrorActionPreference = 'Stop'
$repo = 'Ramzes2023/TenderLens-AI'
$runnerName = 'VALYQON-WIN-ASIA-01'
$runnerLabel = 'valyqon-asia-windows'
$runnerDir = Join-Path $env:LOCALAPPDATA 'VALYQON\windows-asia-runner'

if ($env:OS -ne 'Windows_NT') {
    throw 'Native Windows PowerShell is required; do not run in WSL.'
}
$id = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($id)
if ($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Open standard PowerShell without Run as Administrator.'
}
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw 'GitHub CLI is missing. Install official GitHub CLI first.'
}
if (Test-Path (Join-Path $runnerDir '.runner')) {
    Write-Host 'WINDOWS_ASIA_RUNNER=ALREADY_REGISTERED'
    Write-Host "START_COMMAND=$runnerDir\run.cmd"
    return
}
if (Test-Path (Join-Path $runnerDir 'config.cmd')) {
    throw 'Unconfigured runner files already exist; refusing to overwrite.'
}
Write-Host '=== VALYQON WINDOWS RUNNER PRECHECK ==='
Write-Host 'EXISTING_WSL_RUNNERS=UNCHANGED'
Write-Host 'WINDOWS_HOME_COMPATIBLE=YES'
& gh auth status --hostname github.com
if ($LASTEXITCODE -ne 0) {
    throw 'Complete gh auth login first.'
}
if (-not $Install) {
    Write-Host 'MODE=PRECHECK_ONLY'
    return
}

# Only official GitHub Actions runner releases, with GitHub-published SHA256.
$release = Invoke-RestMethod -Uri 'https://api.github.com/repos/actions/runner/releases/latest' -Headers @{ 'User-Agent' = 'VALYQON-Asia-Runner' } -TimeoutSec 30
$asset = @($release.assets | Where-Object {
    $_.name -match '^actions-runner-win-x64-[0-9.]+\.zip$'
} | Select-Object -First 1)
if ($asset.Count -ne 1) {
    throw 'Official Windows x64 runner ZIP was not found.'
}
$file = $asset[0]
if ($file.browser_download_url -notmatch '^https://github\.com/actions/runner/releases/download/v[0-9.]+/actions-runner-win-x64-[0-9.]+\.zip$') {
    throw 'Unexpected runner download URL.'
}
$digest = [string]$file.digest
if ($digest -notmatch '^sha256:([0-9a-fA-F]{64})$') {
    throw 'Official GitHub asset SHA256 is unavailable.'
}
$expected = $Matches[1].ToLowerInvariant()
$zipPath = Join-Path $env:TEMP 'valyqon-windows-asia-runner.zip'
try {
    Invoke-WebRequest -Uri $file.browser_download_url -OutFile $zipPath -MaximumRedirection 3 -TimeoutSec 240
    $actual = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $expected) {
        throw 'Runner ZIP SHA256 verification failed.'
    }
    New-Item -ItemType Directory -Path $runnerDir -Force | Out-Null
    Expand-Archive -LiteralPath $zipPath -DestinationPath $runnerDir -Force
    $configCmd = Join-Path $runnerDir 'config.cmd'
    if (-not (Test-Path $configCmd)) {
        throw 'Official runner configuration program missing.'
    }

    # The short-lived registration token is kept in memory, never in a file.
    $registration = & gh api --method POST "repos/$repo/actions/runners/registration-token" --jq '.token'
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($registration)) {
        throw 'GitHub runner registration permission was denied.'
    }
    try {
        Push-Location $runnerDir
        try {
            & $configCmd --unattended --url "https://github.com/$repo" --token $registration.Trim() --name $runnerName --no-default-labels --labels $runnerLabel --work '_work'
            if ($LASTEXITCODE -ne 0) {
                throw 'Runner registration command failed.'
            }
        } finally {
            Pop-Location
        }
    } finally {
        $registration = $null
    }

    # Do not leave the user's authenticated gh CLI token available to jobs.
    & gh auth logout --hostname github.com
    if ($LASTEXITCODE -ne 0) {
        throw 'GH CLI logout failed. Do not start runner while authenticated.'
    }
    Write-Host 'GITHUB_CLI_CREDENTIALS=LOGGED_OUT'
    Write-Host 'WINDOWS_ASIA_RUNNER=REGISTERED'
    Write-Host 'RUNNER_LABELS=DEDICATED_CUSTOM_ONLY'
    $runCmd = Join-Path $runnerDir 'run.cmd'
    Write-Host "START_COMMAND=$runCmd"
    Start-Process -FilePath $runCmd -WorkingDirectory $runnerDir
    Write-Host 'WINDOWS_ASIA_RUNNER=STARTED'
    Write-Host 'Keep the runner console open. No Windows service installed.'
} finally {
    Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
}
