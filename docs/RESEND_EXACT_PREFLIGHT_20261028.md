# Exact production mail preflight — 28 October 2026

Base main: `1c12b34b3b723a227826509b0b55503d11c151f0`, merged PR #340.
Issues #293 and #334 remain open. No real message, production deployment,
registration activation, user-data mutation or Resend configuration change.

## Fresh independent evidence

Official Resend MCP read-only domain and historical request-log reads reconfirmed:

- `valyqon.dns.army` verified, EU sending enabled; DKIM and both sending CNAMEs
  verified; open/click tracking disabled. `valyqon.ai` not_started; no ownership
  assumption or sender switch.
- Both 27 October Gmail messages remain bounced, `Transient / ContentRejected`,
  SMTP `550 5.7.1`. First had no URL, second had one. Link removal and changing
  sender localpart have not demonstrated a remedy. Domain/IP reputation versus
  content contribution remains unresolved. No actual inbox receipt is proved.
- Exactly five historical messages are listed, three synthetic recipients and
  two Gmail bounces; no new send. Raw recipients, IDs, bodies and IPs omitted.
- Both public resolvers' DMARC/DKIM/send/rsend checks PASS; protected Resend
  candidate config PASS. No-send diagnostic exit 0. Planned team probe differs
  from protected noreply sender; a successful probe cannot alone qualify the
  actual account-email sender/template.

## Exact Compose check actually executed

`scripts/ops/resend_production_preflight.py` was piped over pinned SSH and ran
only Docker inspect/image inspect/volume inspect/compose config. Resolved
secrets stayed private. A mode-0600 temporary candidate was deleted afterwards.

Live Compose labels identify `/opt/tenderlens`, project `tenderlens-vps`:

1. compose.public.yaml
2. compose.phase20.runtime.yaml
3. compose.phase21.domain.yaml
4. compose.release-a98a7ff.yaml
5. compose.public-demo-821bd6b.yaml

Environment interpolation uses `.env` then `.env.public.runtime` in that order.
The candidate selects only nine mail keys from the existing protected regular
file (owner and mode 0600 checked); dollar characters are escaped for Compose.
It preserves the configured noreply sender. It does not import arbitrary extra
secret-file settings. This candidate is not installed or activated.

Measured PASS: original resolved API environment equals running API environment;
candidate differs only in allowlisted API mail settings; all other service,
image, volume, legal, routing and application settings equal original; original
image tag still resolves to running immutable image ID; named-volume mountpoint
identities match; original resolved config repeats identically; API/Caddy IDs,
images, mount mappings and start times unchanged. Mail disabled, legal required.

This closes exact *configuration* preflight, not a live cutover rehearsal. The
six-service sanitized lifecycle rollback in #340 remains the executed rollback
evidence. Public-port/ACME/live-volume replacement has not been exercised and is
not authorized. Before a future approved API-only cutover, refresh preflight and
backup, pin the existing image ID, preserve every original overlay/env file,
and validate rollback using the original ordered command and no candidate.
Never rebuild, pull, operate on Caddy, or recreate the whole stack for mail.

## Backup limitation

The attempted fresh encrypted off-host backup command was rejected by automatic
approval review **before execution**: it duplicates production SQLite, environment
files and container metadata containing user data/secrets on server and local
backup storage, and that sensitive duplication lacked specific user approval.
No workaround or indirect retry was made. The earlier verified encrypted backup
and restore evidence in #340 remains historical, not a fresh cutover backup.
Refreshing it needs express owner authorization for that exact scope and custody.

## Delivery and account-email E2E execution plan

1. Keep production mail disabled and legal registration blocked. Recheck current
   UTC, Resend history and marker. The earliest probe is **2026-10-28 18:00 UTC**;
   elapsed time alone grants no permission. Existing marker means STOP.
2. Only after separate owner approval use the unchanged
   `valyqon_resend_diagnose.ps1 -SendOneResendTest` with its interactive consent,
   atomic O_EXCL marker and fixed owner-controlled recipient. Exactly one plain
   text `hello world`, Resend only; no links or production cutover. No MCP send
   substitute. On timeout, rejection, ambiguity or bounce: STOP, preserve marker,
   inspect existing events, never resend.
3. Correlate provider event/time privately through official MCP and obtain actual
   recipient Inbox/Spam receipt/time. Publish only fixed result categories and
   UTC times. SMTP acceptance or synthetic delivered is insufficient.
4. If that succeeds, separately authorize **two bona fide account emails**, one
   verification and one reset, using the configured noreply identity, actual
   application templates, a disposable test account/database and an isolated
   owner-accessible HTTPS instance. No existing user account, public production
   registration or production mail mode is changed. Provisioning this real-mail
   instance is deferred until the prior delivery gate passes; no send-capable
   harness is run by CI. Confirm receipt and provider outcome for verification
   before requesting reset. Any refusal/timeout stops the sequence without retry.
5. Open the received verification link privately, verify authenticated identity,
   reject token replay; request reset once, confirm its provider event and actual
   receipt, use received link, verify session revocation, reject old password,
   accept new password, reject reset replay and preserve account/organization IDs.
   Check token expiry and cross-origin/enumeration/rate-limit behavior offline.
   Never publish credentials, cookies, tokens, URLs or message bodies.
6. Publish verification/reset provider and recipient results separately. Remove
   isolated account artifacts safely; production remains unchanged. Delivery,
   fresh restore/rollback readiness, health and separate legal/operator release
   approval must all pass before a production activation proposal.

`test_auth_mail_roundtrip.py` now executes the API → actual SMTP templates →
verification → reset → new login sequence with TLS SMTP intercepted in memory,
disposable SQLite, canonical links, RFC headers, replay rejection, revoked old
session/password and preserved authenticated identity. This is offline integration
evidence, **not** real email E2E. Existing tests cover expiry/failure/enumeration.

No speculative template or DNS fix is deployed: evidence does not establish an
application defect responsible for Gmail rejection. New preflight tests reject
image, volume, proxy, legal, provider, extra-env and missing-credential drift.

Next owner decision: separately approve the single gated probe; additionally,
approve fresh encrypted backup duplication before any cutover work. A later
genuine account-email test requires its own approval after probe success. None
of these approvals authorizes production deployment or legal launch.
