# Phase24 live notices to preliminary scoring

## Targeted JS contract repair — 2026-10-13

Host evidence supersedes the earlier pending status below: TED public HTTPS
returned five real notices (PUBLIC_LIVE_TED_GATE=VERIFIED). Those real metadata
records were scored against a SYNTHETIC in-memory company profile
(REAL_NOTICE_SYNTHETIC_PROFILE_SCORING=VERIFIED; EVALUATIONS=5), not customer AI
scoring. The four specified Python suites and prior Discovery/Geography/i18n JS
tests passed. UK Find a Tender remains UNAVAILABLE (ConnectorTransportError),
SAM.gov requires an API key, and P3.9 production remains BLOCKED.

The new JS failure at original line 75 concerned `finishJson`, a test-local
resolver assigned only when the actual VM handler enters `response.json()`.
It was not a missing browser export or global function. Two host
`await Promise.resolve()` calls do not establish that the VM's async continuation
has reached JSON parsing. The harness now awaits an explicit JSON-entry signal
and fails if the real discovery handler completes before reaching that point.
It retains the function assertion, deferred JSON completion, company switch,
and all stale-result/health/count assertions. No production defect was proven;
discovery.js and previous passing tests are unchanged.

Only this report and tests/js/main_live_discovery_contract.test.cjs were edited
for the repair. Added assertions check fetched source labels, rendered metadata
labels, partial-failure messaging, exact official HTTPS href preservation, and
escaping of hostile provenance/buyer/number/summary/evidence/missing-data fields.
They execute the existing CommonJS renderer and browser VM handler with
synthetic fixtures and mocked fetch; no network or test-only exports were added.
Node is unavailable in this sandbox (`where.exe node` found no executable), so
the repaired JS runtime validation is HOST PENDING, not PASS. Local
`git diff --check` passed; the untracked repair files were reviewed directly.

## Earlier implementation record

2026-10-13. Implementation delivered; execution verification HOST PENDING.

## Exact files changed in this run

- scripts/phase24_public_sources_live_probe.py
- tests/js/main_live_discovery_contract.test.cjs (new)
- tests/test_phase24_live_to_scoring.py (new)
- docs/PHASE24_LIVE_INTERNATIONAL_DISCOVERY_REPORT.md
- docs/PHASE24_LIVE_TO_SCORING_REPORT.md (new)

No other files written, no Git mutation, no outbound network. Existing uncommitted
changes preserved. No UI defect identified requiring a discovery.js change.

## Working bridge

Existing bounded public catalog -> actual TED/UK adapters -> canonical TenderNotice
-> production prefilter_notice and analysis_from_notice -> production score_tender.
The probe adds aggregate and per-source live_scoring.evaluated_notice_count,
examples (maximum three), profile_is_synthetic:true, full_pdf_analysis:false,
llm_used:false, profile assumptions, fit score/status, completeness, real criterion
statuses, unknown reasons and stop factors. Existing official IDs/URLs are kept.
Every successful-source fetched notice is evaluated even if prefilter rejects it.
Candidate means prefilter candidate only; FILTERED_OUT is never a claimed match.
An empty/failed source is NOT_EVALUATED, count zero, never scoring success.
Programmatic limit/timeout arguments are validated before any fetch.

Benchmark assumptions: SYNTHETIC industrial cable supplier; sell; product/search
keywords cable and cables; EUR; maximum contract value EUR 1,000,000; no declared
region/document/security inventory. This English vocabulary may reject real
foreign-language cable notices. That is honest limited fit, not translated AI.
Scores normalize over scorable criteria; even 100% fit can have low completeness.
No new scoring algorithm, persistence, customer profile lookup or LLM operation.

Actual customer workflow remains explicit PDF preview -> user review/apply -> active
organization company -> scoped Discovery. The new offline integration test uses
existing disposable database helpers, synthetic PDF/provider responses, actual
HTTP adapters with MockTransport, real catalog and application business code.
It checks preview does not apply, reviewed constraints, partial UK failure, category
filtering, known budget versus unknown budget/currency/deadline, unscored documents,
canonical links, active-company switching and tenant/outsider isolation.
JS executes actual discovery.js in a small DOM harness: provenance, escaped title
and official links, unsafe URL rejection, metadata/full-AI distinction, source
health, truthful Dashboard counts, aborted cross-company request and late
cross-organization response suppression. Older passing tests were untouched.

## Evidence before / after

Before (founder supplied host evidence): TED five real notices; sample IDs
704344-2026, 704142-2026, 704352-2026. UK UNAVAILABLE ConnectorTransportError,
no HTTP status; SAM AUTH_REQUIRED. Scoring not evaluated: no profile supplied.
Python live contract six passed; prior PDF/Geography/i18n tests passed. Offline
gate failed solely on missing JS test.
After: code and tests added, no new live response witnessed. No new score for the
previous real notices is asserted. Host must run the bounded probe to establish
actual live_scoring numbers. UK root cause remains undetermined after inspecting
official endpoint/query and bounded transport handling; no proven adapter bug,
TLS bypass, host expansion, retry, scraping or request was introduced.

## Host-pending test matrix

Python and Node command lookup failed in Codex; no runtime passes claimed.
Run with the existing host launchers, no dependency install:

```text
python -m pytest -q tests/test_phase24_live_to_scoring.py tests/test_phase24_live_discovery_contract.py tests/test_pdf_profile_discovery_e2e.py tests/test_pdf_discovery_scoring_monitoring_e2e.py tests/test_organization_workflows.py tests/test_company_profile_pdf.py
node tests/js/main_live_discovery_contract.test.cjs
node tests/js/main_discovery_scoring_monitoring.test.cjs
node tests/js/main_pdf_to_discover.test.cjs
node tests/js/main_pdf_ai_ux.test.cjs
node tests/js/main_geography.test.cjs
node tests/js/main_i18n.test.cjs
```

After offline gates, run exactly one explicitly bounded official public probe:

```text
python scripts/phase24_public_sources_live_probe.py --live --limit 5 --timeout 12 --output PATH
```

PATH is a caller-selected report, not a customer artifact. Policy remains HTTPS
allowlist api.ted.europa.eu / www.find-tender.service.gov.uk, maximum eight dispatches,
2 MiB wire/decoded cap, no redirects/retries, five notices/source, timeout<=12.
Without --live no network is constructed; scoring is NOT_EVALUATED. Partial TED
success can coexist with unavailable UK, which remains visibly failed.

Local git diff --check validation is recorded separately at delivery; runtime and
live gates remain pending until host execution. No live AI or customer DB tests.

## Blockers and next milestone

Host runtime validation and new live benchmark are outstanding. UK independent
verification remains unavailable. P3.9 production resource/cancellation gate is
BLOCKED and unchanged. Next high-value milestone: inspect host benchmark fit and
unknown criteria, then validate one explicitly reviewed active-company Discovery
with an authoritative tender PDF through the existing full document workflow.
Full document AI/RAG/customer onboarding is not proven by a synthetic benchmark.
