# VALYQON temporary Gmail SMTP candidate — NOT a production deployment

## Purpose

The operator's verified Resend subdomain valyqon.dns.army bounced twice at Gmail
with 550 5.7.1 likely unsolicited mail. Resend Support attributed this to sending
domain reputation and/or message content, not transport credentials or DNS
authentication. Do not repeat Resend tests indiscriminately.

The existing public website https://valyqon.duckdns.org/ must keep its demo
image, SQLite users, Caddy HTTPS, and old fallback hostname.

For explicitly operator-approved temporary low-volume fallback, the already
provider-neutral SMTPEmailSender can use Google Gmail SMTP with a Google App
Password for an owned Google account. Prefer an independent service account
rather than the owner's personal Gmail; app passwords grant broad account
access and Google advises Sign in with Google for apps where possible.
This candidate is NOT suitable for bulk commercial sending.

Google references:
https://support.google.com/mail/answer/185833
https://support.google.com/mail/answer/22839
https://support.google.com/mail/answer/81126

## Operator command (Windows PowerShell)

Prerequisites: existing pinned host SSH access with key under
$HOME\.ssh\tenderlens_vps_ed25519, Gmail 2-Step Verification, and a Google App
Password (16 characters) for a Gmail account the operator actually owns.
Do not paste the password into chat, code or GitHub.

From C:\Users\ramze\TenderLens-AI run:

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\ops\valyqon_gmail_fallback_candidate.ps1

This ONLY stages a protected candidate under
/home/ubuntu/.config/valyqon/google.candidate.env (mode 0600) and tests SSL
SMTP authentication. It DOES NOT modify the already-protected Resend config,
Docker Compose, production database or enabled API email mode.

For one explicitly approved controlled inbox check:

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\ops\valyqon_gmail_fallback_candidate.ps1 -SendOneTestEmail

For a different authorized test mailbox, additionally pass -TestRecipient.
Do not automate repeated tests. SMTP handoff proves transport acceptance,
not mailbox delivery. Independently verify with the recipient.

If Google App Password is unavailable or authentication fails, stop. Never
work around Google account restrictions.

## Remaining release gates

1. Real controlled recipient inbox received test mail, not a synthetic sink.
2. Fresh consistent production SQLite backup, encrypted off-host custody with
   separately protected key, isolated restore and exact image rollback rehearsal.
3. Inspect the true five production Compose overrides and their effective
   precedence. Running demo image differs from current main: never blindly
   redeploy latest main just to activate SMTP.
4. Attach only a private verified SMTP environment overlay, after operator
   approval and backups, then recreate only production API if justified.
5. Verify public HTTPS, premium demo, existing account rows/hashes/links,
   login and reset flows, session/token isolation, and error rate limits.
6. Keep VALYQON_LEGAL_REQUIRED=true; do not open new signups until the
   operator has approved legal materials.

Successful candidate SMTP login is NOT a production mail deployment.
The public API currently remains VALYQON_EMAIL_MODE=disabled until a later
explicit release after these gates.
