# One-command Python 3.12 bootstrap for trusted, isolated Chechnya EIS acceptance.
# No production setup, global pip installs, GitHub secrets or real user alerts.
# If 3.12 is absent, exit with an explicit winget installation command.
[CmdletBinding()]
param(
    [string]$RegionalRssUrl,
    [switch]$SendAuthorizedTelegramTest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$expectedBranch = 'feat/ru-chechnya-eis-rss-20261022'
$branch = (& git -C $repo branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $branch -ne $expectedBranch) {
    throw "Use the $expectedBranch branch before running isolated Chechnya acceptance."
}
if ($RegionalRssUrl -and $RegionalRssUrl -match '[\r\n]') {
    throw 'Regional RSS URL must be a single line.'
}

# Search only actual interpreters. Windows Store's python.exe command alias
# is not a real interpreter and must not be selected.
$projectPythons = @(
    (Join-Path $repo '.venv\Scripts\python.exe'),
    (Join-Path $repo 'venv\Scripts\python.exe')
)
$venvPython = $null
foreach ($candidate in $projectPythons) {
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
    & $candidate -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)' 2>$null
    if ($LASTEXITCODE -eq 0) {
        $venvPython = $candidate
        break
    }
}

if (-not $venvPython) {
    $basePython = $null
    $baseArgs = @()
    $launcher = Get-Command 'py' -ErrorAction SilentlyContinue
    if ($launcher -and $launcher.Source) {
        & $launcher.Source -3.12 -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)' 2>$null
        if ($LASTEXITCODE -eq 0) {
            $basePython = $launcher.Source
            $baseArgs = @('-3.12')
        }
    }
    if (-not $basePython) {
        $userInstall = if ($env:LOCALAPPDATA) {
            Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
        } else { '' }
        $systemInstall = if ($env:ProgramFiles) {
            Join-Path $env:ProgramFiles 'Python312\python.exe'
        } else { '' }
        foreach ($candidate in @($userInstall, $systemInstall)) {
            if (-not $candidate -or -not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
            & $candidate -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)' 2>$null
            if ($LASTEXITCODE -eq 0) {
                $basePython = $candidate
                break
            }
        }
    }
    if (-not $basePython) {
        Write-Host 'PYTHON_312_MISSING=YES' -ForegroundColor Yellow
        Write-Host 'Install the Python 3.12 runtime, then rerun this bootstrap script:' -ForegroundColor Yellow
        Write-Host 'winget install --id Python.Python.3.12 --exact --source winget --accept-source-agreements --accept-package-agreements'
        throw 'Python 3.12 is required; the Microsoft Store execution alias is not an installation.'
    }
    $venvDir = Join-Path $repo '.venv'
    if (Test-Path -LiteralPath $venvDir) {
        throw 'Existing .venv has an incompatible interpreter. Rename that directory before retrying; it will not be overwritten.'
    }
    Write-Host 'CREATING_LOCAL_VENV=YES' -ForegroundColor Cyan
    & $basePython @baseArgs -m venv $venvDir
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 virtual environment creation failed.' }
    $venvPython = Join-Path $venvDir 'Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    throw 'Local Python 3.12 virtual environment executable missing.'
}
Write-Host 'VALYQON_PYTHON_312=FOUND' -ForegroundColor Green
& $venvPython --version
if ($LASTEXITCODE -ne 0) { throw 'Python interpreter did not start.' }

Push-Location $repo
try {
    Write-Host 'INSTALLING_PROJECT_TEST_DEPENDENCIES=YES' -ForegroundColor Cyan
    & $venvPython -m pip install -r requirements-dev.txt
    if ($LASTEXITCODE -ne 0) { throw 'Project Python dependency installation failed.' }
    $arguments = @()
    if ($RegionalRssUrl) {
        $arguments += @('-RegionalRssUrl', $RegionalRssUrl)
    } else {
        $arguments += '-TryOfficialSearchCandidate'
    }
    if ($SendAuthorizedTelegramTest) {
        $arguments += '-SendAuthorizedTelegramTest'
    }
    Write-Host 'STARTING_ISOLATED_CHECHNYA_EIS_TEST=YES' -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot 'ru_chechnya_windows_live.ps1') @arguments
    if (-not $?) { throw 'Isolated Chechnya acceptance did not finish successfully.' }
} finally {
    Pop-Location
}
