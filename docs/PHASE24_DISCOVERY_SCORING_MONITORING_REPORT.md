# Phase24 scoped discovery, scoring and monitoring proof

Status: implemented regression proof; execution HOST-PENDING. No PASS claimed.
P3.9 production API cancellation/resource-isolation gate remains BLOCKED.

Only two new tests and this report were written. Existing Discovery already
distinguishes metadata preview, preliminary match, completeness, missing criteria,
source failures and uploaded-document analysis. No UI or protected backend change
was necessary. Existing local edits and existing tests were preserved.

## Actual local API contracts

The workflow router in app/api/organization_workflow_routes.py uses
`/api/v1/organizations/{organization_id}`. Tests exercise:

- POST `/api/v1/organizations`, POST scoped `/members`, POST scoped `/companies`.
- POST scoped `/companies/{company_id}/profile-from-pdf/preview`: draft only.
- GET and PATCH scoped `/companies/{company_id}`: explicit authorized apply.
- POST scoped `/companies/{company_id}/activate`: shared active company selection.
- POST scoped `/discover/tenders`: catalog fetch, real profile prefilter and
  preliminary scoring of metadata. Returns items, attempted/successful/failed
  source lists and partial/total failure flags. Items expose metadata_analysis,
  preliminary_scoring, analysis_stage and full_ai_analyzed.
- POST scoped `/scoring/evaluate`: accepts factual TenderAnalysis directly and
  returns ScoringResult against the current active company. This test supplies
  synthetic document facts; it does not prove PDF extraction or full AI analysis.
- POST scoped `/monitoring/scan`: EIS feed matches and company/org-scoped seen
  state, returning a list of new notices. Separate from global discovery.

## Proof matrix

| Chain | Real implementation exercised | Synthetic boundary | Status |
| --- | --- | --- | --- |
| Org/company/auth | TestClient, existing repositories and services, temporary SQLite | Established OrganizationWorkflowTests setup | Host-pending |
| PDF draft/apply | Preview API, draft service, authorized PATCH and persisted GET | FakeProvider LLM output; bounded PdfSummary instead of PDF parser | Host-pending |
| Protected fields | Identity, mode, exclusions, currencies, budget and all hard-stop flags checked before/after apply | Synthetic company | Host-pending |
| No automatic search | Catalog call list and feed fetch spy remain empty through preview/apply | External fetch boundaries only | Host-pending |
| Discovery | Existing route, fetch_matches_from_catalog_for_profile, prefilter_notice, score_tender | PartialCatalog external response: TED notices and UK failure | Host-pending |
| Candidate filtering | Product match included; used/unrelated/over-budget excluded | Synthetic notices | Host-pending |
| Currency honesty | USD retained by prefilter, unchanged amount/currency, scorer reports budget failure and stop | No FX service or conversion | Host-pending |
| Factual scoring | Existing evaluate endpoint/engine, evidence, unknown region/security/documents, missing facts and risks | Direct synthetic TenderAnalysis facts | Host-pending |
| Negative scoring | Unrelated category, excessive EUR value, USD rejection, absent currency unknown | Same saved active profile | Host-pending |
| Monitoring | Existing scan route, actual EIS prefilter and repository dedup | DynamicSource synthetic EIS feed | Host-pending |
| Scope | First scan new, second empty; other company uses its own profile; returning company stays deduped; other org gets independent first match | Temporary fixture DB only | Host-pending |
| Authorization | Viewer/outsider cannot PATCH or scan; outsider cannot discover/evaluate; foreign org company GET is 404 | Real sessions/memberships in fixture | Host-pending |
| UI | Actual renderer functions plus actual script in VM, source/provisional/unknown labels, stale same-org company response rejected and request aborted, org reset clears counts | Minimal DOM and delayed fetch | Host-pending |

No scorer, prefilter, authorization, organization/company service or dedup function
is mocked. The fixture uses the existing application and a disposable local DB;
no real tenant, Postgres, provider, source, customer PDF or analytics is used.
Fake catalog failures are test telemetry, not measured live source health.

## Actual validation and commands

On this sandbox, `python --version` and `node --version` failed with PowerShell
CommandNotFoundException. Get-Command also found no python3, py or nodejs.
Therefore neither new suite nor previous suites ran. No packages were installed
and no network calls were made. Source inspection found no AGENTS.md under the
root or inspected app/tests/docs directories. Tests remain unverified at runtime.

Run on the Windows host with its established environment, disabling Python cache
and pytest cache writes to preserve the write boundary:

```
python -B -m pytest -p no:cacheprovider tests/test_pdf_discovery_scoring_monitoring_e2e.py -q
node tests/js/main_discovery_scoring_monitoring.test.cjs
```

The previous milestone's reported passes were user-provided context, not results
from this session. No existing test was rewritten or weakened.

## Limits and remaining blockers

- Runtime results and any backend defect remain unknown until host execution.
  No confirmed protected-backend defect was found by source inspection; none was
  changed. A failing host run must identify its actual path/function and assertion.
- No real source transport, source health, LLM, PDF extraction, full tender PDF
  analysis, Qdrant RAG, history persistence, dashboard statistics or production
  resource isolation is proven here. UI preview on port 8765 disables /api.
- Documents not declared by the company remain not_scored, not confirmed
  eligibility. Fit is deterministic compatibility, not win probability. Stops
  are asserted separately from score; a high score cannot erase a hard stop.
- Discovery and EIS monitoring are separate feeds; synthetic shared notice IDs
  do not establish live catalog/feed equivalence. Monitoring state is disposable.
- P3.9 remains BLOCKED; this work makes no production-readiness claim.

Recommend a separate future staging validation with explicit consent for selected
real sources and AI, after the P3.9 gate is resolved. That validation must measure
actual transport failures, document provenance and cancellation/resource isolation
without using production tenant data or automatically applying PDF suggestions.
