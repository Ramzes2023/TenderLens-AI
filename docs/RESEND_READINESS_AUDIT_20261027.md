# Resend readiness audit — 27 October 2026

Scope: issue #334 and mail gates of #293. Audited current main d9446c0,
PR #328 (RFC 5322 headers), #331 (Resend-only), #332 (one-shot diagnostic),
issue history and local production backup evidence. No live deployment or email.

## Measured results

- Both 1.1.1.1 and 8.8.8.8: expected single DMARC TXT, DKIM key presence,
  send/rsend CNAME presence PASS. Presence is not message-level alignment proof.
- Protected Resend SMTP candidate: PASS, regular file, owner ubuntu, mode 0600.
  Existing candidate From is noreply@valyqon.dns.army; planned one-shot From
  remains team@valyqon.dns.army. Diagnostic now reports that difference rather
  than silently implying candidate and test are identical. No config was changed.
- Resend GET /domains and GET /emails with existing protected credential: HTTP 401
  on both. This proves current read access failed, not whether the key is revoked,
  incorrectly scoped or unsuitable for this API route. Do not replace the working
  SMTP credential or infer that SMTP is broken from these API responses.
- Existing production API container remains
  487088a88931b324d4e524f8f381bba165297642d5e70847e052278fc18124fd;
  image sha256:96f1b0826294ee97c2f29884c977673e0e4404d6aa96ce5d4b8f9ca1d534ad34.
  VALYQON_EMAIL_MODE=disabled; VALYQON_LEGAL_REQUIRED=true.
- One-shot marker absent. No message sent, including synthetic addresses.
  Earliest permitted test remains **2026-10-28 18:00 UTC**.
- 60 targeted offline tests PASS: verification, password recovery, canonical links,
  revocation after delivery errors, enumeration protection, RFC headers, diagnostic.
  Eight added execution cases run the actual embedded remote Python using fake I/O:
  early gate, marker collision, no-send audit, eligible single attempt, wrong sender,
  unsafe permissions, symlink, SMTP failure/redaction. No real sockets are used.
- Baseline main CI d9446c0: tests, Docker build, Windows fixture, source contract PASS.
  Baseline results do not substitute for this PR's CI.

## Backup / isolation evidence

Existing encrypted off-host backup mail-20261027T172146Z was authenticated and
restored previously. Re-ran the exact-live-image isolated auth suite on this restored
input: reset and verification expiry/replay, canonical reset origin, failure revocation,
enumeration, cross-origin, rate limits, legal signup rejection, account IDs and owner
links, integrity and foreign keys PASS. Network disabled; no production volume mounted.

Also ran an isolated configuration-return drill using original environment recovered
privately from encrypted container metadata. Exact production image instantiated SMTP
with an offline dummy key, then original disabled-mail configuration, each on a fresh
writable copy of restored DB. Both stages passed six GET routes, auth initialization,
legal registration rejection and protected auth/organization row parity. No message
was sent. Local runners/results remain private operational artifacts in the existing
workspace and server backup directory; no credentials were committed.

**Limit:** this is configuration/application recovery evidence, not a live cutover or
complete ordered-Compose deployment rollback rehearsal. That release gate stays open.
Backup still lives in temporary off-host storage and needs durable custody before release.

## Cause and remaining gates

Historical evidence: two real Gmail messages bounced with 550 5.7.1 "likely unsolicited";
Resend Support reportedly ruled out DNS/authentication and SMTP vs API transport.
New-domain reputation and/or content remain plausible, not separately proven causes.
Google documents several distinct 5.7.1 reasons; the full rejection text matters:
https://support.google.com/mail/answer/3726730

No evidence justifies changing DNS, weakening DMARC, rotating domains, using personal
Gmail SMTP, deleting suppressions, or repeatedly probing the rejected recipient.
Reference: https://resend.com/guides/email/new-domain-emails-going-to-spam

The date-gated no-link test can only narrow content/link vs sender reputation hypotheses;
it cannot prove a bona fide verification/reset template delivers or broad deliverability.
After its allowed time, preserve its marker and inspect the Resend event and actual
recipient Inbox/Spam before considering a separately approved account-email E2E.

Read-only provider access currently needs an authorized authenticated Resend session or
valid read-capable credential supplied through protected storage, never chat/GitHub.
Browser inventory exposed no browser connector; native Yandex access was not approved.
No settings or credentials were changed to work around that restriction.

Production remains BLOCKED on real recipient receipt, provider evidence, complete
isolated deployment rollback, fresh backup, bona fide auth-email E2E and separate legal
approval for public signup. No purchase or ownership of valyqon.ai is assumed.
