# Windows PowerShell 5.1 / PowerShell 7
# Operator-controlled fallback. Stages a protected SMTP candidate; never changes the running API.
param(
    [string]$FromAddress = "ramzesisayev444@gmail.com",
    [string]$TestRecipient = "ramzesisayev444@gmail.com",
    [switch]$SendOneTestEmail
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$OutputEncoding = New-Object System.Text.UTF8Encoding($false)

$sshKey = Join-Path $HOME ".ssh\tenderlens_vps_ed25519"
if (-not (Test-Path -LiteralPath $sshKey)) { throw "PINNED_SSH_KEY_MISSING" }
if ($FromAddress -notmatch '^[A-Za-z0-9._%+-]+@gmail[.]com$') {
    throw "FROM_MUST_BE_OWNED_GMAIL_ACCOUNT"
}
if ($TestRecipient -notmatch '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+[.][A-Za-z]{2,}$') {
    throw "INVALID_TEST_RECIPIENT"
}

Write-Host "VALYQON GMAIL SMTP CANDIDATE — NO PRODUCTION CUTOVER" -ForegroundColor Cyan
Write-Host "The Gmail From address must be an account you own; app passwords require Google 2-Step Verification."
Write-Host "An app password gives broad account access. Prefer an independent service Gmail account."
Write-Host "This script does NOT enable signup, customer emails, or password reset on production."
$approval = Read-Host "Type STAGE_GMAIL to stage the protected candidate"
if ($approval -cne "STAGE_GMAIL") { throw "OPERATOR_APPROVAL_NOT_GRANTED" }

$sshArgs = @(
    "-T", "-i", $sshKey,
    "-o", "BatchMode=yes",
    "-o", "IdentitiesOnly=yes",
    "-o", "StrictHostKeyChecking=yes",
    "-o", "ConnectTimeout=15",
    "ubuntu@63.189.75.15"
)

$secure = Read-Host "Enter the 16-character Google App Password (hidden)" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    # Google sometimes groups the 16 characters as four groups separated by spaces.
    $password = $password -replace '\s', ''
    if ($password -cnotmatch '^[A-Za-z]{16}$') {
        throw "GOOGLE_APP_PASSWORD_FORMAT_INVALID"
    }
    $candidateConfig = @(
        "VALYQON_EMAIL_MODE=smtp"
        "VALYQON_SMTP_HOST=smtp.gmail.com"
        "VALYQON_SMTP_PORT=465"
        "VALYQON_SMTP_USERNAME=$FromAddress"
        "VALYQON_SMTP_PASSWORD=$password"
        "VALYQON_SMTP_FROM=$FromAddress"
        "VALYQON_SMTP_SSL=true"
        "VALYQON_SMTP_STARTTLS=false"
        "VALYQON_PUBLIC_BASE_URL=https://valyqon.duckdns.org"
    ) -join [Environment]::NewLine

    # Secrets flow exclusively through SSH standard input, never command-line args,
    # a Git commit, console output, or the working repository.
    $remoteStage = 'set -eu; umask 077; install -d -m 700 /home/ubuntu/.config/valyqon; t=$(mktemp /home/ubuntu/.config/valyqon/google.smtp.XXXXXXXX); trap ''rm -f -- "$t"'' EXIT; cat > "$t"; chmod 600 "$t"; mv -f "$t" /home/ubuntu/.config/valyqon/google.candidate.env; echo CANDIDATE_STAGED=PASS'
    $candidateConfig | & ssh.exe @sshArgs $remoteStage
    if ($LASTEXITCODE -ne 0) { throw "CANDIDATE_STAGING_FAILED" }
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    Remove-Variable -Name password,candidateConfig,secure -ErrorAction SilentlyContinue
}

if ($SendOneTestEmail) {
    $sendApproval = Read-Host "Type SEND_ONE_TEST to send exactly one test to $TestRecipient"
    if ($sendApproval -cne "SEND_ONE_TEST") { throw "TEST_SEND_APPROVAL_NOT_GRANTED" }
}

$pythonProbe = @'
import os
import pathlib
import smtplib
import ssl
import stat
import sys
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid

candidate = pathlib.Path("/home/ubuntu/.config/valyqon/google.candidate.env")
config = {}
send_one = "__SEND_ONE__" == "yes"
recipient = "__RECIPIENT__"

try:
    mode = stat.S_IMODE(candidate.stat().st_mode)
    if mode != 0o600:
        raise RuntimeError("candidate permissions not 0600")
    for line in candidate.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        name, delimiter, value = line.partition("=")
        if delimiter:
            config[name.strip()] = value.strip()
    assert config["VALYQON_EMAIL_MODE"] == "smtp"
    assert config["VALYQON_SMTP_HOST"] == "smtp.gmail.com"
    assert config["VALYQON_SMTP_PORT"] == "465"
    assert config["VALYQON_SMTP_FROM"] == config["VALYQON_SMTP_USERNAME"]
    assert config["VALYQON_SMTP_USERNAME"].endswith("@gmail.com")
    assert config["VALYQON_SMTP_SSL"] == "true"
    assert config["VALYQON_SMTP_STARTTLS"] == "false"
    assert config["VALYQON_PUBLIC_BASE_URL"] == "https://valyqon.duckdns.org"
    assert len(config["VALYQON_SMTP_PASSWORD"]) == 16

    with smtplib.SMTP_SSL(
        "smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=20
    ) as smtp:
        smtp.login(
            config["VALYQON_SMTP_USERNAME"], config["VALYQON_SMTP_PASSWORD"]
        )
        print("GMAIL_CANDIDATE_AUTH=PASS", flush=True)
        if send_one:
            message = EmailMessage()
            message["From"] = config["VALYQON_SMTP_USERNAME"]
            message["To"] = recipient
            message["Subject"] = "VALYQON AI - controlled SMTP fallback check"
            message["Date"] = format_datetime(datetime.now(timezone.utc))
            message["Message-ID"] = make_msgid(domain="gmail.com")
            message.set_content(
                "Hello. This is one operator-authorized transactional mail "
                "delivery test for the VALYQON AI account system. No action is required."
            )
            refused = smtp.send_message(message)
            if refused:
                raise RuntimeError("recipient rejected during handoff")
            print("SMTP_HANDOFF=PASS", flush=True)
            print("REAL_INBOX_DELIVERY=NOT_VERIFIED", flush=True)

    print("PRODUCTION_API_UNCHANGED=YES", flush=True)
    print("GOOGLE_SMTP_CANDIDATE_READY=YES", flush=True)
except Exception as exc:
    # Do not print SMTP exceptions; some may embed credentials or message contents.
    print("GMAIL_CANDIDATE_AUTH_OR_SEND=FAIL", flush=True)
    print("ERROR_TYPE=" + type(exc).__name__, flush=True)
    sys.exit(1)
'@
$pythonProbe = $pythonProbe.Replace("__SEND_ONE__", $(if ($SendOneTestEmail) { "yes" } else { "no" }))
$pythonProbe = $pythonProbe.Replace("__RECIPIENT__", $TestRecipient)

$pythonProbe | & ssh.exe @sshArgs "python3 -"
$exitCode = $LASTEXITCODE
Write-Host "FINAL_PROBE_EXIT=$exitCode"
if ($exitCode -ne 0) { throw "GMAIL_CANDIDATE_NOT_READY — leave production unchanged" }

Write-Host "Protected candidate validated. Production API email remains disabled." -ForegroundColor Green
Write-Host "Next gates: real inbox receipt, off-server backup and isolated rollback, reviewed exact Compose overlay, live app auth E2E."
