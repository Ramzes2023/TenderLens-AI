# VALYQON procurement source readiness — evidence ledger (2026-10-15)

This is **an audit, not an activation/deployment**. A source adapter, a passing mocked test,
a public web page, and an operational customer query are four different kinds of evidence.
Only a real adapter response containing validated notices can count as observed ingestion.
An empty batch or a transport error counts as NOT VERIFIED (not necessarily broken).

## Main: 13 potential registrations, not 13 verified delivery channels

| Region | Source IDs in current main | Catalog status | Live evidence |
| --- | --- | --- | --- |
| Russia | `eis` (44-FZ), `eis_223`, `b2b_center` | Opt-in/configured; 223/B2B registered conditionally | EIS 44/223 RSS -> ephemeral DB -> authenticated metadata scoring observed on operator Windows host; B2B public real-data authenticated scoring GH workflow success. EIS 223 detail pages unresolved. None certifies production delivery. |
| CIS | `kz_goszakup` | Disabled without operator API token | Fixture contracts only in this audit; live tenant ingestion not verified |
| EU | `ted` | Enabled by default | Five real TED notice responses documented from prior host probe; authenticated live customer browser still pending |
| USA | `sam_gov` | Disabled without operator API key | No authenticated live test |
| UK | `uk_fts` | Enabled by default | Prior host probe: ConnectorTransportError, no successful notices |
| Global | `world_bank` | Enabled by default | Current live output not yet verified |
| Canada | `canada_buys` | Enabled by default | Current live output not yet verified |
| Australia | `austender` | Enabled by default | Current live output not yet verified |
| New Zealand | `nz_gets` | Enabled by default | Current live output not yet verified |
| South Africa | `za_etenders` | Enabled by default | Current live output not yet verified |
| India | `india_cppp` | Enabled by default | Current live output not yet verified |

Main's eight default anonymous sources are TED, UK FTS, World Bank, CanadaBuys,
AusTender, New Zealand GETS, South Africa eTenders and India CPPP. Runtime config
can differ. No access to the live customer's source health or production env was used.

## Draft CIS integrations, not yet on main

PR #30: `am_armeps` and `tj_eprocurement` are **disabled by default** in the
proposed catalog. At exact PR SHA `307e0ee1a2cf9d25893960587c831421402d1e06` GitHub
Actions run `38779509059` completed both real HTTPS-to-isolated-SQLite acceptance jobs:
Armenia stored 20 records with 6 snapshot matches; Tajikistan stored 20 with 9
snapshot matches. This proves the bounded public ingestion path on the test runner,
not production activation or complete keyword search and scoring. PR #30 remains
draft and requires further evaluation. PR #32 Moldova and Kyrgyzstan is research
only: no registered production adapter or proven real ingestion.

## Query semantics are not uniform

In `SourceCatalog.fetch(search_terms=...)`, custom source-side term handling
applies to `ted` and configured `eis`/`eis_223`; other default sources return
their bounded canonical recent batch for downstream company filtering. A green
fetch is therefore **not** proof of complete server-side keyword recall.

## Exact gates

- `scripts/ci_public_sources_live_proof.py` is dry-run unless explicitly invoked
  with `--live` in GitHub Actions for this repository's pull requests.
- On a pull request affecting the sources or checker, the isolated workflow
  probes **only the eight anonymous enabled-by-default official sources**.
  No keys, databases, companies, documents, cookies, proxy bypass or AI services
  are used. Current adapters' existing public-IP/TLS/HTTP policy remains in force.
- Each source returns `REAL_NOTICES_NORMALIZED` only for nonempty validated
  `TenderNotice` objects. Empty, invalid, failed or timed-out results do not pass.
  The workflow requires all eight; a partial result intentionally stays red.
- Successful live CI proves only a small current source batch (at most three records
  per adapter), not durable persistence, tenant-scoped Discovery, delivery latency,
  detail URL reachability, pagination, full-market coverage, AI or 24/7 SLA.
- CI always uses temporary runners. Existing main, production env, AWS,
  migrations, tokens and customer databases are untouched.
- Never merge or enable unverified adapters just to increase an advertised count.

Historical supporting evidence: `docs/PHASE24_LIVE_INTERNATIONAL_DISCOVERY_REPORT.md`,
`docs/PHASE24_LIVE_TO_SCORING_REPORT.md`, PRs #24/#27/#31/#34, and CIS draft PR #30.
