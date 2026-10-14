$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'host_bash_transport.ps1')

$command = Get-ValyqonPreviewBashCommand -RunId 'preview-20261013_01'
if ($command -cne "tr -d '\015' | bash -s -- 'preview-20261013_01'") {
    throw 'Unexpected receiver command.'
}
if ($command.Contains("`r") -or $command.Contains("`n")) {
    throw 'Receiver command must be a single line without CR/LF.'
}
foreach ($invalid in @('bad id', 'x;exit', "x'y", "x`r", "x`n", '-option', ('x' * 129))) {
    $rejected = $false
    try { $null = Get-ValyqonPreviewBashCommand -RunId $invalid }
    catch { $rejected = $true }
    if (-not $rejected) { throw 'Unsafe run ID accepted.' }
}
Write-Output 'PRIVATE_HOST_BASH_TRANSPORT_LOCAL=VERIFIED (command construction and input rejection; no SSH executed)'
