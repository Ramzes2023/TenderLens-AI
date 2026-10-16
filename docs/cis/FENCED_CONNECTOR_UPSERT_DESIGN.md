# Lease-fenced connector notice persistence — review design

This change is a **stacked review** on the Armenia/Tajikistan integration branch, and is not activated in production.

## Original defect

`ConnectorSyncHandler` wrote each notice through `OpportunityRepository.upsert()`, opening a separate DB connection/transaction unrelated to `JobRepository.fenced_write()`. After lease expiration and a new worker claim, the old handler could still update `source_opportunities` before its final `complete()` was rejected. Composite notice identity prevents duplicates, **not stale overwrites**.

## Bounded change

- Keep public `OpportunityRepository.upsert()` for operator/import paths with unchanged validation and transaction semantics.
- Share the same normalization, provenance validation and INSERT/UPDATE/observation SQL through a private helper accepting an already-active connection.
- Add `OpportunityRepository.upsert_fenced(notice, version, context.fenced_write)`: all connector writes are committed through the **same transaction and lease-token verification** handled by `JobRepository.fenced_write`. The method cannot fall back to an unfenced write.
- `ConnectorSyncHandler` now requires the scoped fencing callback; lease loss becomes a sanitized retryable execution failure. Invalid notice handling, request budgets and disabled source policy are unchanged.
- Protect original Russian `eis`/`eis_223` observation writes by running those SQL statements within that same transaction.

## Acceptance

- Existing `tests/test_connector_workers.py` cases: source identity, retries, idempotency, error redaction, PostgreSQL standalone upsert SQL compatibility.
- New real SQLite two-worker race: worker A pauses in source fetch, its lease expires, worker B reclaims and stores a newer normalized notice, then A resumes. The old worker must not overwrite B.
- New real SQLite rollback: lease clock crosses expiry during the already-started notice write, which must roll back the INSERT.

CI must pass. If tests fail, do not merge. No new network/AI/production dependencies.

## Not claimed

Each notice remains its own fenced transaction, **not** an atomic whole-sync batch, and upstream fetches may be repeated. A handler can continue CPU/HTTP work until it cooperatively checks its lease. PostgreSQL multi-process parity, operational load and crash/restart testing remain necessary before automatic production activation. This fix does **not** enable Armenia or Tajikistan and does not make unrelated unverified CIS sources operational.
