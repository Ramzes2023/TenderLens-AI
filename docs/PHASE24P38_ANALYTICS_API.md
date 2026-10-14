# Phase 24P.3.8 — secure read-only company analytics API

Status: **PARTIAL**. The authenticated, versioned H API is implemented and tested;
the repository still lacks a hard database execution/materialization budget.
No production, network, secrets, installations, migrations or UI changes.

## Baseline audit

Read the actual main router registration, session authentication (`touch`),
organization membership/roles, explicitly addressed company lookup, repository
scope checks, P3.5 HMAC signing/pagination, P3.4 fit policy, P3.6 dates/deadlines,
P3.7 load/aggregate service and their fixtures. Read PHASE24_PROGRESS.md,
PHASE24P35_RETRIEVAL.md, PHASE24P36_DATES.md and PHASE24P37_ANALYTICS.md.
The previous CODEX_EXIT marker was not accepted as test evidence.

Independent guarded baseline `p38-baseline`: **241 passed**, exit 0, 21.19s,
no skips/deselections. This reruns the seven-file final P3.7 focused selection.
No blocking P3.7 defect was found. P3.7 remains COMPLETE for its pure observed
sample service; it does not promise immutable database retention or an API.
The only service change adds an optional server-owned `frozenset` identity
selection before calculating row-dependent numerators and denominators.
Existing callers keep their original behavior and assertions.

## Exact endpoints

All paths start with
`/api/v1/organizations/{organization_id}/companies/{company_id}/analytics/v1`:

* `GET /history/aggregate`
* `GET /history/rows`
* `GET /history/replay` — requires a population token or row cursor.
* `GET /capabilities/D`
* `GET /capabilities/R`
* `GET /capabilities/P`

Registered additively in `app/api/main.py` through its existing router path.
Public models are in `app/api/analytics_schemas.py`; stored bodies are never
automatically dumped into this API. Aggregate/rows/replay deliberately share one
typed envelope, ensuring the same predicates and commitment on every read.
No existing Discover/history/scoring/Saved/PDF/UI API is replaced.

History query parameters:

| Parameter | Meaning |
| --- | --- |
| `timezone_name` | Required display IANA name; no machine timezone fallback. Missing is 422; absent zone data is explicit `timezone_available=false`. |
| `start`, `end` | Optional aware ISO instants, normalized UTC, `[start,end)` over persisted `search_created_at`, retaining P3.5 second-resolution bounds. |
| `source` | Exact supported server source ID. |
| `country` | Exact uppercase country membership; no adapter/currency inference. |
| `category` | `scheme/code`, e.g. `cpv-2008/45000000`; notice evidence stays notice evidence. |
| `fit_band` | Historical `low`, `medium`, `high`, or `unknown`. |
| `date_semantics`, `date_day` | Paired exact semantic/day predicate. `published_at`, `source_publication`, `release_date`, `source_update`, `deadline`; instant buckets are UTC, calendar buckets retain source precision. |
| `deadline` | `instant_closing_soon` or separately labeled `local_date_closing_soon`. |
| `deadline_days` | 1..366 elapsed days/calendar days, default 7, over one server UTC AsOf. |
| `page_size` | 1..100, default 20. |
| `order` | `identity` or `top`; top contains eligible historical previews only, score descending then exact identity ascending. |
| `kpi` | Exact six KPI names; selects their tender drilldown rows from the filtered aggregate. Cardinality KPI units remain source/country, not tender counts. |
| `population_token`, `cursor` | Supply one signed token, repeating the exact query. Population token starts at row 0; cursor resumes a fixed offset. |

Unsupported/repeated query keys are 422, including client `as_of`, `policy`,
`ids` and population IDs. No unsigned client population is accepted.

Example request:

```http
GET /api/v1/organizations/7/companies/33/analytics/v1/history/aggregate?timezone_name=Europe%2FRome&page_size=20&country=FR
```

Illustrative excerpt for the documented controlled fixture, not customer data:

```json
{
  "population": {
    "version": "company-analytics-v1",
    "origin": "H",
    "organization_id": 7,
    "company_id": 33,
    "time_field": "search_created_at",
    "profile_trust_mode": "historical_preview_at_search_time",
    "union_count": 5,
    "filtered_count": 1,
    "unknown_fit_count": 0,
    "lifetime_total": null
  },
  "kpis": {
    "Matched": {
      "value": 1, "numerator": 1, "denominator": 1,
      "identities": [["ted", "b"]],
      "coverage": "complete_observed_storage", "reason": null,
      "time_field": "discovery_search_event", "unit": "unique_tender_identity"
    }
  },
  "total": 1,
  "next_cursor": null
}
```

The full population additionally includes its SHA256 ID, selected event/run IDs,
watermark, retrieval UTC AsOf, deadline UTC AsOf, start/end/interval, current digest,
supported analytics/preview-engine/fit/date-parser/taxonomy/country/deadline
versions, timezone availability, window, normalized filters, coverage/source
coverage, unknown/exclusion counts and capability reasons. The envelope includes
bounded distributions with membership manifests, deadline buckets, search-day
identities, ten-group completeness counts, observed source counters, row total,
population token and next cursor. Historical rows include stable source/external
and hashed row IDs, event/ordinal/snapshot hash, historical band/eligible score,
and current band/reason. Arbitrary tender bodies, titles, URLs, analysis fields,
raw malformed scores, connector details, raw provenance extras and error payloads
are intentionally absent from this initial public allowlist.

Capability response example:

```json
{
  "version": "company-analytics-v1",
  "organization_id": 7,
  "company_id": 33,
  "origin": "D",
  "capability": {
    "state": "unavailable",
    "reason": "no_authorized_immutable_current_discover_snapshot"
  }
}
```

D cannot be reconstructed from a new Discover POST or relabeled H. R is unavailable
for aggregation; its existing account-private run/revision APIs stay independent.
P lacks an explicit immutable company/profile/document binding and is unavailable
here. No tender-identity join mixes D/H/R/P. Full AI, stop factors and probability
of winning never replace preview relevance. Fit remains Low `[0,35)`, Medium
`[35,65)`, High `[65,90]`; missing/invalid/stale current digests remain unknown.
Original company profiles are never changed by analytics.

## Authorization and cursor threat model

Every valid request checks current session with `touch=False`, then organization
membership in owner/admin/member/viewer roles, then the explicitly addressed
company BEFORE history storage/signature processing. A shared API key alone is
not a session identity. Each repository batch also reauthorizes. Before returning
H data, current session/membership/company/profile are checked again. Explicit
inactive company reads remain authorized; activating another company does not
silently replace the addressed scope. Moving a token to another company is 422;
revoked membership is 403 before history access; inaccessible organization is 403;
missing company within an authorized organization is 404.

Existing app-approved `seal`/`unseal` HMAC-SHA256 abstraction and the existing
in-memory application signing key are reused. No secret is read or introduced.
The signed binding includes API and all policy/engine/parser/taxonomy versions,
account/org/company, normalized interval, timezone/window, predicates, page size
and ordering. Signed state includes profile digest, original watermark/retrieval
AsOf/count, one deadline AsOf, entire-event fingerprint, population ID, offset and
one-hour expiry. Tokens contain no snapshot body, error text or credentials.
Fingerprint covers ALL event fields, including saved source observations, not
only snapshot JSON. Output ID binds that fingerprint plus the complete query.
Raw identities must pass a bounded identifier allowlist; key-containing identities
fail closed. There is no cache and no server-owned replay snapshot to leak.

Initial load performs P3.7 complete traversal plus body verification/count check.
Replay injects only the signed original fence into the same loader. After
calculation, another complete same-fence load compares every event byte before
the final access check. A deleted/modified event, constant-count source metadata
change, moved timestamp, profile change or observed race returns 409. A later
backdated insert above the watermark is excluded. Returned logical populations
are immutable signed commitments; stored rows are not made immutable. A mutation
after final verification is detected on the next replay. Deleted bytes cannot be
recovered; tokens preserve identity, not retention.

## Bounds and honest availability

* Maximum 500 selected events, 5,000 persisted row occurrences/union rows, 8 MiB per
  snapshot, 16 MiB selected event bytes, 2 MiB serialized envelope, pages 1..100.
* At most 51 bounded repository batches per load (two passes plus final check),
  at most 102 per API read because of the final independent verification load.
  No per-event detail queries and no 50/100-event truncation.
* Cooperative 10-second read/calculation budget checked between reads and before
  final verification. Limit excess is 503 with a narrow-interval instruction.
* 401 authentication; 403 forbidden; 404 absent authorized company; 422 invalid,
  tampered, expired, differently bound controls/tokens; 409 changed commitment;
  503 unavailable/corrupt/missing storage or exceeded budget. Storage errors never
  become successful zero aggregates. Responses use `Cache-Control: no-store`.
* Snapshot corruption/missing bodies are 503; invalid identity/source observations,
  duplicate conflicts and failed sources retain P3.7 partial coverage/null totals
  with observed numerators and exclusion reasons. Successful empty storage can
  produce Discovered=0; absent source evidence stays unavailable.
* Source observations/Active Sources describe the selected SEARCH EVENTS, even
  under row country/category/fit filters. Row metrics/distributions describe the
  exact filtered unique tender population. KPI drilldown separately enumerates
  represented tenders; source/country cardinalities are never labeled tender totals.

### Remaining acceptance blocker

The existing P3.5 repository performs `COUNT(*)` and materializes selected full
snapshot strings before the API wrapper can check their byte sizes; the cooperative
timer cannot interrupt one running database statement or synchronous computation.
The implemented batch/event/retained-data/response limits are tested, but are NOT
proof of a hard DB wall-time or peak-memory bound against arbitrarily oversized
persisted rows or very large underlying histories. Claiming the entire P3.8 cost
acceptance COMPLETE would be false. P3.9 should evaluate a portable preflight/body
read limit, query-plan/index evidence and a database cancellation/statement budget,
without a speculative warehouse or destructive snapshot rewrite. PostgreSQL
runtime and real browser/consumer acceptance have not been run offline.

## Test evidence

Runner: `.cache/phase24p3/run_tests.py`, which blocks external socket connects and
dotenv opens. Test DB fixtures only; no preexisting `.tmp-phase24*` folder touched.

Initial API run found a new public-schema defect (source/country cardinality
manifests contain strings rather than tender tuples), fixed in the schema. A new
duplicate fixture initially constructed two independently timestamped bodies;
fixed to repeat the SAME saved object, preserving P3.7's conflict assertion.
No existing assertion was weakened. Initial failed runs are not acceptance evidence.

Measured validation (overlapping selections; all listed here exit 0):

* `p38-acceptance-focused`: **290 passed**, 139.51s, eight files. Exact command
  is in PHASE24_PROGRESS.md; includes all 241 baseline/service/retrieval cases
  and the then-current 49 API cases.
* `p38-acceptance-broad`: **882 passed + 390 subtests**, 543.45s, 50 files;
  the P3.6 48-file selection plus service and API. It predates final path/storage
  guards; no skips/deselections.
* `p38-final-api`: **49 passed**, 363.81s, includes final path/storage guards,
  no skips/deselections.
* `p38-storage-final`: **2 passed / 47 deselected**, 9.64s.
* `p38-id-final`: **9 passed / 40 deselected**, 33.60s.
* `p38-budget-final`: **3 passed / 47 deselected**, 6.66s: exact row/KPI/replay,
  limits and a new case expiring inside the final DB read. It follows the final
  narrow post-read/post-authorization deadline checks. The file now contains
  50 cases; the preceding complete API run covers 49, the added case passes here.

The final narrow guard detects budget excess after a statement returns, including
the last read; it does not cancel that statement. The hard-budget blocker remains.
One existing Starlette deprecation warning. compileall and diff-check passed;
untracked new files additionally passed whitespace/conflict checks. No whole-repo,
live API, PostgreSQL or visual acceptance is claimed.

Final API command:

```powershell
python .cache/phase24p3/run_tests.py p38-final-api tests/test_analytics_api.py
python .cache/phase24p3/run_tests.py p38-budget-final tests/test_analytics_api.py -k "budget_expiration or duplicate_conflicts or known_kpis"
```

Six JS suites passed, each exit 0: company, discovery, discovery_full_ai, phase24r,
premium, shortlist_ui, using existing portable Node v24.21.0 and
`.cache/phase24p33-completion/dashboard.html`. No browser was invoked.

P24.2 browser acceptance remains PENDING; published TED/CPV P3.3 remains PARTIAL;
unpublished eForms SDK fixtures are not customer data. P3.2/P3.6 limitations remain.
Charts/UI are later P24.4+, and P24.4/P24.5/P24.6 were not started.
PRODUCTION_TOUCHED=False.

## P3.9 compatibility continuation

The P3.9 independent baseline reran all 50 API cases plus service/retrieval:
118 passed, no skips/deselections, exit 0. P3.8 remains PARTIAL. The new opt-in
SQLite pre-body size preflight, read-only connection and SQL progress cancellation
address the materialization/SQL subset of the blocker above; they do not prove
hard whole-request memory/time bounds. Bounded analytics on unverified PostgreSQL
now returns 503; original PostgreSQL repository calls remain unchanged.
See [PHASE24P39_COMPATIBILITY.md](PHASE24P39_COMPATIBILITY.md) for migration
decision, tested compatibility, final evidence and remaining rollout gates.
