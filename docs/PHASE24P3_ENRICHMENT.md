# Phase 24P.3.1–3 foundation contract

Offline support register (2026-10-10). Evidence is the existing checked-in source
tests; no live source verification or new upstream field request was performed.
These are official-source-shaped offline fixtures, not a claim of a new live capture.

| Adapter / existing test | Country evidence | Classification evidence | Date provenance |
| --- | --- | --- | --- |
| SAM.gov / `test_sam_gov_source.py` | `placeOfPerformance.country.code/name`; explicit procurement location | None | `postedDate`, `responseDeadLine` / existing typo fallback |
| TED / `test_ted_source.py` | None; `place-of-performance` is preserved as region, never parsed as a country | None; no fixture-verified CPV response field; offline registry now verified below | `publication-date`, selected existing deadline fallback |
| UK FTS / `test_uk_fts_source.py` | None; `UKE1` delivery region is not country evidence; buyer address is excluded | None | release `date`, `tender.tenderPeriod.endDate` |
| AusTender / `test_austender_source.py` | None; state/city and AUD are excluded | `dataLayer.atmCategoryCode/atmCategoryTitle`; fixture `80100000`, Management advisory services | extracted detail Publish Date / raw RSS pubDate; decoded selected TimeZone CloseDateTime parameter or detail Close Date & Time, retaining display text |
| ZA / `test_za_etenders_source.py` | None; province is excluded | explicit `category`; fixture Services: General | raw `date_Published`, `closing_Date` |
| CanadaBuys / `test_canada_buys_source.py` | None; delivery/opportunity regions excluded | None | original publication/closing CSV cells |
| NZ GETS / `test_nz_gets_source.py` | None; Region excluded | None | raw pubDate, extracted description Close date |
| India CPPP / `test_india_cppp_source.py` | None | None | extracted Published Date / Bid Submission End Date cells |
| KZ / `test_kz_goszakup_source.py` | None | None | raw publish_date/end_date |
| EIS / `test_eis_business_metadata.py`, `test_source_framework.py` | None; region and RUB excluded | None | original publication XML text; extracted description deadline |

`TenderNotice.enrichment` and discovery enrichment are optional. Old notice JSON,
history and Saved snapshots decode with null enrichment and are never backfilled.
New parser output captures schema 1, adapter metadata revision, normalizer revision,
source/external identity and actual UTC parser observation time. Observation is not
publication, search persistence, first discovery or synchronization time. Re-reading
stored notice JSON preserves the original observation. Shared opportunity writes add
the existing connector version; live parser output has no connector-sync claim.
Connector scheduling, configured authentication, request fields, credentials, hosts,
authorization and routes are unchanged. No dashboard GET or rendering fetches a source.

Only selected public fields enter provenance; whole upstream bodies and credentials
are not copied. Existing identity, region, summary, value and dates are unchanged.
Date provenance retains exact scalar/JSON values where available, and explicitly
labels extracted cell/description/detail text or already normalized caller fallback.
Dates are reported-unparsed or missing; this checkpoint supplies no new date parser,
timezone assumptions or deadline windows. Source notices cannot establish scoring
provenance; the contract says unavailable_in_source_notice. Existing metadata preview
and full-document scoring remain separate. Profile binding belongs to 24P.3.4.
UK FTS date provenance explicitly means release date; EIS updated fallback means
source update. The existing published_at field is preserved for compatibility, but
these provenance semantics must not silently become a true-publication time series.

Country policy `iso3166-location-v1`: explicit ISO alpha-2 whitelist (249 entries),
finite alpha-3/name aliases documented in normalization.py. Names outside that subset
stay unmapped; Congo/Korea/Virgin Islands stay ambiguous. No substring, NUTS, buyer,
currency, language, source coverage or title inference. Code/name evidence in a
single location must agree; disagreement clears canonical codes. Distinct locations
permit multiple countries. Codes are sorted/deduplicated and evidence retains each
raw value/path/location. Partial records expose known countries and unknown evidence.
Multi-country membership is non-additive: future distribution totals may exceed unique
tender count; no aggregates, KPI or Discover country filtering are implemented here.

The original taxonomy policy `observed-source-categories-v1` supports ONLY the two observed source
category pairs in the register. These IDs deliberately do not claim UNSPSC or CPV
versions. Matching labels must agree, duplicate memberships count once, and all raw
entries/labels/roles remain available. Role is reported, not an invented primary or
secondary designation. Unverified codes and code systems stay unsupported. No text,
source-only or scoring-category mapping exists. Industry and hierarchy remain empty
with unmapped industry status.

24P.3.3 continuation (2026-10-11): the locally supplied official TED HTML now
supports a packaged CPV 2008 label registry; the full checkpoint remains PARTIAL.
See the reference audit below. No verified TED source classification field was
found in existing fixtures, so no new field is requested or guessed.

The optional schema is version-checked, bounded to 64 KiB, identity-bound and validates
canonical country/category output by recomputing it from retained evidence. This is
internal consistency validation, not cryptographic authentication of browser-submitted
Saved metadata; the existing Saved API accepts client metadata and authorization is
unchanged. Future analytics must use authorized server-observed discovery/history
populations, not silently promote arbitrary client metadata to source truth.

## 24P.3.3 offline CPV reference audit - PARTIAL / blocked acceptance

Reference URL: https://docs.ted.europa.eu/eforms/latest/reference/code-lists/cpv.html
Local file: `.cache/phase24p3/official_ted_cpv_2008.html` (1,164,820 bytes).
SHA256: `e4134a747acbc18d99a778412002caf55212baf8cbc1c695a03fab00edecbbb9`.
The supplied bytes were hashed and parsed as inert data; scripts/links were never
executed/followed. SHA256 binds these local bytes, not the publisher's authenticity.
`python scripts/verify_cpv_reference.py LOCAL_REFERENCE.html` verifies the digest,
metadata and every label against the packaged `app/analytics/cpv_2008.json`.

The page explicitly states Version 2008 and Structure hierarchical. Its code table
has 9,454 unique eight-digit English code/label pairs, from `03000000` through
`98910000`; every pair is preserved, including leading zeros. Coverage means all
rows of this supplied table, not supplementary vocabulary, all language labels,
obsolete-code history, or a claim of independently verified legal completeness.
The eForms documentation version/latest URL is not the taxonomy version.

`cpv-2008` is the explicit taxonomy ID. `validate_cpv` accepts only exact ASCII
8-digit strings present in the registry. Well-formed absent codes are unknown,
never asserted obsolete. Wrong types, whitespace, Unicode digits and 9-digit
strings are invalid. Hyphenated check-digit notation is explicitly unsupported:
this reference supplies neither digits nor their algorithm, so digits are never
stripped, computed or called valid/invalid. `cpv_parent` reports unsupported for
known codes: the HTML declares hierarchy but contains no parent edges or an
ordering/prefix derivation rule. Prefix truncation is not authoritative evidence.
No root/leaf classification or hierarchy filter is asserted.

Classification policy `source-classifications-cpv2008-v2` verifies CPV labels,
retains original code/label/path/role and each evidence entry, deduplicates canonical
memberships, keeps unknown/invalid/conflicting entries, and does not mutate input.
A conflicting label contributes no membership. Distinct verified evidence can
still contribute the same code while the record is partial. Unversioned `CPV`
remains unsupported; no implicit version alias. AusTender and ZA retain independent
IDs and registries; numeric equality never converts them to CPV/UNSPSC. Industry
is still unmapped: no verified CPV-NACE crosswalk exists. Multi-code membership is
non-additive and future consumers must disclose denominators and count unique
tenders; no charts or filters from later checkpoints were started.

Legacy `observed-source-categories-v1` snapshots are validated under their original
policy without reinterpreting earlier unsupported CPV evidence. Unknown policy
versions fail validation. Old absent enrichment remains null. Discovery, history,
Saved, tenant/role/company scope and metadata-preview/full-AI contracts are retained.
CPV roundtrip/authorization tests use explicitly synthetic enrichment, not a claim
of source-field verification. Existing `test_ted_source.py` supplies no CPV field;
BT-262/BT-263 links on the reference do not establish TED Search API JSON names.
`TED_FIELDS` and parser extraction remain unchanged.

Precise completion blockers: authoritative parent edges or derivation evidence;
fixture-verified actual TED classification fields; obsolete-code history if obsolete
recognition is required; verified industry crosswalk and real chart/filter acceptance
(the latter belongs to later authorized checkpoints). Check-digit semantics remain
unsupported until an authoritative reference is supplied. 24P.3.3 is not COMPLETE.
24P.2 browser acceptance remains pending; 24P.3.4-24P.6 remain unstarted.

### Continuation verification

- SHA256, declared version/structure and full table equality: PASS (9,454 rows).
- CPV-focused final suite: 19 passed; enrichment/company/role/history/Saved suite:
  30 passed after the company-isolation assertions. Earlier combined UI/enrichment
  run: 72 passed. These counts overlap and must not be added.
- All six existing JavaScript suites: PASS using the already available local Node
  runtime and the dashboard HTML rendered by the existing Python UI test fixture.
- One stale Monitoring shell-asset version assertion was repaired to match the
  preserved 24P.2 version; 11 Monitoring UI checks passed.
- `compileall` of changed Python modules and `git diff --check`: PASS.
- The first broad attempt was interrupted after identifying a Windows test-runner
  spawn problem: the local `.cache` runner lacked an `if __name__ == '__main__'`
  guard and spawned PDF workers repeated pytest. The guard was repaired locally;
  application PDF code was unchanged. A guarded broad run then reported 1,835
  passed, 3 skipped, 36 deselected and 440 subtests passed, with one guard rejection
  from `RagConfigTests.test_semantic_defaults` attempting to create `.env`.
  No dotenv file was opened. A final permitted regression excludes that test as
  well as dotenv-named tests and the environment-example reader; result below.

All earlier uncommitted work is retained. No source calls, installation, migration,
production action, git staging/commit/push or changes to `.tmp-phase24*` directories.

The next full run exposed a pre-existing Windows timing flake in
`test_timeout_budget_includes_dns_and_fallback` (two 10 ms delays shared one
monotonic-clock tick). The test now models DNS and first-attempt elapsed time with
a controlled budget clock while preserving real AnyIO cancellation. No HTTP
application code changed. The entire HTTP/transport rerun passed: 424 passed,
2 existing raw-deflate checksum skips. A final full permitted run follows this fix.

Final permitted full offline regression (2026-10-11): **1,836 passed, 3 skipped,
37 deselected, 440 subtests passed**, one existing Starlette deprecation warning,
exit code 0. Command: `python .cache/phase24p3/run_tests.py cpv-regression-verified
tests -k "not dotenv and not public_environment_example_is_trackable_but_real_file_is_not
and not semantic_defaults"`. The 37 deselections are explicit exclusions of
dotenv-named tests plus the environment-example reader and synthetic dotenv writer;
they are not counted as passing. Skips: Windows symlink privilege unavailable (1),
raw deflate without checksum (2). External-connect and dotenv-open guards remained
active. All six JavaScript suites passed. Final `git diff --check`: PASS.
This is offline regression evidence, not live-source or real-browser acceptance.
24P.3.3 remains PARTIAL for the documented reference/source/hierarchy blockers.


## 24P.3.3 official Genericode / TED field-list completion audit ? 2026-10-11 ? PARTIAL

This section supersedes only the earlier unsupported-parent availability statement.
All prior uncommitted Phase 24P changes, the original label registry and snapshots
are retained. No 24P.3.4+ work or 24P.2 browser acceptance was performed.

### Pinned inert evidence and coverage

- Genericode URL: https://raw.githubusercontent.com/OP-TED/eForms-SDK/1.15.1/codelists/cpv.gc
  Supplied file: `.cache/phase24p33-completion/official_eforms_cpv.gc`.
  SHA256 `e8f48feedb63ce1583caa22825011afccd402973c28a885c2e81f89460fd6301`.
  XML metadata: Genericode 1.0 namespace, `cpv_2008_core`, taxonomy Version `2008`,
  canonical URI `http://publications.europa.eu/resource/dataset/cpv`, agency
  `Publications Office of the European Union`; repository tag is SDK `1.15.1`,
  not a new CPV taxonomy version. No DOCTYPE/entity declarations are accepted.
- Label HTML URL: https://docs.ted.europa.eu/eforms/latest/reference/code-lists/cpv.html
  SHA256 `e4134a747acbc18d99a778412002caf55212baf8cbc1c695a03fab00edecbbb9`.
  Original packaged `app/analytics/cpv_2008.json` SHA256
  `f0e00c73491a8a82142c07767de079f433217e636ae74c9b4874338e840b7ab3`.
- Search field-list URL: https://docs.ted.europa.eu/ODS/latest/reuse/field-list.html
  Supplied file: `.cache/phase24p33-completion/official_ted_search_fields.html`.
  SHA256 `79324dc627ee846f137e8cf4d069509784d51dcc7770f592dcd58096e261a419`.
  Page component `ODS`, data-version `1`, displayed version `1.0`; this is a
  documentation version, not proof of a v3 JSON response schema.
- Supplied `sources.txt` SHA256
  `9fc0a23ae0670c670ec81f60d67fa2929084a0cf50e35205ef9dc33034340a80`.
  Recorded source digests match supplied bytes. Local hashing binds bytes and
  does not independently authenticate the download; no URLs were fetched.
- Derived `app/analytics/cpv_2008_parents.json`, version
  `cpv-2008-explicit-parents-sdk1.15.1-v1`, SHA256
  `6523c610246141beadeb1461f23d22456a081417aaec15c0c724be4f14e557e8`.
- Derived documentation-row fixture `tests/fixtures/ted_classification_field_evidence.json`,
  SHA256 `1b2a4f20ba9b7f2f17e19a53baa460b8f60ab10982c3b620dc8fa5211193d85a`.
  This fixture is extracted documentation evidence, not a fabricated API response.

`python scripts/verify_cpv_hierarchy.py LOCAL.gc` parses the original XML safely,
checks pinned metadata/digest, all code IDs, duplicate rows/columns, parent IDs,
orphans and cycles. All 9,454 IDs equal the existing registry. Exact label equality
holds for 9,447 rows; 7 rows differ only in straight versus typographic apostrophes:
03331100, 15612400, 45215215, 45234160, 45236210, 55243000, 66513200.
The reference labels remain unchanged. Exact equality is deliberately required;
no punctuation normalization is used to authorize edges. The preliminary terminal
inspection used a system encoding and overstated differences; verified UTF-8
comparison and the generated audit are authoritative.

There are 9,409 explicit parentCode edges, 45 omitted parents, zero orphans and
zero cycles in the full original graph. 9,400 edges have exact matching child AND
parent labels and are usable; 9 edges incident to mismatched labels are withheld.
The derived JSON retains every mismatch, withheld edge and omitted-parent code.
No prefix, ordering, root or leaf inference is used. Missing/withheld parent is
`unknown_parent`, including chain endpoints; it is never asserted to be a root.

### Implemented hierarchy and compatibility

`cpv_parent`, `cpv_ancestors`, `cpv_descendants` use only packaged verified edges.
Ancestors are nearest-first; descendants are deterministic, unique, sorted and
explicitly `verified_edges_only`, not a claim of complete descendant coverage.
`cpv_category_match` consumes canonical CPV memberships with tri-state output:
True for exact/verified ancestor membership; False for exact-only nonmembership
or proven separate branches below a shared verified ancestor; None when incomplete
edges or unsupported evidence cannot prove the answer. Multiple memberships use
any positive match; all candidates must be proven negative before returning False.
Conflicting labels and independent AusTender/ZA schemes contribute no CPV match.
Legacy policies are not reinterpreted for descendant matching.

The original `source-classifications-cpv2008-v2` and
`observed-source-categories-v1` normalization outputs are unchanged, including
empty stored `hierarchies`; hierarchy traversal is an explicit lookup API, not a
silent snapshot backfill. No downstream chart/filter integration from 24P.3.4+
was added. Ninth-digit notation remains `unsupported_check_digit`: neither supplied
reference provides authentic validation digits/algorithm. Obsolete-code history
is unavailable. CPV and NACE remain separate; no industry crosswalk is invented.

### TED schema gate ? still pending

`python -m scripts.verify_ted_classification_fields LOCAL.html` verifies pinned
bytes and extracts actual four-column documentation rows, including aliases and
eForms references. `classification-cpv` (alias PC) aggregates BT-262/BT-263 at
Procedure, Part and Lot contexts, so it cannot by itself establish main/additional
role or an individual lot/part. `main-classification-{proc,part,lot}` references
BT-262-{Procedure,Part,Lot}; `additional-classification-{proc,part,lot}` references
BT-263-{Procedure,Part,Lot}. Related classification-type fields exist; a generic
classification field name alone does not prove every reported code is CPV.

The supplied table columns are Search field, Alias 1, Alias 2, Reference in the
eForms SDK. They contain no JSON scalar/array/object type, cardinality, per-lot
binding or response example. Existing project `test_ted_source.py` fixtures prove
only the old nonclassification response fields. Thus actual classification JSON
types and CPV scheme/context binding remain unverified. TED_FIELDS and parser
extraction are unchanged; negative tests ensure scalar, list, number, object and
null candidate values are not guessed into CPV evidence. No positive API fixture
was invented. Next evidenced step: supply an offline official v3 response schema
or authentic scrubbed capture specifying these fields, types, scheme indicators
and part/lot identity binding; then implement and test extraction from that shape.
For withheld hierarchy edges, supply an authoritative label-equivalence/corrected
reference before promoting them. Check-digit support requires official validation
evidence. Industry support requires a separately verified crosswalk.

### Acceptance and verification

A/B: verified explicit graph and lookup/matching implemented with disclosed partial
coverage; all supplied IDs checked, mismatched edges withheld. C: search names and
eForms contexts verified, actual response shape BLOCKED/PENDING. D: safe unsupported
status retained. E: targeted and broad offline regressions recorded below. F: provenance
and blockers documented. **24P.3.3 does not meet all acceptance gates: PARTIAL.**
24P.2 real-browser acceptance remains PENDING; 24P.3.4+ remains unstarted.
No network, credential/.env access, dependency installation, production change,
migration, commit/push/deploy or modification of `.tmp-phase24*` directories.

PRODUCTION_TOUCHED=False


### Final completion-audit test evidence

Final broad offline command (no -k exclusions, no deselections or skips within
these 32 selected files; this is not a full repository run):

```powershell
python .cache/phase24p3/run_tests.py p33-broad-final tests/test_analytics_normalization.py tests/test_cpv_registry.py tests/test_cpv_hierarchy.py tests/test_ted_source.py tests/test_organization_workflows.py tests/test_organization_pdf_rag.py tests/test_pdf.py tests/test_company_profile_pdf.py tests/test_web_auth.py tests/test_auth_api.py tests/test_session_access.py tests/test_organization_api.py tests/test_organization_data.py tests/test_shortlist_api_behavior.py tests/test_shortlist_api_contract.py tests/test_shortlist_integration.py tests/test_shortlist_repository.py tests/test_saved_ui_contract.py tests/test_discovery_history_api_behavior.py tests/test_discovery_history_api_contract.py tests/test_discovery_preview_scoring.py tests/test_discovery_full_ai_contract.py tests/test_saas_core.py tests/test_premium_ui.py tests/test_phase24r_ui_audit.py tests/test_monitoring_ui_contract.py tests/test_responsive_ui.py tests/test_source_framework.py tests/test_austender_source.py tests/test_sam_gov_source.py tests/test_uk_fts_source.py tests/test_za_etenders_source.py
```

Result: **291 passed, 390 subtests passed**, exit 0, 129.13 seconds; one existing
Starlette deprecation warning. Covers Discover/history/Saved, PDF/company PDF/RAG,
auth/session/organization permissions, company and tenant isolation, source parsing,
legacy snapshots and 24P.2 UI contracts. External-connect and dotenv-open guards
remained active. No unrelated tests were edited or excluded to obtain this result.
The entire repository suite was not rerun; secret-dependent tests are outside
this explicit selected scope. No real-browser acceptance claim is made.

Focused commands: `python .cache/phase24p3/run_tests.py p33-focused-final
 tests/test_cpv_registry.py tests/test_cpv_hierarchy.py
 tests/test_analytics_normalization.py tests/test_ted_source.py` gave 59 passed
before adding six TED evidence/negative-shape cases. `python
 .cache/phase24p3/run_tests.py p33-evidence-final tests/test_cpv_hierarchy.py`
gave 10 passed before the final shared-ancestor negative assertions.
All final tests and those final assertions are included in the 291-pass run.
Counts overlap and must not be added. Initial runs had two new-test expectation
failures caused by the preliminary system-encoding comparison (15 versus 7 label
mismatches and the wrong unknown-parent sample). Corrected those new tests to the
UTF-8 verified source; no existing regression test was weakened.

All six JavaScript suites passed, each exit 0, with existing local Node
`.cache/phase24p0-local/.phase24p0-tools/node-v24.21.0-win-x64/node.exe`:
company.test.cjs, discovery.test.cjs, discovery_full_ai.test.cjs,
phase24r.test.cjs, premium.test.cjs, shortlist_ui.test.cjs. Each was invoked as
`NODE tests/js/FILE .cache/phase24p33-completion/dashboard.html`; the dashboard
fixture was rendered by existing `dashboard_html()`.
Changed Python compileall: PASS. `git diff --check`: PASS; new untracked files
also checked for trailing whitespace and merge markers: PASS. Git's existing
LF/CRLF notices remain. Existing `app/analytics/cpv_2008.json` and
`app/api/command_center_ui.py` are preserved; no staging/commit/push/deploy.


## 24P.3.3 public TED v3 capture audit - 2026-10-11 - PARTIAL

This section supersedes the earlier statement that no actual classification response
shape is verified. It does not supersede the unresolved entity-binding gate.
No existing source adapter, taxonomy, model or stored snapshot is changed.

Evidence endpoint: https://api.ted.europa.eu/v3/notices/search (public POST).
Supplied OpenAPI: `.cache/phase24p33-ted-evidence/ted-api-v3.yaml`, OpenAPI 3.1.0,
info.version 3.0.0; SHA256
`e0cfe4e84123c3b62118ca99e07e8b9a09467494846280b8c7e60d700fbd2ff8`.
Supplied response: `.cache/phase24p33-ted-evidence/public-search-response.json`, SHA256
`8246a105bea0e0603a2669bbc99a2098df704870449060c827bf7973c6585b81`.
Both match the user-provided digests. No original download URL for the YAML was
provided, so none is invented. These hashes bind bytes, not independent origin
verification. YAML/JSON are inert data, never imported/executed or followed.

`request.json` requests publication-number, classification-cpv and six main/additional
classification fields at proc/lot/part scope, with query
`classification-cpv = 45000000`, ACTIVE, page 1, limit 3, PAGE_NUMBER,
checkQuerySyntax false. No sorting or eForms restriction is present.
Actual envelope is an object: notices is an array of three objects,
totalNoticeCount is integer 108760, iterationNextToken is null, timedOut is false.
OpenAPI describes iterationNextToken as string; the actual PAGE_NUMBER null is
recorded without coercion. ACTIVE demonstrably does not establish recency or an
open deadline: all three publication identifiers end in 2016. No date is inferred
from the identifier, and totalNoticeCount is not the sampled/ingested count.

| Actual publication-number (string) | Actual classification-cpv (array of strings) |
| --- | --- |
| 392803-2016 | 45000000, 45200000, 45440000 |
| 392804-2016 | 45000000, 45200000, 45310000 |
| 392805-2016 | 45000000, 45200000, 45261000 |

Every notice has exactly publication-number, classification-cpv, links.
links is an object with xml/pdf/pdfs/html/htmlDirect objects mapping language keys
such as MUL/ENG to URL strings; it supplies no classification context. No links
were fetched. All nine sampled CPV values are exact supported registry strings;
there are five distinct codes across the sample. This proves a nonempty aggregate
CPV array, not main/additional roles or a per-procedure/part/lot classification.
None of the six requested contextual fields is present, not even as null/empty.
No scheme indicator, procedure identifier, part identifier, lot identifier or
relationship between a code and an entity appears in any sampled notice.

OpenAPI NoticeResponse describes classification-cpv and each of
main-classification-proc/part/lot and additional-classification-proc/part/lot as
array<string>. The latter six types are SCHEMA ONLY: no positive sampled values.
The earlier field-list ties aggregate classification-cpv to BT-262/263 across
Procedure/Part/Lot. Array positions, first code, common code, numeric prefix and
notice identity cannot establish an entity binding or main/additional role.

**Precise blocker:** verified aggregate CPV has no entity/role binding. The current
normalize_classifications exposes deduplicated (scheme, code) memberships at notice
level; feeding the aggregate into it would collapse potentially different lot
classifications into a tender claim. The safe branch required by the task is used:
TED_FIELDS and parser remain compatible; no guessed scoped parser or aggregate
canonical membership is introduced. Registry/hierarchy are preserved: 9,454 codes,
9,400 verified edges, nine withheld edges and 45 missing parents; unresolved edges,
unsupported check digits, obsolete history and CPV/NACE mapping remain explicit.
AusTender/ZA schemes stay distinct. No country, industry, role or scope inference.

Minimal future safe evidence capture (proposal only; not performed): obtain a public
response for a known eForms notice with a procedure classification and two identified
lots with different main and additional codes. Request publication-number, the six
context fields, their six classification-type companions and exact lot/part identity
fields documented in the supplied OpenAPI. Include a part-bearing notice separately
if absent. Retain request, raw response, public endpoint/notice URLs and SHA256.
If search returns parallel flat arrays without an authoritative positional binding,
that capture alone is insufficient: supply an official binding specification or an
inert public notice XML subset with explicit entity IDs and their classification
nodes, plus an evidenced way to relate those nodes to the Search fields. No additional
XML fetching is authorized or added to the adapter by this proposal. Require actual
nonempty values and explicit CPV scheme; missing part evidence stays unsupported.

Added `scripts/verify_ted_api_sample.py` checks pinned bytes, reads only the pinned
NoticeResponse section as text and derives the exact sanitized sample. The new
`tests/fixtures/ted_public_search_sample.json` retains all three real publication IDs,
code arrays, envelope, exact request, endpoint and hashes; only notices[].links is
removed. It contains no synthetic positive classification values. The verifier is
an evidence audit, not a production response parser. New tests cover actual values,
checksum tampering, old-notice compatibility, missing/malformed arrays, duplicate and
multi-code mutations, invented lot dictionaries/parallel IDs, and one mocked request
without link fetching. Negative mutations are explicitly synthetic. The real sample
also traverses Discover/history/Saved with owner/viewer/outsider/anonymous and active
company isolation, snapshot preservation and no refetch assertions.

24P.3.3 remains PARTIAL: scoped TED ingestion acceptance is blocked by the missing
positive entity/role evidence. 24P.2 real-browser acceptance remains PENDING;
24P.3.4+ is unstarted. All pre-existing tracked/untracked work is retained. No network,
.env access, secrets, installs, production, migrations, staging/commit/push/deploy or
changes to pre-existing .tmp-phase24 directories were performed.


### Public-capture audit validation

Focused guarded offline run: **80 passed**, exit 0 (five files: new
`test_ted_api_evidence.py`, TED source, CPV registry, CPV hierarchy, analytics
normalization). Broad guarded offline run: **306 passed, 390 subtests passed**,
exit 0; 33 selected files, the earlier completion-audit 32-file command plus
`tests/test_ted_api_evidence.py`, using new basetemp
`.cache/phase24p3/p33-ted-evidence-broad-final`. No skips/deselections; one existing
Starlette deprecation warning. Counts overlap. External-connect and dotenv-open
guards remained active. This is a relevant broad regression, not a full-repository
or browser run. Six local JavaScript suites passed (company, discovery,
discovery_full_ai, phase24r, premium, shortlist_ui) using the existing local Node
and `.cache/phase24p33-completion/dashboard.html`. Compileall for sources/analytics
and both new Python files passed. The initial new fixture had a PowerShell UTF-8
BOM, causing four new-test failures; regenerated as UTF-8 without BOM and reran
successfully. No existing regression expectations were changed.

Final new-test rerun after adding the five-unique-code assertion and exercising the
original response including links: **15 passed**, exit 0. Compileall and final
`git diff --check`: PASS. Reviewed all 20 untracked source/doc/test files under
app/scripts/tests/docs for trailing whitespace and merge markers: none found.
Pre-existing .tmp-phase24 directories were excluded and preserved.

## 24P.3.3 official eForms XML context integration - 2026-10-11 - PARTIAL

New supplied offline evidence, interpreted only as inert data:

- `.cache/phase24p33-xml-context/official_sdk_cn_24_minimal.xml`, 11,308 bytes,
  SHA256 `3bba90994d3e7d86ed8bb07f5c2fc49b8be27523b9ac5397c83ee86312b43ef8`.
  Source attribution: official OP-TED/eForms-SDK repository
  (`https://github.com/OP-TED/eForms-SDK`). No precise revision/download URL was
  supplied; none is invented. XML declares UBL 2.3, eforms-sdk-1.16, notice
  VersionID 01. This is an SDK example, NOT published-notice XML. Its comment
  referring to an older notice does not establish publication of these bytes.
- `.cache/phase24p33-xml-context/official_eforms_lot_schema.html`, 544,407 bytes,
  SHA256 `79241647c6acae10fcf61b3112cef35228339c632c664bfc4f8101f82c0556bd`.
  Canonical URL declared in the supplied page:
  `https://docs.ted.europa.eu/eforms/latest/schema/procedure-lot-part-information.html`;
  displayed documentation version 1.15. This is distinct from XML SDK 1.16 and
  CPV vocabulary 2008. Hashes bind local bytes, not independently authenticated origin.

The supplied schema's Table 1 documents `cbc:ID/@schemeName` Lot/LOT-XXXX,
LotsGroup/GLO-XXXX and Part/PAR-XXXX on separate `cac:ProcurementProjectLot`
elements. IDs are unique within a notice. Procedure information lives in root
blocks, not inside every lot. Classification section BT-26/262/263 documents
`cac:ProcurementProject/cac:MainCommodityClassification/cbc:ItemClassificationCode`
and the AdditionalCommodityClassification counterpart, with `@listName="cpv"`.
Groups are retained as their own contexts; no group CPV or group-to-lot membership
is invented. Groups and Parts cannot coexist. Internal procurement project IDs
are retained separately from technical IDs.

`app/analytics/eforms_xml.py` supplies deterministic `extract_eforms_classifications`
over already available UTF-8 bytes, with required caller evidence-kind/source-reference
labels. Output is an independent versioned sidecar, never passed into notice-level
`normalize_classifications` or company products. Each entry preserves the exact
eight-character string, raw context/procedure ID, ID attributes, main/additional role,
CPV 2008 validation and original node location as a namespace-expanded indexed path.
Paths are locators, not executable XPath; lexical XML prefix aliases are not retained.
The complete original bytes remain available in the pinned fixture and are SHA256-bound.
UBL, customization and notice versions, notice ID, internal IDs, source reference,
XML/schema/CPV reference checksums are retained separately. Caller labels do not prove
publication/authenticity; the exact official example digest cannot be labeled published.

Fail-closed limits: 2 MiB UTF-8 bytes, 64 element levels, 20,000 elements; DTD and
ENTITY declarations forbidden before parsing, including external declarations.
Reject malformed XML, unknown declared/used namespaces, unqualified elements,
unsupported root, duplicate/ambiguous technical IDs, unknown schemes/paths,
explicit listVersionID other than 2008 (absence means pinned validation reference),
nonexact/unknown/check-digit CPV, multiple project blocks and ambiguous main nodes.
Unknown classifications reject the complete extraction instead of yielding partial
claims. Only the evidenced ContractNotice root is currently supported. This is a
small whitelist extractor, NOT full XSD/business-rule validation. Other notice roots,
supplementary classification systems and check-digit notation stay unsupported.
Linked URIs, schemaLocation, includes and HTML scripts are never fetched/executed.

Offline fixtures in `tests/fixtures/eforms/`:

- Official XML copy: exact source bytes/hash above, distinguished as `sdk_example`;
  procedure `4805c409-5939-4be9-8abd-837f7a5fee23`, lot `LOT-0000`, internal ID `1`,
  both with main `72230000`. Equality of these two codes is not scope equivalence.
- `synthetic_multiple_lots.xml`, SHA256
  `63fad45f01f5bd1d4d73104c281da8bca19a06e2bd1122bd81863a879af7a2b0`:
  distinct procedure/lot codes, additional role, leading-zero code and separate group ID.
- `synthetic_part.xml`, SHA256
  `dc7c3a8e4216b7415a601d9fd9140f7d78ff05d038e324303b19388ebbd3a44e`:
  separate Part identity. Synthetic fixtures/mutations are context unit tests, not
  official examples, valid complete notices or live extraction evidence.

### Existing connector evaluation and future acceptance

Existing `TedApiSource.fetch` performs Search POST JSON only; TED_FIELDS is unchanged.
`catalog.py` declares default SourceCapabilities (documents false); `ingestion.py`
allows TED host api.ted.europa.eu and one existing request. Search response XML links
are URLs, not XML bytes. Thus this connector cannot supply XML without extra fetching.
No optional live-detail route, new network call, host, field request or capability was
added. The sidecar function can accept separately authorized, already available bytes,
but is deliberately unwired. Existing NoticeEnrichment v1 would flatten memberships
and does not support these contextual roles; attaching this sidecar there is unsafe.
Search `classification-cpv` remains **aggregated/unbound**, with no main/additional
role or entity membership promoted into adapter enrichment.

Future integration acceptance requires authentic offline published-notice XML with
publication/notice identity binding to the Search record, exact request/acquisition
provenance and checksums; a procedure and two identified lots with different main
and additional codes; a separately evidenced Part-bearing supported root; and an
authorized existing-byte acquisition/storage contract. Any future fetching needs
separate authorization and bounded connector policy. Add versioned contextual
storage/validation and consumers that explicitly select scope without notice/company
flattening, tenant/role/company regression and old snapshot compatibility. Provenance
labels supplied by clients are not sufficient. The SDK example cannot close this gate.

**24P.3.3 remains PARTIAL**: offline XML scope extraction is implemented and tested,
but published-notice ingestion/entity binding and Part-bearing notice root coverage
are not verified. Earlier withheld hierarchy edges, check digits, obsolete history
and CPV/NACE limits remain as documented. 24P.2 browser acceptance stays PENDING;
24P.3.4+ remains unstarted. Existing uncommitted work, snapshots and adapters preserved.
No external network, dotenv/secrets, installs, migrations, production, staging,
commit/push/deploy or changes to `.tmp-phase24*` directories.

PRODUCTION_TOUCHED=False

### XML context validation

Guarded runner `.cache/phase24p3/run_tests.py` forbids external connects and dotenv
opens. Focused `p33-xml-focused-final` selection: eForms XML, TED API evidence,
CPV registry/hierarchy, analytics normalization and TED source: **107 passed**, exit 0.
Final narrow `p33-xml-version-final tests/test_eforms_xml.py`: **28 passed**, exit 0,
after adding explicit old-CPV-version rejection. Broad run predates that last narrow
addition; the final XML suite verifies it. Counts overlap and are not additive.

Broad exact command:

```powershell
python .cache/phase24p3/run_tests.py p33-xml-broad-verified tests/test_eforms_xml.py tests/test_ted_api_evidence.py tests/test_analytics_normalization.py tests/test_cpv_registry.py tests/test_cpv_hierarchy.py tests/test_ted_source.py tests/test_organization_workflows.py tests/test_organization_pdf_rag.py tests/test_pdf.py tests/test_company_profile_pdf.py tests/test_web_auth.py tests/test_auth_api.py tests/test_session_access.py tests/test_organization_api.py tests/test_organization_data.py tests/test_shortlist_api_behavior.py tests/test_shortlist_api_contract.py tests/test_shortlist_integration.py tests/test_shortlist_repository.py tests/test_saved_ui_contract.py tests/test_discovery_history_api_behavior.py tests/test_discovery_history_api_contract.py tests/test_discovery_preview_scoring.py tests/test_discovery_full_ai_contract.py tests/test_saas_core.py tests/test_premium_ui.py tests/test_phase24r_ui_audit.py tests/test_monitoring_ui_contract.py tests/test_responsive_ui.py tests/test_source_framework.py tests/test_austender_source.py tests/test_sam_gov_source.py tests/test_uk_fts_source.py tests/test_za_etenders_source.py tests/test_canada_buys_source.py tests/test_nz_gets_source.py tests/test_connector_workers.py tests/test_india_cppp_source.py tests/test_kz_goszakup_source.py tests/test_eis_business_metadata.py
```

Result: **473 passed, 390 subtests passed**, exit 0, 184.73 seconds, 40 selected
files, no skips/deselections; one existing Starlette deprecation warning. Relevant
broad offline regression, not full repository/browser/live-source acceptance.
Initial XML run had 106 passes and two setup/teardown errors because pytest put
the 2 MiB parameter into a Windows environment-variable test ID; fixed with short
explicit parameter IDs. A broad invocation referenced a nonexistent test filename
and ran zero tests; corrected to existing test_connector_workers.py before the
successful broad run. No unrelated tests or expectations changed.

Six JS suites passed using existing local Node and the existing rendered dashboard
fixture: company, discovery, discovery_full_ai, phase24r, premium, shortlist_ui.
Compileall for analytics/sources and the new test: PASS. git diff --check: PASS.
Authored new files checked separately for trailing whitespace/merge markers: PASS.
Official copied XML retains original comment whitespace for byte fidelity; an initial
generic whitespace check flagged this source whitespace, which was preserved.
Pre-existing tracked app/tests diff compared with the starting diff: unchanged.

## 24P.3.4 preliminary fit contract - 2026-10-11

Immutable policy **preliminary-fit-v1** lives in `app/analytics/fit.py`.
Eligible numeric input is exactly a Python int/float (excluding bool), finite and
within **0..90 inclusive**, at explicitly known `metadata_preview` stage.
Low `[0,35)`, Medium `[35,65)`, High `[65,90]` are disjoint. Matched is eligible
score >=35; High Fit is eligible score >=65. Every predicate uses the identical
eligible denominator; unknowns are excluded and separately reported, never zero.
No numeric strings, Decimal, complex, containers, nonfinite or out-of-range values
are coerced. Raw input is retained in FitClassification. This is preliminary
relevance, not AI win probability. Stop factors remain separate reasons in the
existing ScoringResult and UI; neither presence nor absence changes band eligibility.
Policy changes require a new version, never redefining this version's thresholds.

Verified engine evidence: `app/scoring/preview.py` wraps score_tender, uses product
matches in title/object/technical text, assigns 0/35/60/70 relevance, applies the
existing supply-intent +10 and incidental-service cap, then clamps/rounds to 0..90.
The upper contract bound is 90 even though the current strongest formula branch
returns 80. Category criterion earned points and other document criteria are not
the overall preview band. No formula, score, weights, completeness or stop factors
were changed. **metadata-preview-v2** now names this existing formula, matching the
existing V2 workflow annotation; it is distinct from scoring-run wrapper version
`scoring-engine-v1` and CompanyProfile.profile_version (a user profile label).
Full-document score_tender retains its separate 0..100 contract.

New authenticated Discover results contain optional frozen `preliminary_provenance`:
organization/company IDs from the authorized active workspace, canonical profile
digest, engine version, scoring policy version, scoring stage and actual UTC
`scored_at` measured just after that item's calculation. Unknown future sidecar
fields survive serialization; unrecognized engine/policy/stage fails classification
closed. Future discovery-history writes automatically retain this sidecar through
the existing model_dump_json snapshot path; Saved decode/round-trip retains it too.
No database migration, old snapshot rewrite or default evidence backfill occurs.
Missing sidecar decodes as None. `analysis_stage`'s existing schema default is NOT
historical evidence: classify_discovery_fit checks model_fields_set for explicit
presence. full_scoring/full_analysis never supply preliminary fit.

Reused `app/scoring/runs.py:profile_digest`: SHA256 of canonical sorted-key compact
UTF-8 JSON with allow_nan=False, over CompanyProfile.model_dump(mode='json'). It
includes every serialized constraint, defaults, name and profile version; list
order remains significant. Determinism and changed constraints are tested. A name
or digest alone cannot bind a company: exact authorized organization AND company
IDs must match. Digest equality additionally binds CURRENT FIT to the current
authorized profile. Changed/missing digest, absent/untrusted origin, missing/naive
scoring time or conflicting versions/stages yield unknown. No hidden re-score or
separately authorized re-score path was introduced.

Pure callers supply server-only VerifiedFitContext AFTER membership/company checks
and a trusted-origin decision. It is not a bearer token and is never built from
request JSON. Server-created Discover / repository-scoped discovery-history may
be trusted; client-submitted Saved snapshots may not, even if their evidence looks
identical. The existing history repository rechecks membership/company on reads
and writes; active-company resolution checks membership before Discover. Current
digest must be computed from that authorized profile, never a company label.
This checkpoint adds no analytics endpoint, population service, GET write, source
fetch, cache, job, background mutation or change to viewer access. Existing viewer
search-history persistence semantics documented in 24P.1 are preserved.

Trusted legacy H with an explicitly stored preview stage may be classified ONLY
as **historical preview at search time** without an immutable digest. Present
scope/version/stage conflicts remain unknown. This is not current-profile
eligibility and does not prove an old engine/policy version. Old H supports stored
profile_name/profile_version, raw preview score/criteria/stop factors, explicit stage
where present, and repository organization/company/search-created_at. It does NOT
support retroactive immutable profile digest, engine/policy version, actual scoring
time, immutable document revision or full-document current-company binding.
History.created_at is persistence/search-event time, not calculation time.

Existing durable R already stores digest, scope, engine wrapper version and database
calculated_at, and rejects stale profiles. Its serialized legacy scoring has no
explicit preview policy/stage sidecar; it is not silently accepted as a Discover
preview. Its calculated_at is the fenced materialization time, not a newly invented
per-item scoring instant. R/P/opportunity APIs and storage remain unchanged and
are regression-tested. No join by tender identity or company name is added.

Acceptance here is the reusable eligibility/band/provenance contract. KPI/ring/table/
filter consumers must call this same policy over their future authorized population;
their wiring, aggregation, pagination and secure analytics API remain 24P.3.5+.
24P.3.2 consumer verification remains pending, 24P.3.3 remains PARTIAL (published
XML integration blocked), and 24P.2 browser acceptance remains PENDING.

### 24P.3.4 validation and closure

**24P.3.4 COMPLETE for the authorized reusable contract checkpoint.** Guarded
offline targeted run: 91 passed, exit 0 (analytics fit, preview, full-AI contract,
history API behavior, scoring workers). Broad: 567 passed, 390 subtests passed,
exit 0, 200.84s, 44 files, no skips/deselections. Exact selection is the preceding
40-file XML context broad command plus tests/test_analytics_fit.py,
tests/test_scoring_workers.py, tests/test_scoring.py and
tests/test_discovery_history_repository.py, under new basetemp p34-broad.
Final narrow analytics-fit run after final trust/cross-tenant assertions: 38 passed,
exit 0 (p34-isolation-final). Counts overlap. One existing Starlette warning.
Initial new fixture attempted duplicate workspace names, correctly rejected by
the existing API; fixed the fixture to different workspace names with identical
profiles. No existing assertions were changed. All six local JS regressions
(company, discovery, discovery_full_ai, phase24r, premium, shortlist_ui) passed,
each exit 0, with existing Node and dashboard fixture. Changed Python compileall
and git diff --check exit 0. Reviewed 24 untracked source/doc/test files for AST
syntax, conflict markers and trailing whitespace; no problems. XML bytes and
existing .tmp-phase24 directories preserved. No network, dotenv/secrets, install,
staging/commit/push/deploy, production or migration; 24P.3.5+ remains PLANNED.

## 24P.3.5 retrieval continuation — PARTIAL

The 24P.3.4-era planned status is superseded by the additive verified retrieval
subset documented in [PHASE24P35_RETRIEVAL.md](PHASE24P35_RETRIEVAL.md).
Stored H snapshots preserve enrichment and preliminary provenance without any
re-fetch, backfill or scoring. R bodies use their immutable candidate revisions;
they are not merged into H or promoted to current Discover preview evidence.
Guarded broad: 395 passed and 390 subtests passed; focused: 96 passed; final
acceptance: 8 passed (overlapping selections). Six JS suites, compileall and
diff-check pass. Exact completeness blockers and API bounds are in the register.
24P.2 browser acceptance stays PENDING, 24P.3.3 stays PARTIAL, and 24P.3.6+
are not begun. No prior snapshot, fixture, fit policy or enrichment code changed.
