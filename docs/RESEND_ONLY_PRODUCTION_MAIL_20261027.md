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
