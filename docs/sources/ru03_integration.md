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

Scoring requires explicit `sources=['eis_223']` and a configured catalog.
`app/api/runtime.py::build_runtime` now constructs ScoringRunService after
the catalog and passes the existing `runtime.source_catalog` instance.
No second catalog or scoring pipeline is created. Catalog failure preserves
standard scoring with `catalog=None` and rejects 223 selection. Default
selection remains `ted`; existing source ordering and 44-FZ behavior are unchanged.
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

## Final runtime integration

Base: `5f53570ec7cf65815d45de42d9f20dfc9b59764a`.
The narrow application runtime wiring blocker is resolved.

`tests/test_ru03_scoring_runtime.py` now runs the activation/isolation matrix
through both manual composition and real `build_runtime`. Runtime configuration
is synthetic; repositories, HTTP routes, queue and scoring handler remain real,
using only the host runner's temporary SQLite database. The catalog factory is
called once, and the scoring service receives the identical runtime catalog.
The existing 44-FZ discovery adapter also retains that catalog's source instance.

Coverage includes default-off, URLs without enablement, enablement without feeds,
static RSS activation, profile-feed activation, explicit source selection,
unchanged default ted and eis scoring, registry ordering, duplicate/limit
rejection, replay identity and company/organization isolation. A failed catalog
build additionally preserves standard scoring while rejecting eis_223.

Migration 14 was reviewed: only additive CREATE TABLE/INDEX IF NOT EXISTS;
no schema changes or migrations were applied to existing databases.
Pytest was not run in the Codex sandbox. Independent host execution remains
required; the previously reported 671 passed, 2 skipped is not a result for
these new changes. `git diff --check` passed. Changes remain uncommitted.
Live EIS verification remains outstanding; no live availability claim is made.

## RU-03 SQLite import compatibility repair

The reported Windows result (718 passed, 2 skipped, 1 failed) identified an
import allowlist mismatch: migration 14's domain is `source_observations`, but
its actual table is `source_notice_observations`. The importer now includes
that fixed table in source validation, destination emptiness checks and the
existing transactional transfer/count verification. Observation revisions are
preserved; no identity sequence or tenant mapping is changed.

Presence of the table requires the known migration 14 ledger entry (including
the existing domain/checksum validation); migration 14 also requires the table.
Source table/index DDL and complete `table_xinfo` are compared with an isolated
database generated by the existing migration machinery. This checks nullability,
defaults, primary keys, constraints and hidden columns, and rejects extra indexes
or triggers on this table. Exact canonical DDL is intentionally required;
hand-written equivalent schemas require explicit review. Arbitrary extra tables,
integrity failures, foreign-key failures and unsupported versions remain rejected.
Legacy sources without migration 14 and its table retain the existing contract.

`tests/test_ru03_import_contract.py` covers migrated/read-only sources, observation
history transfer, nonempty destination rejection, altered columns/types/constraints,
indexes/triggers, missing table/ledger, changed checksums, unrelated tables,
legacy formats and real SQLite integrity/FK violations. The offline transfer test
uses real SQLite row operations and substitutes only PostgreSQL sequence calls;
it does not claim PostgreSQL integration coverage. The existing actual scoring
worker parity regression continues to call the real import preflight.

No pytest execution occurred in the Codex sandbox. Host execution of the new
suite and scoring worker regressions is required before claiming a passing
result. No production or user database was opened or migrated. Runtime wiring
remains unchanged by this import repair. Existing legacy-table validation is
unchanged; the stricter complete-schema comparison is scoped to migration 14.
