# Phase 24 — Operator Reliability Audit and Initial Implementation

Date: 2026-10-15. This document records code that was inspected on main, not an assumption that deployments are running.

## 1. Alerting

Existing: opt-in, process-local observability metrics and JSON logs; request correlation IDs; bounded queue health including expired leases and failure codes; Telegram customer tender alerts; customer-facing Source Health view.

Missing before this branch: 24/7 operator alarm worker, persistent notification deduplication, cross-process HTTP 5xx error-rate aggregation, service scheduler/heartbeat and verified operator Telegram routing.

New initial checkpoint: app/observability/operator_alerts.py. Invoked with python -m app.observability.operator_alerts, default DRY_RUN. Aggregates failed jobs in the last 15 minutes, expired worker leases, missing/stale evidence from explicitly listed source IDs, and high/recently increasing HTTP 5xx from explicitly supplied local Caddy JSON access logs. When opt-in is enabled AND --send is supplied, can send Telegram operator notifications with one-hour local deduplication. Only fixed alert codes and generic messages are sent; no account IDs, document text, credentials or source URLs.

IMPORTANT: A stale source last_seen is not evidence that the source failed; there may simply have been no tenders. Without Caddy JSON logs, 5xx status is NOT_CONFIGURED, never a zero-error success. Without a host scheduler running this command and a confirmed operator Telegram recipient, this is NOT production 24/7 alerting.

Operator config (inject through a secure deployment secret manager; never commit values):
- PYTHON_DOTENV_DISABLED=1 must be set.
- DATABASE_URL is existing application config; prefer a read-only database identity.
- VALYQON_OPERATOR_EXPECTED_SOURCES is a comma-separated list of configured source IDs.
- VALYQON_OPERATOR_CADDY_LOG optionally names an absolute readable, locally stored Caddy JSON access-log file.
- VALYQON_OPERATOR_ALERTS_ENABLED=1, VALYQON_OPERATOR_TELEGRAM_BOT_TOKEN, VALYQON_OPERATOR_TELEGRAM_CHAT_ID, VALYQON_OPERATOR_ALERT_STATE_FILE (absolute path in a private persistent directory) and --send are ALL needed for live delivery.
- Run as exactly one supervised scheduler instance. Host must alert independently if checker stops or credentials/network delivery fail. Verify with a controlled failure injection before enabling an operational SLA.

## 2. Backups and disaster recovery

Existing: docs/PHASE24S1A_POSTGRESQL.md describes operator pg_dump and pg_restore commands and describes an independent restore requirement. An older production SQLite backup was integrity-checked historically. PR #17 proved real PostgreSQL migrations/queries/cleanup in a disposable DB but did NOT prove backup/archive restoration.

Missing: verified scheduled PostgreSQL archive-and-restore into an independent empty DB, protected encrypted offsite backups, real RPO/RTO measurements, clean-server restore drill, coordinated Qdrant/index/PDF backup and restoration. A passed database integrity check is not a proven restore.

Next independent acceptance PR: seed two synthetic tenants on disposable PostgreSQL 16, take a real pg_dump archive, independently restore with pg_restore --single-transaction --exit-on-error, compare migration fingerprints and tenant records, and prove cleanup. Then define daily encrypted offsite backups, a daily success check, monthly isolated restore tests and quarterly complete-system DR rehearsal before production. None is claimed to have run by this document.

## 3. Operator administration

Existing: Support Center operator ticket API guarded by VALYQON_SUPPORT_OPERATOR_EMAILS; read-only aggregate queue CLI; Source Health customer view. Phase 24 database audit says billing/subscriptions have no durable payment or subscription-write model in that revision.

Missing: privileged operator dashboard for users/organizations, subscription modifications, quota enforcement controls, connectors and dispute investigation. Existing support allowlist must NOT grant these capabilities. Build separate privileged operator identity, verified authentication, additional policy/authorization, audit records with reason and actor, CSRF enforcement, redacted sensitive data and rate limits. Start with read-only visibility. Manual subscription extensions must wait for a transactional, audited billing/entitlement model; no fake entitlement changes.

## Change boundaries

This branch does not modify main, AWS, production, customer databases, Russian PR #15/#16, or real payment systems. No new public endpoint is introduced. The operational alert checker is OPT-IN and needs CI validation and scheduler integration before being called production-ready.
