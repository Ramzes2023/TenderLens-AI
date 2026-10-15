# RU-08 six Russian sources: integration audit

Scope: isolated `parallel-sources-audit-20261013`, base `545aac5be5d08289bea875691ef9124d0d0b74d7`. No live requests, pytest, commit, runtime settings loader, production database, or production enablement were executed by Codex. This is not six-source readiness. Zero new live adapters meet the supplied evidence threshold.

## Captured evidence and status

Authoritative capture: `VALYQON_RU08_SIX_20261013_220933/public_access_manifest.json`. The fixture copy preserves the original manifest, including its original unvalidated status and host paths. Only one response body exists. The manifest's zero counts are capture-time values, not evidence that platforms contain no tenders.

| Source / internal key | Status and exact endpoint | Captured evidence count | Obstacle / permission | Local test enablement |
| --- | --- | --- | --- | --- |
| EIS 44-FZ / `eis` | Existing connector; live proof pending. `https://zakupki.gov.ru/epz/order/extendedsearch/rss.html?searchString=%D0%BF%D0%BE%D1%81%D1%82%D0%B0%D0%B2%D0%BA%D0%B0&morphology=on&pageNumber=1&fz44=on` | 0 supplied bodies | Host smoke must retrieve genuine notices; RSS filter is not independent law verification | `local_catalog()`; one public GET only |
| EIS 223-FZ / `eis_223` | Existing opt-in connector; live proof pending. Same RSS endpoint and query, with `fz223=on` instead of `fz44=on` | 0 supplied bodies | Default OFF; no fabricated EIS positive fixtures | `local_catalog(enable_eis223=True)` only; no persistent env flag |
| B2B-Center / `b2b_center` | Existing opt-in connector. Captured `https://www.b2b-center.ru/search/` supports parser contract; live E2E pending | 10 manually inspected structured cards / IDs / direct aggregate detail URLs; parser tests unexecuted | Public anonymous body is not a login/captcha wall. A recaptcha script reference is present, but actual procurement cards are present. No permission to bypass a later denial. Aggregated coverage is not automatically unique | `local_catalog(enable_b2b=True)` only |
| TEK-Torg / `tektorg` | OFFLINE_ONLY; `https://www.tektorg.ru/` capture reports HTTP 307 | 0; no saved body | Redirect target/contract unverified. Secure existing offline XML parser unchanged; not connected live | No live flag; disabled diagnostic registration |
| Roseltorg / `roseltorg` | BLOCKED; `https://www.roseltorg.ru/procedures/search`, `https://www.roseltorg.ru/torgi` | 0; no saved bodies | Both timed out. Repeated records, IDs, detail URLs and reproducible permitted acquisition unverified. Not connected | No live flag; disabled diagnostic registration |
| Fabrikant / `fabrikant` | BLOCKED; `https://www.fabrikant.ru/procedure/search`, `https://bonus.fabrikant.ru/procedure/catalog/` | 0; no saved bodies | Both timed out. Human-readable indexed cards alone do not establish acquisition from this host. JS/network cause unknown. Not connected | No live flag; disabled diagnostic registration |

B2B original host response SHA-256: `b5ec85c85e9a29ff2fd02a6815adbdcdc61ca2155d34fb8c18e057325d945aa7`, 246338 bytes (retained in the capture manifest). The Git-committed UTF-8 fixture contains normalized line endings and is 243045 bytes, SHA-256 `1f937626a85fffdb99de5bb7db10fc99a5a6a41407cc53a53e04c35c0565fc7d`. It is **not byte-for-byte identical** to the host capture. Offline tests pin the checked-in canonical bytes separately and continue to accept the original raw digest; neither variant proves live acquisition. Inspected IDs: `l15290024-3-9-1`, `l15290025-3-9-1`, `l15290023-3-9-1`, `l0338200012226000019-1`, `l0348200072726000025-1`, `l4639392-4-12-1`, `l0358100010326000043-1`, `l15290021-3-9-1`, `l15290020-3-9-1`, `l15290018-3-9-1`. Direct URLs are `https://www.b2b-center.ru/search/number/<ID>/`; they are observed links, not separately fetched detail pages.

Three cards explicitly reference EIS `regNumber`: `0338200012226000019`, `0348200072726000025`, `0358100010326000043`. These are aggregate EIS references, not three new unique tenders. No EIS counterpart was retrieved here. Seven other cards have unknown cross-platform uniqueness. The adapter retains upstream URLs in provenance and summary. RU-08 diagnostics group explicit EIS numbers and report cross-source links only when both notices exist; they do not collapse uncertain matches or write duplicate links to production tables.

## Technical gap table

| Source | Catalog / registry / multi-fetch | Ingestion and local SQLite / PostgreSQL boundary | Existing user query and scoring gap |
| --- | --- | --- | --- |
| EIS 44 | Production catalog key `eis`; profile terms generate RSS feeds. RU-08 uses one fixed public feed | Existing ingestion needs static URLs for shared sync; EIS hosts already allowlisted; `OpportunityRepository` stores source/external ID and connector version, including observations | Snapshot query uses the same repository; genuine live fetch→upsert→query remains host verification work |
| EIS 223 | Registration exists only when enabled AND feed configured; normal defaults OFF | Existing ingestion host and version support present; RU-08 in-memory opt-in supplies static URL | Snapshot search and scoring already support key; scoring enqueue requires enabled catalog; live proof absent |
| B2B | Registration exists only with opt-in; normal default OFF | Existing bounded HTML connector and ingestion route present; provenance survives storage | Snapshot query and scoring already support key; captured-record roundtrip test added but unexecuted |
| TEK | Offline parser is not a live catalog registration | No verified live acquisition or central worker host policy | No live indexed notices; source absent from scoring allowlist |
| Roseltorg | No verified adapter; RU-08 disabled diagnostic only | Need verified listing contract, secure parsing, source host policy and ingest registration before live implementation | No indexed notices; source absent from scoring allowlist |
| Fabrikant | No verified adapter; RU-08 disabled diagnostic only | Same acquisition gaps plus explicit EIS duplicate provenance | No indexed notices; source absent from scoring allowlist |

Architecture: `SourceCatalog` owns `SourceRegistry` and `MultiSourceFetcher`; multi-fetch deduplicates `(source, external_id)` and balances results, without cross-platform dedup. `ConnectorSyncHandler` validates registered enablement, bounded transport, normalized notices and provenance before repository writes. `OpportunityRepository` uses the existing Database backend and existing migrations for SQLite/PostgreSQL, with idempotent source/external ID storage. No migrations were added or modified. PostgreSQL behavior is inspected, not executed.

The existing discovery route in `app/api/organization_workflow_routes.py` selects `snapshot_catalog` in snapshot mode and passes that catalog into profile discovery. RU-08 verifies the underlying catalog keyword query path, not authenticated HTTP, profile matching, AI output or LLM retrieval. `ScoringRunService` reads indexed `source_opportunities`, freezes revisions and applies private profile keywords; it currently permits at most five source selections. A future genuinely connected six-source scoring selection needs a bounded capacity/allowlist review (including handler scan limits); RU-08 does not widen production scoring for three unavailable platforms.

## Engineering and host validation contract

`app/sources/ru08_integration.py` builds exactly six Russian diagnostic registrations without calling `build_source_catalog` (which also constructs international sources and reads credential environment variables). Only the three existing supported connectors can run. Its wrapper applies exact hosts, one request per connector, 5 MiB wire/decoded transport bounds, existing public-IP protection, 15-second request timeout, 25-second overall timeout and no redirects, retries, pagination, scripts, detail fetching or external upstream GETs. Production sources, defaults and central shared files are untouched.

`tests/test_ru08_integration.py` validates captured B2B parsing, exact IDs and URLs, retained provenance, idempotent storage and exact notice identity/URL returned through the existing snapshot query; existing ingestion routing and opt-ins; disabled unavailable platforms; host/credential URL denial; synthetic login/captcha/bot/empty pages; synthetic external-link corruption; and explicit synthetic duplicate linking. Large response bytes are read inside tests, never pytest parameters. Captured-response roundtrip is not live proof. All tests await the host runner; Codex did not run them.

Optional host-only invocation, using a new output file and a child of the OS temporary directory:

```powershell
python -B tests/ru08_six_live_smoke.py --output "$env:TEMP\ru08-result.json" --workdir "$env:TEMP\ru08-host-work"
```

Running the smoke explicitly enables EIS223 and B2B only in its in-memory catalog. It makes up to three sequential anonymous public GETs (one-second spacing), exclusively `zakupki.gov.ru` and `www.b2b-center.ru`. It never probes the three unverified platforms. Denial, redirects, malformed responses or empty results yield BLOCKED, not synthetic success. Dependency failures yield NOT_AVAILABLE. It creates a random temporary child database, initializes only existing opportunity/observation schemas, and never opens a configured/customer DB or `.env`. Output refuses overwrite and uses the exact required top-level/source-entry JSON fields.

`LIVE_E2E_VERIFIED` requires every genuinely fetched normalized notice to be upserted and the same identity AND actual detail URL to be returned through `snapshot_catalog.fetch(..., search_terms=(external_id,))`. `database_upserts` counts successful repository calls, not unique coverage; fresh DB prevents prior evidence reuse. `LIVE_FETCH_ONLY` retains honest partial storage/query counters. Explicit EIS references/cross-source links are included in the note. `ai_query_verified` stays false because AI/LLM APIs and authenticated UI are not tested. No state claims independent legal classification, new unique coverage, or full six-source readiness.
