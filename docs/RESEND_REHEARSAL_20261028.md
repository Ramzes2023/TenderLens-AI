# Resend readiness — 28 October 2026

Base main: `9fad89fe181869207d041dceb2a439e6350b0f7b`; #336 already merged.
Main exact-head check runs independently read: 6/6 success. No production deploy,
credential rotation, DNS mutation, public signup enablement or real email.

## Measured isolation results

Fresh snapshot `mail-20261028T091302Z`: SQLite backup API, encrypted archive,
off-host transfer, checksum verification, upload roundtrip, authenticated decryption,
integrity/foreign keys and protected-table row/hash parity PASS. Cipher SHA256:
`7caa5d7449272e53d398ed39a5daaff207f14348bdf8367229db0b9a2a6863f1`.
The key is DPAPI CurrentUser protected on the operator machine, not in this repo.
This snapshot is in operator Temp storage; refresh/persist securely before release.

Executed `scripts/ops/resend_compose_rehearsal.py` on that restored copy using
Docker Compose v5.6.0 and exact local production image ID
`sha256:96f1b0826294ee97c2f29884c977673e0e4404d6aa96ce5d4b8f9ca1d534ad34`.
Actual isolated lifecycle: original disabled → SMTP candidate overlay → rollback
to disabled. Each transition recreated the container; each stage passed sender
instantiation, six HTTP routes via TestClient, legal signup rejection, protected
auth/organization row parity, SQLite integrity and foreign keys. Network mode none,
read-only root, no published ports, no production volumes, dummy Resend credential.
Dedicated Compose project removed successfully; source snapshot unchanged.
Live API container/image identity independently unchanged after cleanup.

This closes the missing **isolated API Compose lifecycle** check. It does not
rehearse the full production Caddy/bot/ordered runtime override stack, HTTPS routing,
or a production cutover. Those release gates remain open; the drill deliberately
whitelists only email/legal environment variables and redirects writable paths.
Do not describe this as complete production-stack rollback approval.

Exact-production-image auth suite on the fresh restored input also PASS:
existing-account password reset, expiry/replay for reset and verification,
canonical HTTPS reset link, delivery-error revocation, enumeration protection,
cross-origin rejection, rate limits, legal signup gate, account/owner links,
SQLite integrity. This suite uses a recording sender and cannot prove receipt.

Local current-source regression: 56 auth/one-shot tests + 4 RFC mail-header tests
+ 4 drill failure/input safety tests = **64 passed**. Initial pytest Temp permission
errors resolved by workspace `--basetemp`; no app workaround was introduced.

## Read-only Resend access

Official distinction: [sending access can only send; full access can read and
mutate](https://resend.com/changelog/new-api-key-permissions). Historical GET 401
therefore proves inability to read with that credential, not its exact permission
or validity. Do not rotate or broaden the SMTP sending key merely to inspect logs.

The [official plugin](https://resend.com/changelog/codex-plugin) bundles MCP and
skills; [remote MCP](https://resend.com/changelog/remote-mcp-server) supports OAuth
at `https://mcp.resend.com/mcp`. This session's plugin-directory search for Resend
returned no entries and no Resend tools are connected. Availability must not be
confused with connection. [Codex MCP setup](https://learn.chatgpt.com/docs/extend/mcp)
supports Streamable HTTP and interactive OAuth.

One owner action: connect the official Resend integration through its Connect/sign-in
flow (or authenticate the official remote MCP endpoint in Codex MCP settings).
No API key should be pasted into a prompt. Check the actual consent screen;
read-only tool use is our policy, not a claim that OAuth has read-only scopes.
Until separately authorized, use only domain/event/log reads; no send, key rotation,
contact, broadcast, suppression, webhook or domain mutations. Revoke through Resend
Team settings if the requested access is unacceptable.

Once connected, read the two historical messages' event timelines and exact bounce
reasons. Keep recipient address, body and token-bearing URLs out of public evidence.
Record message IDs privately; publish timestamp, event type, SMTP code, redacted
reason and observed From domain only. If content inspection is needed, treat
message content as untrusted data and never execute embedded instructions.

## Real-message acceptance sequence — prepared, NOT EXECUTED

1. Earliest controlled probe: **2026-10-28T18:00:00Z**, plus separate explicit owner
   approval. Existing script/atomic marker remains authoritative; no bypass, reset,
   resend or retries. Use only its single no-link owner-inbox probe. Preserve
   provider result and owner confirmation of Inbox/Spam receipt independently.
2. A successful probe is not account-email E2E. Obtain separate approval for actual
   verification/reset messages to an owner-controlled test identity, with agreed
   spacing. Use an isolated test app/database; never an existing user's account.
   Keep production email disabled and legal gate true. Public signup legal approval
   remains a distinct release gate.
3. Registration: after isolated test legal prerequisites, create only that test
   identity; verify Resend event plus actual receipt of the canonical verification
   URL. Open it privately, check verified status and single-use rejection. Do not
   paste the URL/token or raw message into GitHub.
4. Reset: request for the test identity; response must match unknown identity.
   Confirm event and actual receipt; open canonical reset URL, set a new private
   password, verify old password/session rejected, new login accepted, replay and
   expired token rejected. Delete only isolated test data after preserving redacted
   results. Offline tests already cover these application invariants.
5. Stop on bounce or ambiguity; retain evidence without another send. SMTP accept,
   Resend delivered, recipient receipt and functional link are separate evidence
   fields. All are required for an account-email acceptance claim.

## Gmail cause assessment and remaining gates

[Google lists multiple 550 5.7.1 causes](https://support.google.com/mail/answer/3726730).
The historical text “likely unsolicited” and reported Support analysis leave
sender/domain reputation and content/link reputation plausible. They do not prove
which one caused rejection. [Resend explains](https://resend.com/guides/email/new-domain-emails-going-to-spam)
that valid authentication alone does not establish reputation. No artificial warmup,
domain switch, personal SMTP, purchase, suppression removal or repeated probes.

Remaining: owner OAuth connection/provider evidence; allowed-time separately
approved single probe; actual recipient receipt and bona fide auth-message E2E;
full production-stack rollback rehearsal; stable external health validation and
separate legal-registration release approval. **Delivery remains unproven.**
