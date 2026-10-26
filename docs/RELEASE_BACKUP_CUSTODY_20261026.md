# Backup custody and public launch gates — 26 October 2026

## Verified scope and outstanding gates

PR #297 has offline CI evidence (Chromium, PostgreSQL 16 with restore, Mailpit,
analytics concurrency). This proves isolated behavior, NOT a production deploy.
Codex reported that the temporary public sslip.io host has trusted TLS, but
its root redirects to the old login screen. The reviewed candidate already
implements the VALYQON public homepage. This is a version/deployment mismatch
until an authorized operator proves exact running image SHA and root behavior.

## Backup custody — NEVER use the Git worktree

Do not transfer or save production-derived dumps, encrypted backups,
recovery keys, screenshots, or private customer logs into a Git checkout.
In particular, VALYQON-WEB-REVIEW/.release/evidence is not an approved
backup location. Same-host PostgreSQL pg_dump/pg_restore is not off-host
disaster recovery. Encrypted copies must remain in the already secured server
location until the owner separately authorizes an encrypted off-host store
and names a recovery custodian.

After separate approval, perform an isolated off-host restore using an
authorized transport and an independently stored encryption key. Prove
integrity, row-count reconciliation, recovery time and rollback procedure
without printing data, credentials, plaintext files, URLs with tokens or
private backup paths. The published manifest may contain only sanitized
SHA-256, DB engine version, timestamp, restore PASS/FAIL and schema count.

The repository excludes .release and backup filenames via .gitignore.
Running python -B scripts/check_release_artifacts.py refuses forced-add
backup or .release entries in the Git index without reading their contents.
This does not replace real permissions, encryption or history scanning.

## Public release preflight

1. Compare exact reviewed commit SHA with the image/version actually running
   at the public edge using a trusted operator channel.
2. Root / MUST be HTTP 200 current landing body with landing premium class,
   guestSearchForm and guestSearchResults. A branded login page or HTTP
   redirect must FAIL. /login is a separate expected authentication route.
3. Require trusted HTTPS, public DNS, security headers and truthful /health.
   Even complete edge PASS does not prove official tenders, subscribers
   or real notifications.
4. Require verified external SMTP recipient delivery, opted-in alert receipt,
   customer source-to-Worker-to-durable-DB-to-search-to-user evidence,
   merchant-signed entitlement, and rollback-tested PostgreSQL deployment.
5. Production Compose still points to a single-node SQLite volume, despite
   successful PostgreSQL in an isolated staging stack. Treat cutover as
   BLOCKED until explicit DB migration and off-host restore acceptance.

No merge, deployment, backups transfer, data mutation, payment or external
notifications are authorized by this document.
