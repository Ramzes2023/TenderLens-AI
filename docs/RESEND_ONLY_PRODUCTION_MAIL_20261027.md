# VALYQON AI: Resend-only production email policy (2026-10-27)

## Owner decision

**Resend is the sole email sending provider for VALYQON AI.** Never use
the owner's personal Gmail account as an SMTP sender. The unapproved
Gmail fallback was removed after operator correction. No Google
App Password is needed or accepted for VALYQON.

The publicly available site is `https://valyqon.duckdns.org/`.
Live production auth email remains disabled until its delivery and
rollback gates are satisfied. Existing customers' accounts, SQLite
volume, password hashes, preview, and Caddy must not be mutated
as part of sender-domain diagnostics.

## Verified facts

- Resend sending domain `valyqon.dns.army` was verified in the Resend
  dashboard. Sending was enabled and receiving was disabled.
- Two separate DNS resolvers observed exactly one `v=DMARC1; p=none;`
  record at `_dmarc.valyqon.dns.army`, after a transient duplicate.
  Public DKIM and sender CNAMEs were staged.
- Protected sender configuration is stored on the AWS host in
  `/home/ubuntu/.config/valyqon/resend.env` with mode 0600.
  It must NEVER be committed, logged, printed or pasted in chat.
- SMTP authentication and handoff to Resend using smtp.resend.com:465
  already passed.
- A synthetic Resend test to `delivered@resend.dev` was delivered.
  **This does not prove real inbox delivery.**
- **Two owner-authorized real Gmail probes both bounced with
  Gmail `550 5.7.1 likely unsolicited mail`:**
  First sender `noreply@valyqon.dns.army`; second sender
  `team@valyqon.dns.army`. Changing DMARC and the From address did
  not resolve the rejection.
- Resend Support investigated both events and reported that DNS/
  authentication alignment and SMTP/Forge route are not the cause.
  Gmail's rejection concerns **new sending-domain reputation and/or
  message content**. The newly verified free dynamic-DNS subdomain
  lacks a trusted brand sending history. This is not a certainty that
  changing email body or domain alone will succeed.
- Separately, GitHub PR #328 corrected Date and Message-ID headers
  for the app's three transactional SMTP message types and was merged,
  but **the deployed AWS image was not updated**.

## Next actions — remain Resend only

1. **No further test storms, spoofing or manufactured reputation.**
   Do not repeatedly retry bounced Gmail recipients, remove valid
   suppressions to evade policy, send unsolicited messages, rotate
   free DNS domains, or hide actual delivery failures. This is
   consistent with Resend Support's guidance.
2. **Prefer a verified operator-owned branded domain**, e.g.
   `auth.valyqon.ai` **only if the operator legitimately owns
   `valyqon.ai` and has DNS record access**. Being listed as an
   unverified Resend domain entry does not prove DNS ownership.
   Never change or buy domain names without the operator's consent.
3. For a legitimate new sending subdomain, add it under Resend →
   Domains, choose the correct region, publish **only the exact
   DNS records Resend issues** (including DKIM, appropriate
   return-path SPF/MX or Forge CNAME where provided) in the
   operator-owned DNS. Wait until Resend status becomes Verified.
   Publish exactly one DMARC policy TXT in the relevant namespace;
   do not replace existing unrelated production records.
4. Use a stable product address such as
   `VALYQON AI <team@auth.valyqon.ai>` once this domain is
   verified. Ensure Reply-To points to a **monitored** mailbox;
   an unmonitored address is not made functional by adding a
   header. Keep website and brand details consistent and legitimate.
5. If continuing with verified `valyqon.dns.army` in the short
   term, Resend Support advised waiting between tests, then
   **one explicitly owner-approved** plain-text `hello world`
   diagnostic to the owner's own Gmail, without links/images/HTML.
   If it bounces, collect exact event and provider refusal and
   stop. Never treat SMTP acceptance as receipt.
6. Send only transactional messages users request or explicitly
   opt into. Gradually build a genuine positive sending history
   with real consenting testers, respecting low volumes and
   complaints. No paid warm-up networks or artificial engagement.
   Recheck Resend delivery events and actual inbox reception.
7. On **proven real-inbox success** and an isolated data-safe rollback
   rehearsal: create a *private*, minimal Compose overlay for the
   existing exact production API with environment from the protected
   `resend.env`. Retain existing ordered overlays, original image,
   named SQLite volume and off-server encrypted backup. Never
   blindly redeploy current GitHub main over the existing demo.
   Verify live login, reset link on the right public hostname,
   token single-use, original database rows/hash parity, existing
   public HTTPS, and rollback. Keep signup legal gate enabled.
8. Keep email disabled in production if Gmail remains rejected or
   if recipient delivery is not verified. This is honest fail-closed
   behavior rather than a broken password recovery promise.

References:
- https://resend.com/guides/email/new-domain-emails-going-to-spam
- https://resend.com/docs/knowledge-base/is-it-better-to-send-emails-from-a-subdomain-or-the-root-domain
- https://resend.com/docs/forge
- https://support.google.com/mail/answer/81126

Tracked in GitHub issue #293. Owner's actual support response documents
the two specific bounce event URLs; do not publish API keys.

## Resend-only controlled diagnostic in PR #332

The new script path is scripts/ops/valyqon_resend_diagnose.ps1.
Run from an up-to-date trusted working copy:

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\ops\valyqon_resend_diagnose.ps1

The default mode is NO-SEND. It checks DMARC, DKIM and the two Resend
sending CNAMEs against both 1.1.1.1 and 8.8.8.8, and validates the
protected AWS resend.env without logging its API key. It never modifies
the live VALYQON API, database, demo or Caddy.

Resend Support specifically advised a single spaced plain-text test
without any links to distinguish message-content filtering from
sender-domain reputation. No earlier than 2026-10-28 18:00 UTC, the
operator may explicitly approve ONE probe:

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\ops\valyqon_resend_diagnose.ps1 -SendOneResendTest

After the required typed SEND_ONE_RESEND_TEST confirmation, the script
sends hello world FROM team@valyqon.dns.army via Resend TO the owner's
authorized Gmail address as a recipient only. An atomic 0600 marker on
AWS permanently blocks unreviewed repeat attempts, even if Gmail bounces.

Decision path: If this minimal link-free message arrives, investigate
earlier message contents and linked DuckDNS URL reputation with a
separate authorized template test only after security rollback proof.
If it again bounces with Gmail 550 5.7.1, stop repetitive testing and
prefer an operator-owned branded domain verified inside Resend, with
gradual genuine opt-in sending. A new branded domain is NOT an instant
reputation fix. One recipient receiving one test is NOT proof of broad
deliverability. Synthetic delivered@resend.dev is only integration proof.

Google Postmaster Tools can be useful once domain DNS ownership is
verified and there is sufficient traffic. Low-volume domains can have
no visible telemetry: https://support.google.com/mail/answer/9981691.


## Update: Resend engineering response, 2026-10-28 19:54 UTC

Resend Customer Success Engineer Brian reviewed the two original recipient
bounces and confirmed Gmail — not Resend — classified the messages as suspected
unsolicited email. Resend cannot override Google's classification. His explicit
recommendations: use a domain that the operator actually owns and controls
(rather than a shared-domain namespace), and prefer account-email links whose
hostname matches the sending domain. The original no-link probe also bounced,
so the URL mismatch is a deliverability risk, **not** an established sole cause.

Current operational mismatch:
- Sender mailbox domain: `valyqon.dns.army`.
- Canonical account-verification and reset links: `valyqon.duckdns.org`.
- Neither an entry for `valyqon.ai` in Resend nor a historical DNS record
  proves operator ownership of `valyqon.ai`.
- The old two probes still do **not** prove current app templates deliver.
- Resend MCP excluded recipient suppression (get 404, list empty).
- No provider-supported bypass, sender allowlist or SMTP code-only fix has
  been identified.

The read-only exact Compose preflight now reports
`sender_link_host_alignment=DIFFERENT_HOST` and
`sender_link_review_required=true` for the existing candidate. This is
**an advisory review gate**, not proof of SPF/DKIM/DMARC failure and not an
automatic DNS ownership check. An exact hostname match is a conservative
criterion; sibling subdomains on a legitimately owned parent may also be
acceptable once separately reviewed.

### Production-safe next path (no action authorized here)

1. Establish that the owner legitimately controls a branded domain's DNS.
   If `valyqon.ai` is not owned, obtaining a domain requires a separate
   explicit user purchase/ownership decision. Do not assume or buy one.
2. Set up the operator-controlled public app hostname with a valid certificate
   and intact existing HTTPS/legacy redirect, and a Resend sender domain or
   subdomain under the same legitimately owned brand. The website hostname and
   sending subdomain need not literally be identical if the provider confirms
   their branded-domain relationship meets its URL guidance; preserve the
   explicit review warning until confirmed.
3. Verify the exact records Resend provides for the selected sender, including
   DKIM, SPF/bounce Return-Path and DMARC. Keep secrets in server-protected
   configuration and do not alter existing production Compose/Caddy for
   read-only diagnosis.
4. Prepare a strictly limited auth-mail-only candidate with approved URL
   and `From` values, independent real verification and reset acceptance
   with specific user consent, recipient Inbox/Spam receipt and Resend event
   evidence. Maintain one-time controls. Mail provider acceptance alone is not
   recipient acceptance.
5. Obtain explicit approval for a fresh sensitive backup/restore operation,
   verify immutable image+volume rollback, and preserve the legal readiness
   gate before any public signup or production release.

Resend case: existing owner support thread, 28 October 2026. Its final message
provides advice, not a Gmail delivery guarantee.
