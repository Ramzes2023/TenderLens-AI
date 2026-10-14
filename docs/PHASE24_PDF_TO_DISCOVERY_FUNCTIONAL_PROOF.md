# Phase 24: Company PDF profile to discovery functional proof

Status: implementation and test review completed; runtime sign-off PENDING.
This is an existing-app milestone, not a new engine. No production readiness claim.

## Source inspection

Inspected the existing organization routes, organization company routes, organization
workflow routes, main application factory, API settings/runtime, dashboard, SaaS shell,
shell navigation, discovery JavaScript and premium CSS. Also inspected company profile
analysis, monitoring service/prefilter, metadata scoring preview, LLM operation dispatch,
RAG ingestion and existing company PDF, organization company, organization workflow,
discovery scoring and organization PDF/RAG tests. No private documents, environment
files, tenant data, caches, credentials or private logs were read.

The existing test helpers create temporary SQLite repositories and inject an ApiRuntime
into TestClient. They do not build the live runtime. The new test suppresses dotenv
file I/O during helper import because main.py constructs default settings at import.
The supplied runtime does not start a real analytics service or request analytics routes.
P3.9 authenticated analytics resource safety remains BLOCKED.

## Exact existing API contracts exercised by the new test

- POST /api/v1/organizations with a synthetic shared organization name.
- POST /api/v1/organizations/{org}/members with a synthetic viewer account.
- POST /api/v1/organizations/{org}/companies with an initial profile.
- POST /api/v1/organizations/{org}/companies/{company}/profile-from-pdf/preview.
- GET /api/v1/organizations/{org}/companies/{company} before and after Apply.
- PATCH /api/v1/organizations/{org}/companies/{company} with suggested_profile.
- POST /api/v1/organizations/{org}/discover/tenders for the active company.

No new routes were created. Authentication uses the existing synthetic account/session
fixture. The first company is active under the existing API behavior. A second shared
organization from the fixture provides a cross-organization company lookup check.

tests/test_pdf_profile_discovery_e2e.py contains one integration test. It uses the
existing temporary SQLite helper and FakeCatalog/FakeProvider. Only external provider
output, source fetch and the expressly permitted bounded PDF summary are synthetic;
profile analysis/validation, protected-field merge, permissions, PATCH persistence,
active-company resolution, discovery prefilter and metadata scoring remain real code.
The provider prompt must contain the offered industrial pumps text. This checks the
input/output contract with deterministic provider output, not real model comprehension.

Assertions cover preview without persistence, explicit Apply, product fit, exclusion
of used pumps, rejection of unrelated furniture, unchanged identity/financial/exclusion
and hard-stop constraints, viewer write denial, outsider denial before PDF/provider work,
cross-organization isolation and no second provider call during discovery. Discovery
results are explicitly metadata_preview and full_ai_analyzed=false. Duplicate notice
handling, full financial rejection behavior and a whole live customer journey are not
claimed by this test.

## Actual user-visible changes

After a successful explicit Apply and company refresh, the existing company editor
offers "Review profile -> Find tenders" only if that edited company is already active,
the workspace is shared, the user can write and the port is not the disabled 8765
preview. Clicking only changes the existing page hash to Discover. It rechecks role,
organization and active company. It does not activate a company, run discovery, call
the LLM, save a tender or modify the profile. The user must press the existing Discover
button to search. An inactive edited company gets no misleading shortcut.

The three lower onboarding cards now have an opaque dark background, matching their
existing light command-view headings and paragraphs. The new JavaScript test executes
the actual Apply function and click handler with a bounded DOM/API harness, checks
success/failure/role/scope/preview gates and no-autoapply behavior, and computes WCAG
contrast for both text colors against the card background (at least 4.5:1). Existing
focus rules and responsive grid rules are retained. EN/RU locale files, shared labels
and Geography 176 outlines were not changed. The new action currently uses English.

## Validation status

Attempted Python command:
`python -m pytest -p no:cacheprovider tests/test_pdf_profile_discovery_e2e.py -q`
with PYTHONDONTWRITEBYTECODE=1. It did not execute: python is not available in this
host's PATH. py and pytest were also not found; checked conventional Python locations
were absent. No installation was attempted.

Attempted JavaScript command:
`node tests/js/main_pdf_to_discover.test.cjs`.
It did not execute: node is not available in PATH; the conventional Program Files
Node executable was absent. Neither new test has a PASS result. Source inspection
and PowerShell file/contract checks executed. Browser rendering remains host pending.
The earlier reported 5 JS and 4 Python PASS results are user-provided prior evidence,
not tests rerun in this milestone.

On a host with the existing dependencies, run the two new tests above with dotenv
loading disabled and bytecode/cache writes disabled. Then rerun main_pdf_ai_ux,
main_pdf_ai_visual, main_ui_consistency, main_i18n and main_geography JavaScript
checks and the existing PDF profile/UI checks under the same safe test environment.
Inspect the lower onboarding cards at desktop and mobile widths and keyboard focus.
Until these execute, functional and visual sign-off remain pending.

## Limits and blocked/planned capabilities

The local 8765/dashboard preview intentionally disables /api. Workspace unavailability,
disabled profile controls and absent real metrics remain expected. Nothing enables it
or supplies fabricated metrics. No live source, LLM, network, database, API server,
worker, Docker or production environment was started. No tenant data/logs were used.

Company catalog PDF profile generation is distinct from tender PDF analysis/RAG.
PDF limits remain 10 MiB and 200 pages. Scanned image-only PDFs require OCR, which is
unavailable. Existing tender-PDF analysis does not prove automatic catalog-to-vector
ingestion. Persistent scoped RAG ingestion requires the worker and a successful job;
no such job or Qdrant/storage operation was exercised here. No automatic complete
AI-document tender selection journey or international source availability was verified.
Source connectors exist, but synthetic successful_sources is fixture output and does
not establish live access, coverage, credentials, quotas or document availability.

No protected backend edit was required. Runtime availability blocks executing the new
proof on this host. P3.9 remains blocked independently and must not be bypassed.

## Next safe milestone

First execute and review the isolated tests and browser checks on the existing test
host. Then use an explicitly configured non-production test workspace, a bounded
approved source/provider, synthetic company catalog and public tender documents to
measure actual source retrieval, provider response, explicit Apply, discovery and
separate tender-PDF analysis. Record unavailable sources honestly. Exercise persistent
RAG only with a test worker and confirmed successful scoped job. Keep production and
real tenants excluded; resolve P3.9 safety before any real authenticated analytics use.

## Exact files changed in this milestone

- app/api/dashboard.py
- app/api/static/premium.css
- tests/js/main_pdf_to_discover.test.cjs
- tests/test_pdf_profile_discovery_e2e.py
- docs/PHASE24_PDF_TO_DISCOVERY_FUNCTIONAL_PROOF.md

Existing unrelated worktree changes were preserved. No Git mutation was performed.
