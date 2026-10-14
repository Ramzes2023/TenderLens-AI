# RU-09 EIS acquisition diagnosis

Scope: EIS 44-FZ and 223-FZ only, following RU-08 commit
`3396e0552dfc3675dc72a2714084b5f8b06e5f9d` (reported baseline: 2218
passes, 3 legacy migration tests deselected). Production adapters and shared
transport remain unchanged. No pytest, Python live run, commit, production DB,
settings loader, `.env`, or network probe was executed by Codex.

## Cause of the host/application mismatch

Both adapters call `source_client(..., trust_env=True, verify=True)`. HTTPX
environment proxy selection is retained, including NO_PROXY routing, but
`app/sources/http.py::_PublicIPClient._init_proxy_transport` deliberately returns
`_RejectedProxyTransport`. Any selected proxy route raises non-retryable
`ConnectorTransportError` before TCP or an HTTP response. This is intentional
proxy safety, not a broken RSS parser. Both LiveClient and BoundedClient inherit
this behavior. A host client using the configured proxy can receive XML while
the application fails closed on that route. The exact host application's route
is still to be measured by the new smoke; system proxy configuration alone does
not establish that HTTPX selected an environment proxy.

RU-08 `local_catalog` wraps the adapters in `LocalBoundedSource`, then invokes
SourceCatalog -> SourceRegistry -> MultiSourceFetcher -> adapter -> BoundedClient.
The wrapper allows one request to `zakupki.gov.ru`, 5 MiB, 15-second request
timeout and 25-second total timeout. BoundedClient disables redirects regardless
of the 44 adapter's requested `follow_redirects=True`. It classifies 408, 429,
and 5xx as retryable; proxy denial and other non-2xx are non-retryable. Neither
adapter nor MultiSourceFetcher retries. MultiSourceFetcher records the exception
type and deduplicates `(source, external_id)` without cross-law deduplication.
The 44 adapter preserves ConnectorTransportError because it is not an HTTPError
or OSError; the 223 adapter explicitly rethrows it.

44 uses `https://zakupki.gov.ru/epz/order/extendedsearch/rss.html` with
`searchString=поставка&morphology=on&pageNumber=1&fz44=on`; 223 uses the same path
with `fz223=on` and no `fz44`. The host sample request had **no law filter**.
Query selection is distinct; independent live law coverage remains unproven.
The 223 adapter already retains requested and observed law separately and leaves
`independently_verified_law=None`, even if fed a 44 record. Source identity does
not prove legal classification.

No adapter patch is justified by this evidence. Changing trust_env, enabling
proxies, disabling TLS, or bypassing public-IP checks would change safety rather
than fix a parser defect. SSRF/public-IP checks, host allowlists, credentials,
timeouts, byte limits and existing DTD/entity controls are untouched. EIS223
remains default OFF; smoke opt-in exists only in an in-memory registry.

## Exact evidence and status

User-host capture, 2026-10-14: HTTP 200, `application/rss+xml;charset=UTF-8`, RSS
root, 200 items, titles and links present. External file:
`C:\Users\ramze\AppData\Local\Temp\VALYQON_RU09_EIS_20261014_114022\eis_44_host_rss.xml`.
Read-only inspection found 482226 bytes, SHA-256
`cc4be75c896254c5be65d5eca9dfc9d767deb543f7bceb57aa49a98156b86008`.
All 200 item links use the official `/223/purchase/public/purchase/` route and
all 200 descriptions contain result-level `Размещение выполняется по: 223-ФЗ`.
There are zero `/epz/order/notice/` item links. The search-form metadata says
`223-ФЗ и 44-ФЗ`, which is not result classification. The sample's “44” filename
does not establish 44-FZ content. Original bytes remain external TEMP.

| Source | Known application result | RU-09 live status |
| --- | --- | --- |
| eis_44fz / eis | Previous smoke: ConnectorTransportError; supplied unfiltered capture has no 44 notices | Pending host runner; no verified live adapter or E2E result |
| eis_223fz / eis_223 | Previous smoke: ConnectorTransportError; external unfiltered capture contains 223 notices, not a verified fz223 request | Pending host runner; offline content only |

RU-09 focused tests and live smoke have **not run yet**. No new pass count or
live status is claimed. Host results must come from the generated JSON, not
HTTP 200 alone. AI query remains unverified.

## Host runner commands

Run outside the Codex sandbox with the project's existing Python environment.
Use a fresh output filename and a workdir beneath HOST TEMP:

```powershell
$env:RU09_EIS_EVIDENCE = "$env:TEMP\VALYQON_RU09_EIS_20261014_114022\eis_44_host_rss.xml"
python -B -m pytest -q tests/test_ru09_eis_diagnostics.py tests/test_eis_223_rss.py tests/test_eis_223_persistence_contract.py tests/test_eis_business_metadata.py
python -B tests/ru09_eis_live_smoke.py --output "$env:TEMP\ru09-eis-live-result.json" --workdir "$env:TEMP\ru09-eis-host-work" --evidence "$env:RU09_EIS_EVIDENCE"
```

The evidence environment variable is only an optional external-file pointer,
not a persistent source flag. Omit it to skip the captured-byte test. Other
tests use explicitly synthetic XML and the production shared client with
MockTransport; their E2E branch assertions are not live evidence. Tests pin the
supplied capture hash and exact 223-only classification, rather than weakening
assertions for an unrelated capture. The executable script exposes the required
`--output`, `--workdir`, and optional `--evidence` arguments.

The smoke makes at most two sequential existing adapter GETs, exclusively the
existing EIS public host. It observes client route type, response status and
parser input without bypassing transport policies. Exception messages, proxy
objects, environment contents, URLs with credentials, and response bodies are
never printed. HTTP=null means no response was observed, not HTTP 200. Import
and runtime failures yield BLOCKED with safe exception types. The optional
external capture is analyzed separately and never substituted for live fetches.

Each source has exactly `state`, `real_records`, `database_upserts`,
`query_matches`, `reason`, `endpoint_host`, and `law_verified`; safe HTTP/proxy
details are in top-level diagnostics. `real_records` counts normalized live
fetches; `correct_law_records` separately counts notices eligible for E2E proof.
Law verification requires agreement between an explicit result-level law label
and the official notice detail route plus registration number. Missing or
contradictory evidence cannot promote a source. This is feed-record law proof,
not separate detail-page acquisition or legal certification.

Only correctly classified, genuinely fetched notices enter a fresh random
temporary SQLite database. Existing OpportunityRepository initialization creates
only the existing isolated opportunity/observation schemas. Existing
`save_and_query` verifies exact identities AND URLs through snapshot_catalog
keyword queries. LIVE_E2E_VERIFIED requires successful upsert/query for all
eligible correct-law records (at least one); wrong-law fetched records are
counted separately and not saved. Partial storage/query outcomes remain
LIVE_FETCH_ONLY. Temporary DB cleanup is automatic. No production DB or
configured source flag is opened or changed.

## Follow-up

Have the host runner execute focused tests and smoke and retain its JSON in
TEMP. If proxy_route_rejected=true and HTTP=null, the mismatch is confirmed for
that process. If false, investigate the reported HTTP/exception outcome rather
than assuming proxy use. An approved direct route or separately reviewed secure
proxy transport is future infrastructure work outside RU-09; do not silently
unset proxy variables to force a successful result. The unfiltered capture can
verify offline parsing but cannot establish either configured live law feed.
No authenticated UI, user AI path, LLM retrieval, profile scoring, production
ingestion, or persistent enablement was exercised. A host runner may commit only
the new RU-09 files after its checks pass; no push/merge/deploy is authorized.
