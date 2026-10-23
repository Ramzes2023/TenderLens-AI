# Diagnoses ONLY the separate local VALYQON website preview.
# No database writes, password manipulation, production access, or secrets.
# -SendProbe sends one synthetic non-sensitive email to LOCAL Mailpit only.
[CmdletBinding()]
param([switch]$SendProbe, [switch]$SkipAccountCheck)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$compose = Join-Path $PSScriptRoot "compose.yaml"
$envFile = Join-Path $PSScriptRoot "review.env"
$args = @("--env-file", $envFile, "-p", "valyqon-website-review", "-f", $compose)
$inbox = "http://127.0.0.1:18866/"
$reset = "http://127.0.0.1:18865/forgot-password"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker Desktop is missing. Start Docker Desktop first."
}

Push-Location $root
try {
    $apiId = (& docker compose @args ps -q api | Out-String).Trim()
    $mailId = (& docker compose @args ps -q mailpit | Out-String).Trim()
    if (-not $apiId) {
        throw "REVIEW_API=NOT_RUNNING. Run ops\website_preview\start.ps1 from the UPDATED review worktree."
    }
    if (-not $mailId) {
        throw "REVIEW_MAILPIT=NOT_RUNNING. Run the updated start.ps1. Old test versions had email disabled."
    }
    Write-Host "REVIEW_API_CONTAINER=FOUND" -ForegroundColor Green
    Write-Host "REVIEW_MAILPIT_CONTAINER=FOUND" -ForegroundColor Green

    $appEnvProbe = @'
import os
mode = os.getenv("VALYQON_EMAIL_MODE", "disabled")
host = os.getenv("VALYQON_SMTP_HOST", "")
base = os.getenv("VALYQON_PUBLIC_BASE_URL", "")
print("REVIEW_EMAIL_MODE=" + mode)
print("REVIEW_SMTP_POINTS_TO_LOCAL_MAILPIT=" + ("YES" if host == "mailpit" else "NO"))
print("REVIEW_RESET_LINK_BASE_OK=" + ("YES" if base == "http://127.0.0.1:18865" else "NO"))
if mode != "smtp" or host != "mailpit" or base != "http://127.0.0.1:18865":
    raise SystemExit(3)
'@
    & docker compose @args exec -T api python -c $appEnvProbe
    if ($LASTEXITCODE -ne 0) {
        throw "REVIEW_EMAIL_CONFIG=OLD_OR_INCORRECT. Rebuild via updated start.ps1."
    }

    try {
        $form = Invoke-WebRequest -Uri $reset -UseBasicParsing -TimeoutSec 7
        if ($form.StatusCode -ne 200 -or $form.Content -notmatch 'forgot-password') {
            throw "Password reset form did not respond correctly."
        }
        Write-Host "REVIEW_FORGOT_PASSWORD_PAGE=OK" -ForegroundColor Green
    } catch {
        throw "REVIEW_FORGOT_PASSWORD_PAGE=UNAVAILABLE. Check $reset"
    }

    try {
        $messages = Invoke-RestMethod -Uri ($inbox + "api/v1/messages") -TimeoutSec 7
        $before = [int]$messages.total
        Write-Host "MAILPIT_HTTP=OK" -ForegroundColor Green
        Write-Host "MAILPIT_MESSAGES_BEFORE=$before"
    } catch {
        throw "MAILPIT_HTTP=UNAVAILABLE. Open $inbox after starting the updated preview."
    }

    if ($SendProbe) {
        $smtpProbe = @'
import smtplib
from email.message import EmailMessage
message = EmailMessage()
message["From"] = "review-probe@valyqon.example.test"
message["To"] = "review-check@valyqon.example.test"
message["Subject"] = "VALYQON LOCAL MAILPIT DIAGNOSTIC"
message.set_content("This is a safe test of the local Mailpit inbox only. Not a password reset.")
with smtplib.SMTP("mailpit", 1025, timeout=8) as sender:
    sender.send_message(message)
print("REVIEW_SMTP_PROBE_SUBMITTED=YES")
'@
        & docker compose @args exec -T api python -c $smtpProbe
        if ($LASTEXITCODE -ne 0) { throw "REVIEW_SMTP_PROBE=FAILED. Local Mailpit SMTP may be unreachable." }
        $seen = $false
        foreach ($attempt in 1..8) {
            Start-Sleep -Milliseconds 450
            try {
                $messages = Invoke-RestMethod -Uri ($inbox + "api/v1/messages") -TimeoutSec 5
                foreach ($message in @($messages.messages)) {
                    if ($message.Subject -eq "VALYQON LOCAL MAILPIT DIAGNOSTIC") { $seen = $true; break }
                }
                if ($seen) { break }
            } catch { }
        }
        if ($seen) {
            Write-Host "REVIEW_SMTP_TO_MAILPIT=VERIFIED" -ForegroundColor Green
        } else {
            Write-Warning "REVIEW_SMTP_TO_MAILPIT=NOT_CONFIRMED. Inspect Mailpit UI and API."
        }
    }

    if (-not $SkipAccountCheck) {
        Write-Host ""
        Write-Host "Enter only your TEST ACCOUNT EMAIL from the 18865 site. Do not enter a password."
        $accountEmail = (Read-Host "Test account email (or press Enter to skip)").Trim()
        if ($accountEmail) {
            $accountProbe = @'
import sqlite3, sys
email = sys.stdin.readline().strip().casefold()
try:
    conn = sqlite3.connect("file:/app/data/website-review.sqlite?mode=ro", uri=True, timeout=5)
    try:
        record = conn.execute(
            "SELECT is_active, email_verified FROM auth_accounts WHERE lower(email)=?",
            (email,)
        ).fetchone()
    finally:
        conn.close()
    if record is None:
        print("ACCOUNT_IN_18865_DATABASE=NO")
    else:
        print("ACCOUNT_IN_18865_DATABASE=YES")
        print("ACCOUNT_ACTIVE=" + ("YES" if record[0] else "NO"))
        print("ACCOUNT_EMAIL_VERIFIED=" + ("YES" if record[1] else "NO"))
except sqlite3.Error:
    print("ACCOUNT_DB_CHECK=UNAVAILABLE")
    raise SystemExit(3)
'@
            $accountEmail | & docker compose @args exec -T api python -c $accountProbe
            if ($LASTEXITCODE -ne 0) {
                Write-Warning "Could not check account existence read-only. The local database may not be initialized."
            }
        } else {
            Write-Host "ACCOUNT_CHECK=SKIPPED"
        }
    }

    Write-Host ""
    Write-Host "REVIEW_PASSWORD_RESET_URL=$reset" -ForegroundColor Cyan
    Write-Host "REVIEW_MAILPIT_INBOX=$inbox" -ForegroundColor Cyan
    Write-Host "If account does not exist in 18865, register a NEW synthetic test account there." -ForegroundColor Yellow
    Write-Host "If the account exists, submit the reset form ONCE, wait 60 seconds before any repeat, then refresh Mailpit." -ForegroundColor Yellow
    Write-Host "The reset page always gives a neutral success message for unknown and cooldown-limited addresses." -ForegroundColor Yellow
} finally {
    Pop-Location
}
