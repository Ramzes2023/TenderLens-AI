# RU-03 integration delivery

Base: `87e18cf8548e347c49e014cec2db4d8409032da5`.

## Activation

The source is absent from the catalog by default. Existing `eis` configuration,
44-FZ adapter, Telegram loop and scoring calculations remain unchanged.

Set `EIS_223_ENABLED=true` and configure either:

- `EIS_223_RSS_URLS`: semicolon-separated official HTTPS extended RSS URLs
  containing `fz223=on` and no `fz44`; or
- `EIS_223_PROFILE_FEEDS_ENABLED=true`: opt in to profile-term upstream searches.

Both 223 flags default to false. URLs alone do not activate the source.
The existing request timeout and verified EIS CA bundle are reused. Static-only
configuration does not send profile terms upstream. Snapshot filtering is local.

Shared connector ingestion requires static 223 URLs and explicit `eis_223`
enqueue through the existing ConnectorSyncService. Only `zakupki.gov.ru` is
allowed for this connector; the existing SSRF protections and five-request
budget apply. Temporary transport errors retain retryability.

Scoring requires explicit `sources=['eis_223']` and a configured catalog passed
as `ScoringRunService(jobs, catalog=catalog)`. Existing service construction
without a catalog continues rejecting 223 selection. Actual composition lives in
`app/api/runtime.py::build_runtime`: ScoringRunService is created before
runtime.source_catalog, without passing that catalog. This file is outside the
closeout allowlist. No lifecycle or route workaround was introduced and no
runtime file was modified. The minimal future authorized fix is to supply the
same catalog after successful catalog construction, failing closed if absent.
Stored snapshots retain the existing base TenderNotice scoring
contract. Algorithms, weights and thresholds are unchanged.

## Metadata and history

Original subclass notice JSON retains feed URL, source URL, GUID, description,
requested law, result-label observed law and independent verification (unknown).
The existing RU signal extractor adds evidence strings, offsets, field names,
law mentions, OKPD2 and KTRU indicators. Text mentions are not legal verification.
Reads and scoring retain base TenderNotice compatibility without rewriting the
original public notice JSON.

Additive migration 14 (`source_observations`) creates one history table and index
in the existing database. No existing migration checksum or schema is changed.
OpportunityRepository.initialize initializes this domain; normal full schema
migration also includes it. No migration was executed during this delivery.
An operator must apply the existing migration workflow before ingestion into
an existing database. No second database or independent migration engine exists.

History writes share the opportunity upsert transaction. Each unique content
revision is stored once per source/external ID; repeated observations update
opportunity last_seen, and replays do not create duplicate history events.
This is content-revision history, not a count of every poll: a return to an
already observed revision does not create another event. Original JSON and
connector provenance are retained per revision. Comparator evidence supports
normalized title/buyer, price/currency and ISO deadlines. Date-only values are
compared at date precision; timezone-free local date-times remain unobserved.
Unsupported fields and missing values do not prove removals. Different external
IDs produce separate first observations; no speculative identity linkage occurs.
RSS 223 currently clears unverified business price/deadline fields, so actual
price/deadline events require a future evidence-backed adapter enhancement.

## Validation and remaining work

`tests/test_ru03_integration.py` covers synthetic RSS, catalog activation,
profile queries and CA propagation, bounded ingestion, real temporary SQLite,
snapshot discovery, scoring worker compatibility, repeat/change/replay history,
source identity, malformed XML/items, host rejection and request budgets.
Existing transport/scoring tests were updated for the explicit activation contract.
These tests do not demonstrate live EIS availability or field completeness.

Pytest was not run, as required. Run the relevant suites on the independent
Windows host runner, including test_source_catalog.py, test_connector_workers.py,
test_eis_223_rss.py, test_eis_223_persistence_contract.py,
test_eis_223_scoring_contract.py, test_ru03_integration.py,
test_ru03_scoring_runtime.py,
test_ru_notice_changes.py, test_ru_procurement_signals.py and
 test_scoring_workers.py. Existing Telegram regression suites should also run.

Live QA still needs official 223 RSS/filter behavior, TLS verification with the
operator CA bundle, timeout/status behavior, actual notice identity stability
and metadata evidence. No network, EIS, Docker, PostgreSQL, deployment,
production migration, customer data change or commit was performed.

Delivery status: A COMPLETE; B PARTIAL (explicit service integration exists,
application composition outside the allowed areas remains unwired);
C COMPLETE; D COMPLETE within content-revision semantics; E PARTIAL
(test code added, independent host execution and results pending).

## Closeout coverage and limitations

The new runtime suite exercises the real FastAPI route and existing queue worker
with a constructor-configured service: default ted, unchanged eis selection,
explicit 223 activation, replay identity, invalid input and customer/company
isolation. A runtime catalog alone cannot activate an unconfigured service.
These tests do not claim that production build_runtime is wired.

The integration suite now includes customer-scoped connector rejection before
fetch and synthetic SQLite upgrade from migration 13 to 14, repeat migration,
old ledger/data preservation and foreign-key integrity. Migration statements in
these tests target only the host runner's temporary fixture database.
Migration 14 contains only additive CREATE TABLE/INDEX IF NOT EXISTS statements;
existing opportunities are not automatically backfilled into observation history.
Disabled-by-default mode requires no new secrets.

Closeout remains partial: runtime composition is outside the allowed scope and
the additional tests await independent host execution. The prior 294 passing
tests did not explicitly include test_ru03_integration.py. Pytest was not run.
git diff --check passed; syntax checking could not run because python was not
available on PATH in the sandbox. Live QA remains outstanding as listed above.
