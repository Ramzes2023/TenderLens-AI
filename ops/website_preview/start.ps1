# Open the reviewed PR's REAL FastAPI landing page in your local browser.
# The review stack uses its own named volume, port and Docker Compose project.
[CmdletBinding()]
param([switch]$NoBrowser)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$compose = Join-Path $PSScriptRoot "compose.yaml"
$envFile = Join-Path $PSScriptRoot "review.env"
$website = "http://127.0.0.1:18865/"
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker CLI is missing. Install/start Docker Desktop." }
Push-Location $root
try {
    $dockerInfo = & docker info --format '{{.ServerVersion}}' 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Docker Desktop engine is not running." }
    Write-Host "VALYQON_REVIEW_DOCKER=READY" -ForegroundColor Cyan
    & docker compose --env-file $envFile -p valyqon-website-review -f $compose config --quiet
    if ($LASTEXITCODE -ne 0) { throw "Preview Compose config failed." }
    & docker compose --env-file $envFile -p valyqon-website-review -f $compose up -d --build api mailpit
    if ($LASTEXITCODE -ne 0) { throw "Preview Docker build/start failed." }
    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        try {
            $res = Invoke-WebRequest -Uri $website -UseBasicParsing -TimeoutSec 3
            if ($res.StatusCode -eq 200 -and $res.Content -match 'guestSearchForm' -and $res.Content -match 'vqPulseChart') {
                $ready = $true
                break
            }
        } catch { }
        Start-Sleep -Seconds 2
    }
    if (-not $ready) {
        & docker compose --env-file $envFile -p valyqon-website-review -f $compose ps
        throw "Preview is not ready. Inspect review-only logs; production containers were not changed."
    }
    # Do not announce password recovery as ready if Mailpit is unreachable.
    $mailpitReady = $false
    for ($mailAttempt = 0; $mailAttempt -lt 20; $mailAttempt++) {
        try {
            $mailResponse = Invoke-WebRequest -Uri "http://127.0.0.1:18866/api/v1/messages" -UseBasicParsing -TimeoutSec 3
            if ($mailResponse.StatusCode -eq 200) {
                $mailpitReady = $true
                break
            }
        } catch { }
        Start-Sleep -Seconds 1
    }
    if (-not $mailpitReady) {
        & docker compose --env-file $envFile -p valyqon-website-review -f $compose ps
        throw "MAILPIT_INBOX=UNAVAILABLE; cannot confirm password recovery. Check localhost:18866 and local review logs."
    }
    Write-Host "MAILPIT_INBOX=READY" -ForegroundColor Green
    Write-Host "VALYQON_BROWSER_PREVIEW=READY" -ForegroundColor Green
    Write-Host "LOCAL_PREVIEW_URL=$website" -ForegroundColor Green
    Write-Host "LOCAL_PASSWORD_RECOVERY=http://127.0.0.1:18865/forgot-password" -ForegroundColor Green
    Write-Host "LOCAL_MAIL_INBOX=http://127.0.0.1:18866/" -ForegroundColor Green
    Write-Host "EMAIL_DELIVERY=MAILPIT_ONLY_NO_EXTERNAL_EMAIL" -ForegroundColor Yellow
    Write-Host "GUEST_TENDERS=EMPTY_UNTIL_REAL_NOTICES_EXIST_IN_ISOLATED_DB"
    Write-Host "PAID_DETAILS=LOCKED; PAYMENT=DISABLED; AI=DISABLED"
    if (-not $NoBrowser) { Start-Process $website }
} finally {
    Pop-Location
}
