# Stop the isolated website review without deleting data or other stacks.
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$compose = Join-Path $PSScriptRoot "compose.yaml"
$envFile = Join-Path $PSScriptRoot "review.env"
Push-Location $root
try {
    & docker compose --env-file $envFile -p valyqon-website-review -f $compose down
    if ($LASTEXITCODE -ne 0) { throw "Review stack stop failed." }
    Write-Host "VALYQON_BROWSER_PREVIEW=STOPPED; DATA_PRESERVED=YES" -ForegroundColor Green
} finally {
    Pop-Location
}
