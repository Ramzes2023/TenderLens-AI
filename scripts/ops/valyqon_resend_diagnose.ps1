# Safe Resend-only sender diagnostic. Default is no send; no production mutation.
param([switch]$SendOneResendTest)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$OutputEncoding = New-Object System.Text.UTF8Encoding($false)

$domain = "valyqon.dns.army"
$key = Join-Path $HOME ".ssh\tenderlens_vps_ed25519"
if (-not (Test-Path -LiteralPath $key)) { throw "PINNED_SSH_KEY_MISSING" }

foreach ($resolver in @("1.1.1.1", "8.8.8.8")) {
    $dmarc = @(Resolve-DnsName -Name "_dmarc.$domain" -Type TXT -Server $resolver -ErrorAction Stop |
        Where-Object { $_.Type -eq "TXT" } | ForEach-Object { $_.Strings -join "" })
    if ($dmarc.Count -ne 1 -or $dmarc[0] -ne "v=DMARC1; p=none;") {
        throw "DMARC_COUNT_OR_VALUE_INVALID"
    }
    Write-Host ("DNS_{0}_DMARC=PASS" -f $resolver)

    $dkim = @(Resolve-DnsName -Name "resend._domainkey.$domain" -Type TXT -Server $resolver -ErrorAction Stop |
        Where-Object { $_.Type -eq "TXT" } | ForEach-Object { $_.Strings -join "" })
    if (@($dkim | Where-Object { $_ -match '(^|;)\s*p=[A-Za-z0-9+/=]+' }).Count -lt 1) {
        throw "DKIM_RECORD_NOT_FOUND"
    }
    Write-Host ("DNS_{0}_DKIM_PRESENT=PASS" -f $resolver)

    foreach ($alias in @("send", "rsend")) {
        $answers = @(Resolve-DnsName -Name "$alias.$domain" -Type CNAME -Server $resolver -ErrorAction Stop)
        if (@($answers | Where-Object { $_.Type -eq "CNAME" }).Count -lt 1) {
            throw "RESEND_SENDING_CNAME_MISSING"
        }
        Write-Host ("DNS_{0}_{1}_CNAME_PRESENT=PASS" -f $resolver, $alias)
    }
}
Write-Host "RESEND_DNS_PUBLIC_RECORDS=PASS"
Write-Host "RESEND_VERIFICATION_DASHBOARD=REQUIRES_OPERATOR_CHECK"
Write-Host "REAL_GMAIL_DELIVERY=NOT_VERIFIED"

if ($SendOneResendTest) {
    Write-Host "From: team@valyqon.dns.army via RESEND; To: controlled Gmail inbox only."
    Write-Host "This sends ONE plain-text test, with no links. No production cutover."
    $consent = Read-Host "Type SEND_ONE_RESEND_TEST to authorize the controlled test"
    if ($consent -cne "SEND_ONE_RESEND_TEST") { throw "OPERATOR_APPROVAL_NOT_GRANTED" }
}

$remote = @'
import os
import pathlib
import smtplib
import ssl
import stat
import sys
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from email.utils import parseaddr

mode = "__MODE__"
secret = pathlib.Path("/home/ubuntu/.config/valyqon/resend.env")
one_time_marker = pathlib.Path("/home/ubuntu/.config/valyqon/resend-gmail-hello-once.marker")
earliest = datetime(2026, 10, 28, 18, 0, tzinfo=timezone.utc)
try:
    secret_stat = secret.lstat()
    if (not stat.S_ISREG(secret_stat.st_mode)
            or stat.S_IMODE(secret_stat.st_mode) != 0o600
            or secret_stat.st_uid != os.getuid()):
        raise ValueError("Unsafe email-secret file permissions")
    cfg = {}
    for line in secret.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        k, sep, v = line.partition("=")
        if sep:
            cfg[k.strip()] = v.strip().strip('"')
    if not (
        cfg.get("VALYQON_EMAIL_MODE") == "smtp"
        and cfg.get("VALYQON_SMTP_HOST") == "smtp.resend.com"
        and cfg.get("VALYQON_SMTP_PORT") == "465"
        and cfg.get("VALYQON_SMTP_USERNAME") == "resend"
        and cfg.get("VALYQON_SMTP_SSL") == "true"
        and cfg.get("VALYQON_SMTP_STARTTLS") == "false"
        and parseaddr(cfg.get("VALYQON_SMTP_FROM", ""))[1] in {
            "team@valyqon.dns.army", "noreply@valyqon.dns.army"
        }
        and cfg.get("VALYQON_PUBLIC_BASE_URL") == "https://valyqon.duckdns.org"
        and cfg.get("VALYQON_SMTP_PASSWORD", "").startswith("re_")
    ):
        raise ValueError("Protected Resend candidate config invalid")

    print("AWS_RESEND_CONFIG=PASS", flush=True)
    print("CONTROLLED_FROM_MATCHES_CONFIG=" + (
        "YES" if parseaddr(cfg["VALYQON_SMTP_FROM"])[1] == "team@valyqon.dns.army" else "NO"
    ), flush=True)
    if mode == "audit":
        print("EMAIL_SENT=NO", flush=True)
        print("LIVE_API_AND_SQLITE_CHANGED=NO", flush=True)
        sys.exit(0)

    now = datetime.now(timezone.utc)
    if now < earliest:
        print("CONTROLLED_TEST=TOO_EARLY", flush=True)
        print("EARLIEST_UTC=" + earliest.isoformat(), flush=True)
        sys.exit(3)

    # O_EXCL prevents accidental repeats/concurrent tests even if the prior send bounced.
    try:
        fd = os.open(str(one_time_marker), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        print("CONTROLLED_TEST=ALREADY_ATTEMPTED", flush=True)
        sys.exit(4)
    with os.fdopen(fd, "w") as out:
        out.write(now.isoformat() + "\n")

    message = EmailMessage()
    message["From"] = "VALYQON AI <team@valyqon.dns.army>"
    message["To"] = "ramzesisayev444@gmail.com"
    message["Subject"] = "hello"
    message["Date"] = format_datetime(now)
    message["Message-ID"] = make_msgid(domain="valyqon.dns.army")
    message.set_content("hello world\n")
    with smtplib.SMTP_SSL(
        "smtp.resend.com", 465, timeout=20, context=ssl.create_default_context()
    ) as client:
        client.login("resend", cfg["VALYQON_SMTP_PASSWORD"])
        print("RESEND_SMTP_AUTH=PASS", flush=True)
        rejected = client.send_message(message)
        if rejected:
            raise RuntimeError("Recipient SMTP handoff rejected")
    print("RESEND_HANDOFF=PASS", flush=True)
    print("REAL_GMAIL_DELIVERY=NOT_YET_VERIFIED", flush=True)
    print("LIVE_API_AND_SQLITE_CHANGED=NO", flush=True)
except Exception as exc:
    # Do not print SMTP exception details: they may contain message or credentials.
    print("DIAGNOSTIC=FAIL", flush=True)
    print("ERROR_TYPE=" + type(exc).__name__, flush=True)
    sys.exit(2)
'@
$remote = $remote.Replace("__MODE__", $(if ($SendOneResendTest) { "send" } else { "audit" }))
$sshArgs = @(
    "-T", "-i", $key,
    "-o", "BatchMode=yes",
    "-o", "IdentitiesOnly=yes",
    "-o", "StrictHostKeyChecking=yes",
    "-o", "ConnectTimeout=15",
    "ubuntu@63.189.75.15", "python3 -"
)
$remote | & ssh.exe @sshArgs
$exitCode = $LASTEXITCODE
Write-Host "RESEND_DIAGNOSTIC_EXIT=$exitCode"
if ($exitCode -ne 0) { throw "RESEND_DIAGNOSTIC_INCOMPLETE" }
Write-Host "PRODUCTION_EMAIL_DEPLOYED=NO"
