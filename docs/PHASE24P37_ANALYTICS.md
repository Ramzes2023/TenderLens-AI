# 24P.3.7 observed historical aggregates

**COMPLETE for the supported, independently verified offline service checkpoint
(2026-10-11).** This does not complete retention, secure API or UI acceptance.

Scope: deterministic offline H service and pure identity manifests. No analytics
HTTP route, dashboard wiring, UI change, source fetch, scoring call, job, migration
or production operation. P3.8/P4/P5/P6 are downstream, outside this checkpoint.

## Predecessor and actual contract audit

Independently ran the final P3.6 six-file selection via the guarded runner:
`p37-baseline-p36`: **216 passed**, exit 0, 30.55 seconds. The previous pasted exit
marker was not used as test evidence. Read the progress plan/P1 matrix/P2 status,
P3 enrichment, fit, retrieval and dates registers, actual schema/repository paging,
source enrichment validation, preview provenance, ten-group engine contract,
deadline grouping/replay and existing tests. No serious P3.6 prerequisite defect
was found. P3.5 retention/immutability limitations remain explicit; they do not
prevent computing an honestly described observed selected-storage sample.

The six existing labels are Discovered, Matched, High Fit, Active Sources,
Countries, Closing Soon. Their UI remains untouched, including its pending-data
presentation. Service-level verification does not make that UI an accepted consumer.

## Population origins and trust

* **D**: current server Discover response, with current authorized company/profile
  digest and actual snapshot provenance. Browser session counts are not H.
* **H**: persisted authorized organization/company discovery search events. This
  service aggregates only H. An event is a company search observation, not a live
  feed, world-wide universe, sync, procurement publication or first discovery.
* **R**: account/organization/company-private durable scoring run, frozen profile,
  snapshot, candidate ordinal and public revision. R's own retrieval limits and
  fenced calculation semantics remain intact. R is never joined to H/D by identity.

`load_history` has no caller cursor, state, event-ID list or population-token
argument. It invokes `page_discovery_history` in batches 1..20 until exhaustion,
using its original maximum-ID/as-of fence, descending timestamp/ID keyset and UTC
search interval `[start,end)`. Every batch rechecks membership and company scope;
permissions/storage failures propagate as errors, never an empty population. No
implicit 50/100-event cap is used. The 123-event fixture reads all identities.

A second bounded pass over the same fence compares complete event bodies and
observation metadata, followed by a final count/access check. Concurrent backdated
inserts above the fence are excluded. Deleted events and changed/deleted snapshot
bodies at constant row count invalidate completeness, including bodies already read
on the first pass. `storage_changed_event_ids` identifies this observed drift.
Retained first-read bytes remain evidence of what was actually read, with partial
coverage; they do not become a claim that missing storage was recovered.

This is not a long-running immutable database snapshot. Changes after verification,
or a change reverted between the two reads, cannot be proved absent. No retention
register/row immutability, lost-event recovery or lifetime coverage was added.
Noncanonical imported database timestamps and PostgreSQL runtime acceptance retain
P3.5's limitations. These limitations never produce a lifetime/all-market number.

`HistoryPopulation` and scope labels are internal server values, not credentials.
They check type, origin H, fenced unique IDs, aware time, sample interval and scope
integrity; they cannot prove authorization of an arbitrary in-process constructor.
P3.8 MUST construct them after actual authorization using the loader, never decode
them from browser JSON. Existing signed-cursor tests cover forgery/replay/revocation;
no new analytics GET or public population token exists here.

## Union and provenance algorithms

`aggregate_history` reads no clock, network, storage or scoring engine. Events sort
by normalized event timestamp descending, then integer event ID descending; the
first occurrence ordinal in the newest event supplies the retained record. Identity
is exactly documented source ID plus nonempty, unmodified external ID. No case
folding, source alias, tender-number/title matching or cross-source merge occurs.

Missing/invalid identities, repeated occurrences, duplicate event revisions and
conflicting duplicate bodies are counted separately. Differing duplicates inside
the newest event exclude that identity, with no fallback to an older revision.
Different historical revisions retain all bytes/event/ordinal provenance and expose
`revision_conflicts` plus field-level `revision_known_value_conflicts`; a known
value disagreement is not silently treated as a reliable average. Mixed source,
country/category evidence is retained in each original selected row.

Strict JSON parsing rejects nonfinite constants and duplicate object keys. Missing,
corrupt/non-object snapshots and count mismatches invalidate complete totals. Each
snapshot has an explicit 8 MiB analytics read bound: larger input is unavailable,
never truncated. Missing analysis/enrichment affects that capability's coverage,
not a fabricated zero score. Permission failures are never catch-and-zero paths.

Output includes analytics/fit/country/taxonomy/date/deadline versions, current digest,
scope, origin, selected event IDs/times/SHA256s, selected row ordinal, score sidecar,
stable population digest, query sample window, actual observed interval, retrieval
fence/time, one caller-supplied UTC deadline `as_of` and window. The SHA256 population
digest binds evidence; it is not a signed authorization token. Retrieval fence time
and deadline anchor have different purposes and remain separately named.

## Numerators, denominators and shared identities

Every `Metric` carries value or reason, observed numerator, denominator, exact
membership manifest, coverage, time field, source IDs and unit. Tender shares use
numerator/denominator only for positive denominators. Country/source cardinality
KPIs are explicitly different units, not tender percentages. KPI tender drilldowns
are separately returned because two countries can belong to one tender.

| Slot | Defined population computation |
| --- | --- |
| Discovered | Unique valid selected observed tender identities U. No lifetime total. |
| Matched | Eligible H historical preview score >=35; denominator eligible scored U. |
| High Fit | Eligible H historical preview score >=65; same denominator. |
| Active Sources | Distinct persisted sources successfully reached at least once in the selected H searches, including recorded successful empty results; denominator distinct attempted sources. Not current health or sources yielding matched U. |
| Countries | Distinct supported explicit tender-country memberships; U denominator and unresolved-country identities disclosed. |
| Closing Soon | Unique U with valid UTC deadline instant in `[as_of,as_of+7 elapsed days)`, U denominator and excluded evidence disclosed. Date-only local calendar membership is separately labeled/output. |

Incomplete history or failed/partially failed selected searches return null KPI
values with observed lower-bound numerators and explicit reasons. A wholly
unsupported country/deadline/fit capability is unavailable. A successful verified
empty U can have zero tender counts. Missing source observations are unavailable,
not zero active-source health. Breakdown values always retain their sample coverage.

Fit calls the EXACT `preliminary-fit-v1` classifier: Low `[0,35)`, Medium `[35,65)`,
High `[65,90]`, strict finite int/float scores, explicit preview stage and trusted
scope. Unknown reasons/counts remain separate. Current-profile classification is
also retained, and rejects stale digests. H relevance is labeled historical preview
at search time; missing legacy digests cannot become current fit. Full AI scores,
stop factors and probability of winning do not replace preview eligibility.

Country/category distributions deduplicate per tender membership, denominator U.
Overlap is total memberships minus distinct represented U; bars are non-additive.
Validation reuses exact P3.2 country evidence and versioned P3.3 taxonomy registry.
Unmapped/conflicting/unsupported raw evidence stays in rows and quality manifests.
No currency/source-country guess, CPV-to-NACE mapping or aggregate TED-to-lot
attribution exists. Industry is typed unavailable because no supported crosswalk
exists. Notice-level categories remain notice-level evidence.

Publication/source-release/source-update, search persistence and deadline series
are distinct. Instant date-distribution buckets use UTC; date-only buckets retain
source calendar precision. Release/update semantics never become true publication.
Search series disclose stored result counts, actual readable row occurrences, valid
identity occurrences, event IDs and per-day distinct identities. Cross-bucket
tender identities are non-additive. Missing days are unobserved, not zero-filled or
interpolated; there is no market-growth claim.

Closing Soon and heatmap reuse P3.6 `group_deadlines` and shared replay predicates
with ONE supplied `DeadlineWindow`. Date-only windows use the verified display IANA
local calendar, never an invented instant. Unknown/no-zone evidence remains unknown.
Instants remain selectable if the display bucket is unavailable. Every returned
cell has an exact identity manifest; pure replay tests assert the expected identities.

Top opportunities include only eligible historical previews, sorted score descending
then source/external identity ascending, with bounded display limit and unrestricted
eligible total. Every row binds event/ordinal/snapshot hash/original item. No source
fetch or current Discover search is used to imitate a historical drilldown.

## Ten-group metadata and observed source health

The ten groups exactly match existing `engine._completeness`: identity
(title/number/customer), price, submission deadline, contract term, delivery,
security, object/quantity, participant requirements, required documents, technical
requirements. Price/security zero is known because presence uses `is not None`.
This is metadata-analysis-field coverage; full-document completeness is separate
and unavailable here, irrespective of preview score.

Report known analyzed U separately from all U. Present groups / `(10 * known U)`
gives the known-analysis percentage; all-U denominator remains `10 * U`, but its
percentage is null if any analysis is missing/invalid. Per-group gaps and unknown
identities are separate. Country/category/publication/deadline enrichment coverage
has its own all-U denominator. Direct metadata versus analysis disagreements are
listed as `metadata_conflicts`. No monetary sum, FX conversion or incomplete-value
average is computed. Full analysis absence is never assigned scored zero.

Source health uses only persisted attempted/successful/failed lists and matching
saved detailed status observations. It returns attempted/success/failed/unknown
samples, event/time interval, recorded successful zero notice counts, per-sample
partial/total-search flags, recorded-duration sample count and missing-duration
count. Duration mean uses only valid recorded nonnegative integer milliseconds,
including known zero; no recorded durations means null plus
`no_recorded_durations`. No duration/count is derived from result length, parser
observation time, request time or configured adapter count. Unobserved sources
are labeled unobserved. Conflicting list/status evidence is disclosed. There is
no uptime, SLA, continuous-monitoring, live-connector-health or outage claim.

## Independent sample proofs

Five controlled schema-shaped records `(ted,a..e)` produce U=5, eligible=4,
bands 1/1/2, Matched=3, High Fit=2, reached sources=1, known countries=2.
UTC Closing Soon is exactly `{a}`, date-only local window exactly `{b}`;
`c` is the exact seven-day UTC end, `d` has ambiguous naive time, `e` is missing.
IT membership is `{a,b,c,e}`, FR is `{b}`; two CPV categories belong only to `a`.
Country/category overlap counts are each 1. Top order is d,c,b,a with exact ordinal
and snapshot proofs. All asserted sets are independently enumerated in the test.

Existing SAM.gov and AusTender source-shaped fixtures pass through actual parsers,
Discover serialization and service: U is precisely SAM `abc123def456` and AusTender
`8daeb3c8-8323-4fbd-86d1-0a7adbf18d63`; country US applies only to SAM, category
`austender-category/80100000` only to AusTender. Known country/category/publication/
deadline coverage is 1/1/2/1 over U=2. AusTender's unsupported local clock remains
ambiguous; AUD/source coverage does not manufacture its country. These are existing
offline source fixtures, not new live published captures.

Ten-group fixture: one known 10/10 analysis, one explicitly known empty 0/10
analysis and one absent analysis produce known U=2, all U=3, present=10,
known required=20, all required=30, known percentage 50%, all-U percentage null.
Separate zero-price/zero-security analysis is 2/10=20%, proving known zero presence.
123-event fixture asserts all exact IDs, 37 bounded batch calls (18 initial,
18 verification, 1 final), and exclusion of a concurrent backdated insert.

## Validation and downstream status

Final focused guarded command:

```powershell
python .cache/phase24p3/run_tests.py p37-final tests/test_analytics_service.py tests/test_analytics_dates.py tests/test_analytics_normalization.py tests/test_analytics_fit.py tests/test_company_history_paging.py tests/test_discovery_history_api_behavior.py tests/test_discovery_history_repository.py
```

Result: **241 passed**, exit 0, 26.19 seconds; no skips/deselections. This includes
60 new service tests. Earlier focused runs: 239 passed (before two snapshot body
deletion race tests), all exit 0; initial service run 45 passed, then 45 passed.
No failed test assertion was weakened. These counts overlap, not additive.

Broad initial `p37-broad`: **831 passed + 390 subtests**, exit 0, 180.69 seconds,
49 files, no skips/deselections. It preceded final bounded body verification,
policy/provenance/count refinements and two new race cases. Final `p37-broad-final`:
**833 passed + 390 subtests**, exit 0, **192.32 seconds**, 49 files, no
skips/deselections. The selection is exactly the P3.6 broad command in
PHASE24_PROGRESS.md plus `tests/test_analytics_service.py`, with run-name replaced
by `p37-broad-final`. This final broad run includes all final service changes.

Six existing JS suites passed, each exit 0: company, discovery, discovery_full_ai,
phase24r, premium, shortlist_ui. Existing portable Node v24.21.0 and
`.cache/phase24p33-completion/dashboard.html` were reused. No browser was run.
Python compileall and git diff whitespace checks passed; new untracked files were
also checked separately for trailing whitespace/conflict markers. Guarded Python
runner blocks external connects and dotenv opens.
One existing Starlette deprecation warning remains. No full-repository, live API,
PostgreSQL integration, real-browser or UI consumer acceptance is claimed.

P3.8 must implement authenticated serialization/replay, binding account/company,
digest/query/policies/population with signed or server-owned state, reauthorization
on every read, explicit public-field serialization and stored-digest drift checks.
A pure manifest does not enable the
current Discover UI to reproduce H. Consumers must preserve sample labels,
unavailability, overlap/unknowns, stage and date semantics. P3.3 remains PARTIAL;
P3.2 consumer end-to-end pending; P2 browser acceptance PENDING. Production/secrets
untouched; no network, installs, Docker, migrations, staging, commits or deployment.
