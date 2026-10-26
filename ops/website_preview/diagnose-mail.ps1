# Diagnostics for the isolated VALYQON website-review stack ONLY.
# No Python -c / here-string across PowerShell->Docker: Windows broke quoting.
# No passwords, tokens, production database writes or external deliveries.
[CmdletBinding()]
param([switch]$SendProbe, [switch]$SkipAccountCheck)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$compose = Join-Path $PSScriptRoot "compose.yaml"
$envFile = Join-Path $PSScriptRoot "review.env"
$composeArgs = @("--env-file", $envFile, "-p", "valyqon-website-review", "-f", $compose)
$inbox = "http://127.0.0.1:18866/"
$reset = "http://127.0.0.1:18865/forgot-password"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker Desktop is missing or stopped."
}
Push-Location $root
try {
    $apiId = (& docker compose @composeArgs ps -q api | Out-String).Trim()
    $mailId = (& docker compose @composeArgs ps -q mailpit | Out-String).Trim()
    if (-not $apiId -or -not $mailId) {
        throw "LOCAL_REVIEW_NOT_RUNNING: run the updated ops\website_preview\start.ps1"
    }
    Write-Host "REVIEW_API_CONTAINER=FOUND" -ForegroundColor Green
    Write-Host "REVIEW_MAILPIT_CONTAINER=FOUND" -ForegroundColor Green

    # The Python module is copied into the app image by Dockerfile: COPY app.
    # Passing only literal module name + subcommand avoids all Windows quote loss.
    & docker compose @composeArgs exec -T api python -m app.review_email_diagnostic check
    if ($LASTEXITCODE -ne 0) {
        throw "REVIEW_EMAIL_CONFIG_OR_IMAGE=INVALID: rerun updated start.ps1 to rebuild"
    }

    try {
        $page = Invoke-WebRequest -Uri $reset -UseBasicParsing -TimeoutSec 7
        if ($page.StatusCode -ne 200 -or $page.Content -notmatch 'forgot-password') {
            throw "Unexpected forgot-password response"
        }
        Write-Host "REVIEW_FORGOT_PASSWORD_PAGE=OK" -ForegroundColor Green
    } catch {
        throw "REVIEW_FORGOT_PASSWORD_PAGE=UNAVAILABLE"
    }

    try {
        $response = Invoke-RestMethod -Uri ($inbox + "api/v1/messages") -TimeoutSec 7
        Write-Host "MAILPIT_HTTP=OK" -ForegroundColor Green
        Write-Host "MAILPIT_MESSAGES_BEFORE=$([int]$response.total)"
    } catch {
        throw "MAILPIT_HTTP=UNAVAILABLE: open http://127.0.0.1:18866/"
    }

    if ($SendProbe) {
        & docker compose @composeArgs exec -T api python -m app.review_email_diagnostic probe
        if ($LASTEXITCODE -ne 0) {
            throw "REVIEW_SMTP_PROBE=FAILED"
        }
        $seen = $false
        foreach ($attempt in 1..8) {
            Start-Sleep -Milliseconds 500
            try {
                $messages = Invoke-RestMethod -Uri ($inbox + "api/v1/messages") -TimeoutSec 5
                foreach ($item in @($messages.messages)) {
                    if ($item.Subject -eq "VALYQON LOCAL MAILPIT DIAGNOSTIC") {
                        $seen = $true
                        break
                    }
                }
                if ($seen) { break }
            } catch { }
        }
        if ($seen) {
            Write-Host "REVIEW_SMTP_TO_MAILPIT=VERIFIED" -ForegroundColor Green
        } else {
            Write-Warning "REVIEW_SMTP_TO_MAILPIT=NOT_CONFIRMED: refresh local Mailpit"
        }
    }

    if (-not $SkipAccountCheck) {
        Write-Host ""
        Write-Host "Enter ONLY the test email registered on the 18865 preview. No password."
        $accountEmail = (Read-Host "Test account email (Enter to skip)").Trim()
        if ($accountEmail) {
            # Stdin reaches Python inside the container; no personal data is
            # passed in command arguments or printed in the diagnostic.
            $accountEmail | & docker compose @composeArgs exec -T api python -m app.review_email_diagnostic account
            if ($LASTEXITCODE -ne 0) {
                Write-Warning "REVIEW_ACCOUNT_CHECK=UNAVAILABLE"
            }
        } else {
            Write-Host "ACCOUNT_CHECK=SKIPPED"
        }
    }

    Write-Host ""
    Write-Host "REVIEW_MAILPIT_INBOX=$inbox" -ForegroundColor Cyan
    Write-Host "REVIEW_PASSWORD_RESET_URL=$reset" -ForegroundColor Cyan
    Write-Host "An account from port 18765 does not exist automatically on port 18865."
    Write-Host "The forgot-password response is deliberately identical for unknown accounts."
} finally {
    Pop-Location
}
