# VALYQON AI — public SaaS cutover sequence (26 October 2026)

**Status: launch NOT VERIFIED.** This is an operator runbook, not authorization to
change a production host, bypass registration consent, start the worker,
send Telegram/email, charge a card, or install anything on AWS.

## Current main / proven already

- The live `main` integrates authenticated web/Planner, audited team controls,
  real recommendations, internal reminder journal and a fail-closed production
  Compose API+Caddy+PostgreSQL option.
- Real published MikroTon notices have been observed through a fenced Worker,
  temporary storage, genuine guest and company-scoped HTTP search and Saved.
  This is genuine source evidence in a **temporary** database, not a running
  production subscriber alert pipeline.
- The private AWS preview and the public VPS are separate installations.
  A working localhost 18765/18865, private Ubuntu preview, source-test fixture
  or Docker-only CI cannot satisfy a public customer-release gate.

## Read-only operator inspection: no uploads

Use one **previously trusted** public VPS host/key and the real public hostname.
SSH's pinned known-host verification must already be configured; never run
`StrictHostKeyChecking=no` or blindly trust a changed fingerprint.

Run from the locally checked-out **reviewed release candidate** (not from an
unrelated Chechnya branch). Use the exact 40-character reviewed Git commit SHA:

```powershell
.\.venv\Scripts\python.exe -m scripts.valyqon_public_launch_doctor `
  --ssh-host <previously-trusted-public-vps-host> `
  --ssh-key <existing-local-private-key-path> `
  --hostname <reviewed-public-https-hostname> `
  --expected-sha <full-reviewed-production-commit>
```

The command verifies synthetic local Compose, read-only pinned SSH inventory
and independent public HTTPS landing+health. It writes **no** production data,
never uploads source or key material, and prints only approved diagnostics.

- `vps_ssh=BLOCKED_...`: repair local routing, existing key permissions or
  previously trusted host-key configuration; do **not** bypass SSH verification.
- `vps_exact_sha=BLOCKED`: do not deploy a random branch. Review and back up
  the target, create a rollback artifact, approve a *separate* change.
- `vps_api_caddy=BLOCKED`: inspect already-running services on the VPS; this
  command intentionally does not start them.
- `external_homepage=NOT_VERIFIED` with `edge_failure_class=login`:
  old login redirect still occupies root; replace it only through an approved
  staged release + rollback and independent external HTTPS proof.
- `external_health!=PASS`: database/scoring/cache or HTTPS availability is
  not yet accepted.
- Even `technical_staging_edge_pass=true` **does not approve commercial launch**.

## Hard commercial release gates (separate acceptance evidence)

1. Owner-approved legal seller details, privacy/terms/cookies and explicit
   consents; `VALYQON_LEGAL_REQUIRED=true` stays enforced, **never**
   substitute an invented `VALYQON_LEGAL_APPROVED`.
2. Supported billing provider, signed callbacks, legitimate subscriptions,
   cancellation/refund/expiry, proper tax receipts and protected paid details.
   Paid detail lock remains forced until actual entitlements pass.
3. Encrypted, access-controlled **off-repository** production DB backups and an
   operator-attested PostgreSQL 16 restoration on isolated storage.
4. Correct real DNS and operator-managed trusted certificate; inspect
   Caddy/headers from an independent external network and no public API,
   Worker, DB or Mailpit ports.
5. Original official notice → approved adapter → Worker → PostgreSQL →
   authorized search and saved tender → **consenting** customer-owned delivery
   → real outbound provider acknowledgement and controlled recipient receipt.
   No fake tenders, background bulk sends or accidental queued job replay.
6. Abuse/rate-limit checks, web registration and password-recovery delivery
   with real sender, secure sessions, admin/tenant isolation and incident
   contact, and AI disclosure if external models are enabled.
7. Health monitoring, alerting, rollback rehearsal, change record, manual
   owner cutover approval and **independent post-deploy tests**.

If any gate lacks evidence, commercial SaaS remains `BLOCKED`. A limited
read-only public landing may be staged separately, provided its real HTTPS
and legal disclosures are approved; it must not claim billing or working
customer delivery.

### Never shortcut the blockers

Do not copy production `.env`, SSH keys, backups or customer records into
GitHub/ChatGPT; do not expose private credentials in logs. Do not run
`docker compose down -v`, enable Worker profiles over an unknown queue,
restart a Bot token with an existing poller or turn off legal/paid gates.
