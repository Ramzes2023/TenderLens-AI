# TED real-source persistence and search acceptance

Scope: independently verify **TED / EU** through the existing VALYQON
ingestion worker and persisted snapshot catalog. This is complementary to
the anonymous source availability audit and does not replace the customer
API/authentication acceptance, PostgreSQL production readiness, or the
full source-list gate.

## Execution boundary

- Production AWS, existing local databases, users, tokens, account profiles,
  source implementations and runner configuration are not accessed or changed.
- The script uses an exclusively created temporary SQLite database, migrates
  only the necessary source tables, runs the production ConnectorSyncHandler,
  and deletes the disposable database on completion or failure.
- Normalized notice identity must match official TED publication-number
  and HTTPS detail route. The title must come from the source, not the
  fallback "TED notice <ID>" placeholder.
- Search uses the existing snapshot_catalog and SourceCatalog paths, not a
  separate implementation or a title match against in-memory HTTP results.
- Verify no false positive for an absent search term, no cross-source reads
  and that replaying a persisted notice updates rather than duplicates it.
- Live mode uses the existing TED strict-host / TLS-verified / public-IP
  transport, bounded via the connector worker FetchPolicy and client timeout.
  There are no credentials, proxy bypasses, redirects or external AI calls.
- Structural counts and PASS/FAIL stages only are printed; no tender titles,
  detail URLs, customer data or upstream exception text.
- The GitHub-hosted ubuntu-latest jobs are intentionally isolated from the
  privately owned VALYQON-RU-01 self-hosted runner. No unreviewed PR code
  may be scheduled on that runner.

## Commands

Offline synthetic worker/SQLite/search regression:

    python -m pytest -q tests/test_ci_ted_persisted_search.py

Explicit real public feed acceptance (returns nonzero on failure/zero results):

    python -B scripts/ci_ted_persisted_search.py --live

Without --live the script makes no source request and exits with NOT_RUN (2).
Never interpret a mocked fixture PASS as real tender availability.

## Required merge gates

1. Offline contracts green, entire repository CI green, live TED job green.
2. Live output must contain LIVE_VERIFIED, nonzero normalized/persisted/search
   counts, exact official identity, source isolation and idempotent upsert.
3. A separate **real PostgreSQL 16** integration / restore acceptance must pass
   before asserting production-database readiness.
4. Authenticated customer keyword search, tenancy isolation and actual live
   discovery must be verified before asserting a complete end-to-end SaaS
   user journey; this script is a persisted source snapshot search gate only.
5. Review parallel branches, shared changes, source registration, and operator
   approval before merge or any AWS/production deployment.

Failure types (NO_ACCEPTED_NOTICES, PERSISTENCE_COUNT_MISMATCH,
SEARCH_NOT_FOUND, etc.) are fail-closed and do not imply an upstream outage
without independent evidence.
