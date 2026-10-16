# This file is executed ONLY inside a disposable Windows Sandbox VM.
# Networking is disabled; the source and wheel cache are read-only mappings.
$ErrorActionPreference = 'Stop'
$source = 'C:\VALYQON_SOURCE'
$cache = 'C:\VALYQON_CACHE'
$result = 'C:\VALYQON_RESULTS'
$exitCode = 2
$status = 'NOT_STARTED'
$log = Join-Path $result 'windows-p39e-pytest.log'
try {
    if (-not (Test-Path (Join-Path $source 'tests\test_p39e_local_preview.py'))) {
        throw 'Fixture source missing.'
    }
    if (-not (Test-Path (Join-Path $cache 'python-3.12.10-amd64.exe'))) {
        throw 'Pinned Python installer missing.'
    }
    $signature = Get-AuthenticodeSignature -FilePath (Join-Path $cache 'python-3.12.10-amd64.exe')
    if ($signature.Status -ne 'Valid' -or
        $signature.SignerCertificate.Subject -notmatch 'Python Software Foundation') {
        throw 'Python installer signature not trusted.'
    }
    $installer = Join-Path $cache 'python-3.12.10-amd64.exe'
    $proc = Start-Process -FilePath $installer -ArgumentList @(
        '/quiet', 'InstallAllUsers=0', 'TargetDir=C:\VALYQON_PYTHON',
        'PrependPath=0', 'Include_pip=1', 'Include_test=0'
    ) -Wait -PassThru -NoNewWindow
    if ($proc.ExitCode -ne 0) { throw 'Python installation failed.' }
    $python = 'C:\VALYQON_PYTHON\python.exe'
    if (-not (Test-Path $python)) { throw 'Python binary missing.' }
    $status = 'DEPENDENCIES'
    $env:PYTHONNOUSERSITE = '1'
    $env:PIP_NO_INDEX = '1'
    $env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
    $env:PIP_NO_INPUT = '1'
    $env:PYTHONDONTWRITEBYTECODE = '1'
    Set-Location $source
    & $python -m pip install --no-index --no-cache-dir --find-links (Join-Path $cache 'wheels') -r 'requirements-dev.txt' *> $log
    if ($LASTEXITCODE -ne 0) { throw 'Offline dependency installation failed.' }
    $status = 'WINDOWS_FIXTURE_RUNNING'
    & $python -m compileall -q app tests scripts 2>&1 | Out-File -FilePath $log -Append
    if ($LASTEXITCODE -ne 0) { throw 'Windows fixture compilation failed.' }
    & $python -m pytest -vv --maxfail=1 --durations=15 tests/test_p39e_local_preview.py 2>&1 |
        Out-File -FilePath $log -Append
    if ($LASTEXITCODE -ne 0) { throw 'Windows fixture tests failed.' }
    $status = 'WINDOWS_FIXTURE_PASSED'
    $exitCode = 0
} catch {
    ('ASIA_SANDBOX_ERROR=' + $_.Exception.GetType().Name) |
        Out-File -FilePath $log -Append
    $status = 'FAILED'
    $exitCode = 2
} finally {
    # Only a small, non-secret exit marker and the test log leave the sandbox.
    $report = @{ state = $status; exit_code = $exitCode;
                 platform = 'native_windows_sandbox'; production_changed = $false }
    $temp = Join-Path $result 'windows-result.partial'
    $done = Join-Path $result 'windows-result.json'
    $report | ConvertTo-Json -Compress | Set-Content -Path $temp -Encoding UTF8
    Move-Item -LiteralPath $temp -Destination $done -Force
}
