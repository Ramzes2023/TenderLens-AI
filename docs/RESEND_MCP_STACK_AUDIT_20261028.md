# Resend delivery evidence and isolated runtime rollback — 28 October 2026

Base: main `9df630e437ef605ed3f6fa109a3b3fd299f8993a` (merged #338).
Delivery remains **unproven**. No message sent, production deployment, domain/key
change, suppression removal or legal/signup activation was performed.

## Independently observed provider evidence

Official Resend remote MCP was connected and used **only for reads**:
list/get domains, list/get emails, metrics, suppression lookup, list webhooks,
list logs and get log. No API key was copied from the production SMTP config.

The `get_email` human-readable summary omitted the bounce object. Reading the
existing GET-email request's response through `list_logs` → `get_log` exposed
the actual `bounce.type`, `subType` and `diagnosticCode`. These are existing
provider records; retrieving a request log neither replays it nor sends mail.
No webhook existed, so this does not supply a historical webhook event timeline.

| Sent UTC, 27 October | Resend last event | Bounce type / subtype | SMTP diagnosis |
| --- | --- | --- | --- |
| 17:14:18 | bounced | Transient / ContentRejected | 550 5.7.1, likely unsolicited mail |
| 17:44:08 | bounced | Transient / ContentRejected | 550 5.7.1, likely unsolicited mail |

Both historical SMTP submissions have HTTP 200 API logs (`resend-smtp:1.0.0`),
followed by bounced status. They used different provider sending IPs. The first
was plain text without a URL, using noreply; the second used team on the same
domain and included a public-site URL. A link is therefore **not necessary** for
the observed rejection. Neither changing localpart/display name nor the second
message's longer wording demonstrated delivery. No causal A/B claim is possible.
Neither message was an actual account verification/reset transaction.

Metrics for 27–28 October: sent 3, delivered 1 (synthetic Resend address), bounced 2,
transient 2, permanent 0, complaints 0, suppressed 0. The controlled recipient's
suppression lookup returned 404/not found. This is not permission to retry.
Recipient addresses, message IDs, IPs, bodies and token-bearing URLs are omitted
from this report and the PR. `resend_delivery_evidence.summarize` publishes only
allowlisted categories and protocol codes; it never asserts inbox receipt.

Domain `valyqon.dns.army`: verified, sending enabled, EU region; DKIM and both
sending CNAME records verified; open/click tracking disabled. `valyqon.ai` remains
not_started: appearance in the account proves neither ownership nor permission
to use it. No domain switch is proposed.

Fresh default **no-send** diagnostic: both 1.1.1.1 and 8.8.8.8 DMARC, DKIM and
send/rsend CNAME checks PASS; protected AWS Resend configuration PASS; exit 0;
EMAIL_SENT=NO; LIVE_API_AND_SQLITE_CHANGED=NO. Planned team sender differs from
protected noreply sender (CONTROLLED_FROM_MATCHES_CONFIG=NO); neither is proven
deliverable. The script's dashboard warning is a generic static message; the
independent MCP domain read above now supplies that evidence.

The measured failure is **Gmail anti-abuse rejection after provider acceptance**,
classified ContentRejected by Resend. Domain/IP reputation and content remain
possible contributors; current DNS verification cannot prove the historical
Authentication-Results headers. No raw Gmail headers or recipient receipt are
available. No evidence establishes a uniquely fixable application-template bug.
[Google documents multiple 550 5.7.1 causes](https://support.google.com/mail/answer/3726730);
[Resend distinguishes authentication from domain reputation](https://resend.com/guides/email/new-domain-emails-going-to-spam).
Do not interpret Transient as authorization for automatic probes or warmup.

## Actual six-service isolated rehearsal

Executed `scripts/ops/resend_stack_rehearsal.py` on the existing Docker host,
Compose v5.6.0, using exact locally installed runtime image IDs for API, Caddy,
guest-source API and guest-AI API. The source worker/scheduler use the same exact
image as the live source API. Caddy routing/headers were captured read-only from
the running proxy; its three upstream names were verified before execution.

Restored input: authenticated decrypt of the already verified off-host roundtrip
archive `mail-20261028T091302Z`; cipher checksum and restored database checksum
matched its manifest. This reuses #338's verified backup, not a newly refreshed
cutover backup. The plaintext exists only in private temporary storage and is
removed by the caller. No live volume was mounted into the drill.

Stages **original disabled → dummy Resend SMTP candidate → rollback disabled**:
all six real service processes recreated at every stage; exact images verified;
HTTPS requests through Caddy passed six website/auth/asset routes; source API
proxy responded; disabled AI failed closed through its upstream; legal signup
rejected; auth/organization rows matched restored input; SQLite integrity and
foreign keys passed. API sender construction matched each stage. Rollback's
resolved Compose JSON equalled original JSON. All stages and cleanup PASS.

Isolation: private randomized project, internal-only bridge, no published ports,
no external Docker networks, no credentials/env files/builds/pulls, read-only
roots, dropped capabilities, private tmpfs, private read-only input mounts.
Caddy uses local CA certificates with a private DNS alias and port 8443; no public
ACME or production TLS storage. Client certificate verification is disabled only
inside this private HTTPS probe. Caddy's file-capability-bearing binary needs
NET_BIND_SERVICE in its bounding set; no other service gets an added capability.

Boundaries: APP_ENV is development, external AI disabled, fixed safe env allowlist,
worker/scheduler use **independent empty tmpfs queues** so scheduled jobs cannot
be consumed or replay production work. Source database is synthetic empty data;
API account input is restored data. The production bot is inactive and is not
started. Unrelated private-preview/PostgreSQL/mail-sink services are not operated
on. This proves sanitized runtime/proxy lifecycle rollback, **not** byte-for-byte
ordered production overrides, real external AI/source fetching, public ACME,
host-port cutover, live-volume restoration or production deployment approval.

After cleanup, all previously running containers retained their IDs, image IDs
and StartedAt timestamps. Final independent read-only check: original production
API identity/image match backup manifest, email disabled/legal required true;
live SQLite integrity, foreign keys and all protected-table counts/hash parity
match; six public HTTPS routes return 200; no drill containers remain.

## Validation and remaining gates

Local regression: **77 passed** across auth verification/reset, RFC headers,
diagnostic/one-shot protection, prior Compose drill, new stack isolation/failure
contracts and recipient-free evidence extraction. One existing Starlette/httpx
deprecation warning. #338 exact head independently verified **7/7 CI success**,
including tests, Windows fixture and Docker build:
https://github.com/Ramzes2023/TenderLens-AI/actions/runs/40663398238
New PR CI is tracked separately; #338's results do not validate a later commit.

Remaining: separately owner-approved single no-link probe **no earlier than
2026-10-28T18:00:00Z**, retaining the existing atomic marker and no-repeat guard;
actual recipient Inbox/Spam confirmation; separately approved bona fide isolated
account verification/reset mail E2E; provider/recipient evidence for any rejection;
fresh encrypted backup and exact ordered production cutover/rollback validation
before any deployment; independent legal/public-registration approval. At the
time of this audit the send gate was still in the future. No send was attempted.

Provider event access is now available and is **no longer a blocker**. Historical
SMTP diagnostics are recovered, but real inbox delivery and the precise relative
role of domain/IP/content reputation remain unresolved. No production mail enable
or public-registration release is justified by green CI or this offline drill.
