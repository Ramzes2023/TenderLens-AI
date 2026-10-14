# Phase24 customer acceptance V5

CODEX_DELIVERY_DONE=YES (source delivery only)
HOST_TESTS_PENDING=YES
CUSTOMER_ACCEPTANCE_OFFLINE_GATE=PENDING_HOST_EXECUTION
BROWSER_AUTHENTICATED=NOT_VERIFIED
P3.9_PRODUCTION_GATE=BLOCKED

No new live or executable test PASS is claimed. Codex performed local source inspection
and `git diff --check` (exit 0; Git emitted line-ending warnings). Python, Node,
the CLI and public HTTP execution are reserved for the Windows host launcher.
The earlier five-notice TED verification remains prior evidence only.

## Exact delivery files

- Modified `app/api/organization_workflow_routes.py`: reject stale scoped Discover
  results after fetch and reject Save with a conflicting preview company/profile.
  All accumulated earlier edits in this file were preserved.
- New `scripts/phase24_customer_acceptance_probe.py`.
- New `tests/test_phase24_customer_acceptance.py`.
- New `tests/js/main_phase24_customer_acceptance.test.cjs`.
- New `docs/PHASE24_CUSTOMER_ACCEPTANCE_V5.md`.

No second frontend, dependencies, auth modules, source catalog, migrations or
production configuration changed. Branch inspected: `phase24-professional-saas-core`.

## Local contract trace

1. `organization_company_routes.py` exposes organization-company
   `POST /companies/{company_id}/profile-from-pdf/preview`. It produces a suggested
   profile without saving it. Explicit review/apply uses the existing
   `PATCH /companies/{company_id}` profile update, with same-origin and service RBAC.
   Preview/apply does not initiate source discovery or monitoring. Optional PDF
   extraction is deliberately omitted from this new gate: it starts with an
   explicitly approved synthetic profile via the actual create-company API.
   Existing PDF preview/apply integration tests remain available separately.
2. `POST /api/v1/organizations/{organization_id}/discover/tenders` authenticates
   a real session, resolves the authorized active organization company and rejects
   missing companies with 409. It calls the existing monitoring service's
   `fetch_matches_from_catalog_for_profile`, passing profile monitoring keywords.
   The catalog retains its current behavior: EIS can use keyword feeds, while TED
   fetches its canonical ACTIVE public search and company filtering happens locally.
   This milestone does not pretend TED receives a product-specific API query.
3. Catalog/fetcher source outcomes feed `TenderDiscoveryResponse`; each included
   notice maps through `analysis_from_notice` and `score_metadata_preview`.
   `score_tender` supplies constraints, criteria explanations, evidence, unknown
   statuses and stop factors. Metadata preview adds product relevance; it is not
   full-document analysis or a probability of winning. Missing deadline/price stay
   null. A missing-information list is not automatically synthesized; criteria
   explanations and rendered missing metadata expose unknowns.
4. Returned items carry server-created preview provenance: organization, company,
   profile digest, engine/policy and timestamp. Discover now re-resolves authorized
   company after retrieval, returning 409 if company/profile changed and 403 if
   membership was revoked. This prevents returning/persisting that stale search.
5. Save uses `POST .../shortlist`; list uses `GET .../shortlist`. The backend
   chooses the authorized active company and production repository checks write
   roles. Present preview provenance must match that company/profile, otherwise
   Save returns 409. Provenance remains an evidence sidecar, not an auth token;
   legacy snapshots without it remain accepted for compatibility. Forged/stripped
   client scores are not promoted to trusted server evaluation by this change.
6. `POST .../scoring/evaluate` deterministically scores supplied analysis facts
   against the active company. It does not extract PDFs or prove their origin.
   `POST .../monitoring/scan` separately enforces owner/admin/member and uses
   organization/company-scoped dedup. Ad hoc Discover never claims seen-state.

`discovery_ui.py` is mounted by the existing `saas_shell.py`. Shipped
`static/discovery.js` already explains profile/search keywords, renders per-source
Fetch outcomes and Preliminary Match, reasons, unknowns and stops, filters fetched
results, restricts external links to canonical HTTPS official hosts, escapes
notice HTML, uses scoped Save and handoffs, and discards late Discover/Save results.
The existing unavailable/login/permission states and port-8765 guard are retained.
No cosmetic UI changes were necessary.

## Programmatic assertions supplied

The Python acceptance test uses the existing FastAPI TestClient and real account
session, organization, company and monitoring services on disposable SQLite.
Default dotenv loading is suppressed during application-fixture import. There
is no PostgreSQL connection and no dependency override of session auth or RBAC.
TED HTTP is intercepted with MockTransport using the actual TED adapter/catalog.
Saved storage is an in-memory double that calls the real organization service
for role authorization and company service for scope checks. Production Saved
SQL persistence is therefore not verified by this gate.

Assertions cover:

- Authorized create-company -> scoped Discover -> response-model JSON validation
  -> explainable metadata criteria -> Save/list -> explicit Monitoring scan.
- Positive cables and negative furniture match; unknown price/deadline, currency
  stop factor and supplied document-fact scoring; metadata never marked full AI.
- Save idempotence, company shortlist isolation, cross-organization company 404,
  missing-company 409 with no personal fallback, viewer write denial, outsider
  403 before source calls, unauthenticated 401, explicit cross-site write rejection.
- Repeat Discover leaves seen-state untouched; explicit Monitoring claims scoped
  state and repeat scan returns no new notices.
- Empty success, partial failure, total failure, 403/429/503 source failures;
  company switch during fetch, membership revocation during fetch, profile edits
  and stale Save conflicts.
- Offline probe makes zero HTTP and reports zero real results; mocked live mode
  exercises the single-request budget and honest failure statuses.

The new JS entry point asserts malicious HTML escaping, invalid official URLs,
missing price/deadline, stops, empty/failure messages and document/metadata display
distinction. It reuses the existing browser-script harness, executing shipped
handlers for late JSON, late Save, role downgrade, canonical URLs, filters, 401,
403, 409, 503 and preview/personal-scope refusal. This minimal DOM harness is not
a real browser or authenticated browser session.

## Data and source separation

Offline records are **synthetic injected TED-schema records**, not a captured live
dataset. Their identifiers are fixture identifiers and must not be interpreted as
verified public notices. The source key `ted`, parser field names and generated
canonical URL format are genuine. `real_results_count=0` in offline mode;
`fixture_results_count` is separate. All evaluations use the current metadata
preview formula and an explicitly synthetic cable profile; no customer data or LLM.

Live CLI constructs only a TED registration through the existing registry/catalog.
The existing adapter sends one POST to `https://api.ted.europa.eu/v3/notices/search`.
FetchPolicy permits only that HTTPS host, one dispatch and 2 MiB. Redirects are
disabled; adapter uses `trust_env=False`, no auth and verified default TLS. An outer
15-second timeout bounds the operation; adapter timeout is 12 seconds. No retries,
custom URL, proxies, credential lookup, custom CA or DB. Errors are reported with
a fixed safe reason; transport exception text is not copied into the report.
Up to three returned notice IDs, canonical URLs and bounded titles accompany
actual metadata scores, unknown explanations and stop factors. Empty or failed
live fetch is UNAVAILABLE with nonzero exit, never PASS.

Coverage is TED only in the live CLI. UK FTS appears only as injected failure
coverage; its last reported unavailability is unchanged. SAM.gov requires a key
and is not attempted. No claims about other source availability.

## Host reproduction

Run through the host launcher with its existing secret/configuration isolation:

```powershell
python -m pytest -q tests/test_phase24_customer_acceptance.py
node tests/js/main_phase24_customer_acceptance.test.cjs
python scripts/phase24_customer_acceptance_probe.py --offline --output "$env:TEMP\phase24-acceptance-offline.json"
python scripts/phase24_customer_acceptance_probe.py --live --output "$env:TEMP\phase24-acceptance-live.json"
```

Focused regression checks after the gate:

```powershell
python -m pytest -q tests/test_organization_workflows.py tests/test_shortlist_api_behavior.py tests/test_phase24_live_discovery_contract.py tests/test_phase24_live_to_scoring.py tests/test_pdf_discovery_scoring_monitoring_e2e.py
git diff --check
```

Mocked tests exercising `live=True` are fixture evidence, even if the code-path
report says LIVE_VERIFIED. Only an independently executed, unmocked host CLI report
can constitute fresh public live evidence. Do not substitute mock output for it.

## Disposable staging browser checklist and blockers

No server was started, no existing ports/containers touched. In-browser acceptance
is NOT_VERIFIED: real Saved SQL storage and authenticated browser integration need
a separately provisioned disposable staging runtime, never production DB/secrets.
Port 8765 deliberately refuses API activity and is not functional session proof.

On disposable staging: sign in as a synthetic owner; create a synthetic organization
and company; preview a synthetic catalog PDF, review then explicitly apply; check
Discover shows active company keywords; click Find; inspect source outcomes,
metadata labels, missing fields, reasons/stops and canonical links; filter sources;
Save and inspect Saved; open Monitoring and explicitly scan. Switch company during
fetch and Save; verify stale results are discarded/rejected. Repeat with viewer,
outsider and a second tenant; verify role and isolation states. Full tender-PDF AI
execution is outside this no-LLM milestone; its renderer contract is tested only.

Remaining gaps: host execution of all new gates; unmocked one-shot live TED result;
real browser plus disposable Saved persistence integration. P3.9 remains BLOCKED.
No deploy, commit, push, staging, dependency changes or other worktree access occurred.
