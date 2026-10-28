# Controlled account-mail acceptance — 28 October 2026

Reviewed main: 6cef2a431df7873f108488d578a1265fb265e470.
Related: #293, #334; merged readiness PRs #336, #338, #340, #341.
This is an execution checklist, not a send authorization or delivery certificate.

## Fresh observations (11:49–11:54 UTC)

Official Resend MCP lists five messages: two historical real-recipient bounces
and three synthetic resend.dev deliveries. Both existing raw GET-email response
logs reconfirm Transient / ContentRejected, Gmail 550 5.7.1 likely unsolicited.
The first message had no URL; the second included the website URL. Different
provider IPs and sender localparts did not prevent rejection. Domain/IP
reputation and content contributions cannot be separated from this evidence.
No new real message was sent. No recipient receipt has been demonstrated.

Resend reports valyqon.dns.army verified, sending enabled in eu-west-1,
DKIM and both sending CNAME records verified, open/click tracking off.
valyqon.ai remains not_started; its listing is not ownership evidence.
GET /health, /register, /verify-email, /forgot-password, /reset-password,
/login all returned HTTPS 200. Page availability does not prove mail delivery.
Current-main GitHub check runs: eight completed successfully, including tests,
Windows fixture and Docker build. Production settings/database were not
re-read in this pass; prior disabled/legal-required evidence is historical.
No production change, backup copy, DNS mutation or marker operation occurred.

## Code review

FastAPI registration issues a verification token and uses the configured public
origin for /verify-email. Failed delivery reports verification_sent=false and
revokes the token. Resend-verification supports recovery from failed signup
delivery; existing-account registration is not a resend mechanism.

Verification defaults to 30 minutes (service constructor permits 5–1440).
Password-reset tokens expire in 30 minutes. Both use random 32-byte
URL-safe secrets with hashed storage and single-use consumption.
Default request cooldown is 60 seconds; route rate limits also apply.
Reset requests for unknown/inactive/cooldown accounts return the same accepted
response. A synchronous delivery error revokes the issued reset token while
retaining the generic response. Reset invalidates prior sessions and tickets,
preserves identity and does not verify an unverified email.

SMTPEmailSender supplies Date and Message-ID, actual plain-text auth templates,
TLS certificate validation and bounded timeouts. SMTP success is only provider
handoff: a later Gmail bounce is not synchronously returned to FastAPI.
No application fix responsible for these Gmail rejections is established.

## Gate 0: existing single probe

Do not run before 2026-10-28 18:00:00 UTC or without separate explicit owner
approval. Use only the unchanged scripts/ops/valyqon_resend_diagnose.ps1
-SendOneResendTest workflow and its typed SEND_ONE_RESEND_TEST consent.
Recheck provider history and the existing atomic marker first. Never remove,
replace or bypass the marker; ambiguity consumes the attempt and means STOP.
Do not substitute MCP/API sending. Team/plain-text success does not qualify
noreply account templates. Current time in this pass was before the gate.

## E2E A: registration (prepared, NOT EXECUTED)

Prerequisites: gate 0 successful with actual recipient receipt; separate approval
for exactly one verification email; controlled mailbox and disposable account;
owner-accessible isolated HTTPS instance, empty disposable database and actual
application templates/approved noreply From. Record exact image, public origin,
recipient scope and consent privately. Do not copy production users or disable
the production legal gate. If required legal documents/consents are unavailable,
STOP registration; direct database insertion is not registration E2E.

1. GET registration and verification pages. Confirm configured HTTPS origin.
2. Submit /api/v1/auth/register once with required legal version/consents.
   Expect 201, verification_required=true, verification_sent=true.
3. Confirm exactly one matching provider message and actual Inbox/Spam receipt;
   record UTC time/location privately. SMTP acceptance alone is insufficient.
4. Before expiry, open the received link privately and complete the page flow.
   Verify /api/v1/auth/me identifies the controlled account.
5. Reuse the token once: expect rejection and no state change. Login succeeds
   only after verification. Record account/organization IDs privately.
6. On bounce, absent receipt, timeout or ambiguous response: STOP. Do not resend.
   Test expiry, cooldown, delivery failures and rate limits offline, not by
   additional real mail.

## E2E B: password reset (prepared, NOT EXECUTED)

Requires E2E A success and separate approval for exactly one reset email.
Use the same disposable verified account and actual noreply template.
Keep a pre-reset session in a separate private browser context.

1. Submit /api/v1/auth/forgot-password once. Expect generic 202.
2. Independently confirm matching provider outcome AND actual mailbox receipt.
   Record UTC time/location separately from registration.
3. Open the received /reset-password link on the configured HTTPS origin within
   30 minutes; choose a new policy-compliant password and submit once.
4. Expect success; old session and old password fail; new password succeeds.
   Account and organization identities must equal those recorded for E2E A.
5. Replay reset token: expect 422. No additional mail request is needed.
6. Stop on bounce/timeout/ambiguity; no automatic retry. Delete only authorized
   disposable test artifacts after evidence is recorded; never production users.

For each case record: consent reference, tested immutable image, execution UTC,
provider outcome/time, recipient receipt/location/time, link-origin match,
token replay result and final status. Keep message IDs, addresses, passwords,
cookies and token-bearing links private. Missing receipt means NOT_VERIFIED.

## Operator-owned branded domain plan (conditional)

A branded domain is a possible legitimate identity improvement, not a proven
cure or a prerequisite established by these two bounces. First obtain evidence
of operator ownership and authoritative DNS control plus explicit permission
for named records. Do not assume control of valyqon.ai or buy a domain.

1. Select an approved dedicated auth subdomain and region; inspect existing
   zone records privately and prepare exact before/after/rollback values.
2. Only after approval add that domain in Resend; retrieve its generated records
   via get_domain. Do not reuse current-domain DKIM or guess new DNS values.
3. Prepare a reviewable DNS change set using EXACT generated names/types/values,
   TTL and region-specific return-path records. Existing Forge uses CNAMEs;
   other setups may require SPF/MX. Avoid conflicting CNAME/TXT/MX records,
   duplicate SPF or DMARC policies, and unrelated inbound MX changes.
4. After record-specific approval, publish only that change set; verify public
   resolution, Resend verified status and DMARC alignment. Keep tracking off.
   Roll back only added/changed records to recorded prior values if needed.
5. Prepare stable noreply identity and an actually monitored support mailbox.
   Do not use personal Gmail as From. A sender/link-origin change requires
   renewed guarded acceptance approval; never bypass the existing one-shot
   sender allowlist or marker to test a new domain.

Reference: https://resend.com/docs/dashboard/domains/introduction
Gmail rejection categories: https://support.google.com/mail/answer/3726730
A verified domain does not guarantee recipient acceptance.

## Minimal production proposal (NOT AUTHORIZED)

Only after both actual-template E2Es and recipient receipts, fresh authorized
encrypted backup/restore, rollback readiness, health checks and release approval:
rerun exact ordered Compose preflight; pin the existing immutable API image;
preserve original env/overlays and SQLite volumes. Prepare a private overlay
changing only approved API mail settings. Recreate only API with no build/pull
or dependencies. Keep public registration legally gated. Check HTTPS/auth,
non-sensitive identity parity and delivery evidence. On failure remove the
candidate from the ordered command and recreate only API with original image
and original settings. Validate health and disabled mail; no volume deletion.
Do not activate this proposal now.

A fresh off-host backup was rejected in the earlier #341 session by automated
authorization review because it duplicates production user data and secrets.
This pass did not retry it. A later fresh backup needs separate explicit
authorization for scope, encrypted storage and custody.

REGISTRATION_EMAIL_STATUS=NOT_VERIFIED_REAL_DELIVERY
PASSWORD_RESET_EMAIL_STATUS=NOT_VERIFIED_REAL_DELIVERY
RESEND_DELIVERY_STATUS=BLOCKED_GMAIL_CONTENTREJECTED
PRODUCTION_DEPLOYMENT_STATUS=NOT_ACTIVATED

Validation on the reviewed main: 71 targeted offline tests passed (one upstream
Starlette deprecation warning). Temporary test storage was kept in the workspace.
