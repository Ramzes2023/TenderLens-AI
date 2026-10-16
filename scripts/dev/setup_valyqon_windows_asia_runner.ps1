#Requires -Version 5.1
<#
.SYNOPSIS
  Registers a fourth, separate GitHub Actions runner for trusted VALYQON Asia
  native Windows 11 Home-compatible tests. Existing WSL runners remain untouched.
.DESCRIPTION
  Requires an authenticated GitHub CLI with repository admin permission.
  Downloads the official Windows x64 runner release after verifying the SHA256
  published by GitHub's release asset API, obtains a short-lived repository
  registration token, and registers ONE custom-labelled runner.
  It never stores registration tokens, starts a Windows service, or modifies CI.
  Native Windows fixture comes from reviewed main. Registration is not a sandbox.
  Run under a dedicated non-admin Windows account wherever possible.
#>
[CmdletBinding()]
param(
    [switch]$Install,
    [string]$Repository = "Ramzes2023/TenderLens-AI",
    [string]$RunnerName = "VALYQON-WIN-ASIA-01",
    [string]$RunnerLabel = "valyqon-asia-windows",
    [string]$Directory = "$env:LOCALAPPDATA\VALYQON\windows-asia-runner"
)
$ErrorActionPreference = 'Stop'
if ($env:OS -ne "Windows_NT") { throw "Run in native Windows PowerShell, not WSL." }
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if ($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Start PowerShell without Run as Administrator; this runner must stay non-elevated."
}
if ($Repository -cne "Ramzes2023/TenderLens-AI") { throw "Unexpected repository." }
if ($RunnerName -cne "VALYQON-WIN-ASIA-01" -or $RunnerLabel -cne "valyqon-asia-windows") {
    throw "Runner identity is pinned for isolation from other teams."
}
$existing = @('VALYQON-Runner','VALYQON-INT-Runner','VALYQON-ASIA-Runner')
$fullTarget = [System.IO.Path]::GetFullPath($Directory)
if ($fullTarget -match '(?i)\\(VALYQON-Runner|VALYQON-INT-Runner|VALYQON-ASIA-Runner)(\\|$)') {
    throw 'Existing runner directory cannot be overwritten.'
}
if ($existing -contains (Split-Path -Leaf $fullTarget)) {
    throw 'Existing runner directory cannot be overwritten.'
}
Write-Host "VALYQON_WINDOWS_ASIA_SETUP=CHECKING"
Write-Host "RUNNER_IDENTITY=$RunnerName"
Write-Host "EXISTING_WSL_RUNNERS=UNCHANGED"
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Host "GITHUB_CLI=MISSING (install official gh and run gh auth login)"
    return
}
& gh auth status 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "GITHUB_CLI=NOT_AUTHENTICATED (run gh auth login)"
    return
}
$edition = Get-ComputerInfo -Property WindowsProductName -ErrorAction SilentlyContinue
Write-Host "WINDOWS_PRODUCT=$($edition.WindowsProductName)"
try {
    $sandbox = Get-WindowsOptionalFeature -Online -FeatureName 'Containers-DisposableClientVM' -ErrorAction Stop
    Write-Host "WINDOWS_SANDBOX=$($sandbox.State)"
} catch {
    Write-Host "WINDOWS_SANDBOX=NOT_QUERYABLE (check Windows Sandbox installation manually)"
}
if (-not (Test-Path (Join-Path $env:SystemRoot 'System32\WindowsSandbox.exe'))) {
    Write-Host 'WINDOWS_SANDBOX=UNAVAILABLE'
    Write-Host 'WINDOWS_HOME_COMPATIBLE=YES (native test runs only protected-main-reviewed fixture as non-admin)'
} else {
    Write-Host 'WINDOWS_SANDBOX=OPTIONAL_NOT_REQUIRED'
}
if (-not $Install) {
    Write-Host "MODE=PREFLIGHT_ONLY; REGISTRATION=NOT_STARTED"
    return
}
if ((Test-Path (Join-Path $Directory '.runner')) -or (Test-Path (Join-Path $Directory 'config.cmd'))) {
    throw "Runner directory already contains a configuration or runner. Refusing overwrite."
}
$release = Invoke-RestMethod -Uri 'https://api.github.com/repos/actions/runner/releases/latest' -Headers @{'User-Agent'='VALYQON-Asia-Windows-Runner-Setup'} -TimeoutSec 30
$asset = @($release.assets | Where-Object { $_.name -match '^actions-runner-win-x64-[0-9.]+\.zip$' }) | Select-Object -First 1
if (-not $asset) { throw "Official Windows x64 runner asset not found." }
if ($asset.browser_download_url -notmatch '^https://github\.com/actions/runner/releases/download/v[0-9.]+/actions-runner-win-x64-[0-9.]+\.zip$') {
    throw "Unexpected runner asset host/path."
}
if ($asset.digest -notmatch '^sha256:([0-9a-fA-F]{64})$') {
    throw "Published SHA256 is missing; refusing an unverified runner binary."
}
$expectedSha = $Matches[1].ToLowerInvariant()
$zip = Join-Path $env:TEMP 'valyqon-asia-runner-verified.zip'
try {
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zip -MaximumRedirection 3 -TimeoutSec 240
    $actualSha = (Get-FileHash -Path $zip -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualSha -ne $expectedSha) { throw "Runner archive SHA256 mismatch." }
    New-Item -ItemType Directory -Path $Directory -Force | Out-Null
    Expand-Archive -LiteralPath $zip -DestinationPath $Directory -Force
    $registration = & gh api --method POST "repos/$Repository/actions/runners/registration-token" --jq '.token'
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($registration)) {
        throw "Cannot request registration token from GitHub; verify repository-admin permission."
    }
    try {
        Push-Location $Directory
        try {
            & (Join-Path $Directory 'config.cmd') --unattended --url "https://github.com/$Repository" --token $registration.Trim() --name $RunnerName --labels $RunnerLabel --work '_work'
            if ($LASTEXITCODE -ne 0) { throw "Official runner registration failed." }
        } finally { Pop-Location }
    } finally {
        $registration = $null
    }
    Write-Host "WINDOWS_ASIA_RUNNER=REGISTERED"
    Write-Host "SECURITY=Windows process test uses protected main files, not PR source; non-admin host test, no VM sandbox."
    # Remove the newly-created gh CLI login before starting the runner, so
    # runner jobs do not inherit a reusable GitHub CLI token from this user.
    & gh auth logout --hostname github.com 2>$null
    if ($LASTEXITCODE -ne 0) { throw "GH CLI credentials were not cleared; do not start runner." }
    Write-Host "GITHUB_CLI_CREDENTIALS=LOGGED_OUT_AFTER_REGISTRATION"
    Write-Host "START_COMMAND=$Directory\run.cmd"
    Write-Host "RUNNER_PROCESS=STARTING_INTERACTIVE_NO_SERVICE"
    Start-Process -FilePath $env:ComSpec -ArgumentList @('/k', ('"' + (Join-Path $Directory 'run.cmd') + '"')) -WorkingDirectory $Directory
    Write-Host "Keep the new runner console open until Windows acceptance completes; no SYSTEM service installed."
} finally {
    Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue
}
