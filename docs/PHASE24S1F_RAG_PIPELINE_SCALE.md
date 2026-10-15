# Phase 24S.1F — durable RAG ingestion

Scope: PDF RAG ingestion and interactive retrieval only. Production untouched;
no deployment, commit, package installation, Docker startup, or real service call.
Starting branch `phase24-professional-saas-core`, clean worktree, HEAD
`4c2fd64ce6da906db2c4ec771452cd3ed60d666e` verified before editing.

## Audit of the starting implementation

- `app/rag/config.py`: defaults to FastEmbed's
  `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, optional GigaChat
  `Embeddings-2`; local Qdrant at `data/qdrant`, fixed operator-configured
  collection. Chunk size 1200, overlap 180, top-k 5 (configuration 1–10), context
  7000 characters (configuration 1000–20000). Collection names are validated by
  configuration, never supplied by the customer.
- `embedding.py`: synchronous `embed_many` / query `embed`, vector count,
  dimensions and finite-value validation. FastEmbed initializes/downloads a
  model at construction if absent; E5 models use passage/query prefixes.
  GigaChat uses the existing SDK with TLS verification, timeout and SDK retries
  disabled. Previously every GigaChat failure became an undifferentiated
  `EmbeddingError`. Embeddings have no Redis cache.
- `app/parsers/pdf.py`: existing PyMuPDF parser, no OCR; 10 MiB bytes, 200 pages,
  2,000,000 extracted characters, encrypted/corrupt/empty-document statuses.
  Native diagnostics are suppressed. `app/services/pdf.py` runs the existing
  `app.parsers.pdf_worker` subprocess with 30-second timeout and no parser stderr.
  It uses bounded in-process bytes/subprocess streams, not persistent staging.
- `chunking.py`: deterministic whitespace normalization, page-local chunks,
  natural-boundary cuts and character overlap; ordered zero-based chunk indices,
  one-based page numbers. No LLM chunking, OCR, or multi-page chunk ranges.
- `service.py`: synchronous indexing embeds the entire chunk list in one call,
  then invokes `replace_document`. Retrieval embeds only the question and filters
  the specified owner/document. Answering offloads retrieval with `to_thread`,
  builds bounded grounded context and uses the unchanged prompt through
  `generate_operation(..., RAG_ANSWER, ..., max_tokens=700)` (`rag-answer:1`).
  The existing context selection may include its first block even when that
  block exceeds the configured target; its chunk-size bound remains unchanged.
- `qdrant_store.py`: Qdrant **local embedded mode**, opens/closes a client for
  each operation. Schema ensures cosine vectors and rejects dimension mismatch.
  Replacement deletes the owner/hash slice and upserts all chunks together.
  Old IDs are UUID5(URL namespace, `tenderlens:{owner}:{sha256}:{chunk_index}`).
  Old payload: owner ID, PDF SHA-256, chunk index, page number, chunk text.
  `has_document` scrolls for just one point, so it is not a completion manifest.
- `app/rag/store.py` / migration 6 retain a legacy relational vector store and
  `rag_chunks` with text/vector blobs. The active `RagService` defaults to
  Qdrant; the new ingestion handler neither invokes that legacy store nor writes
  text/embeddings into SQL. It is not a second vector backend for this phase.
- `app/tenancy.py`: organization compatibility namespace is
  `8_000_000_000_000 + organization_id`, distinct from legacy owners. Existing
  organization RAG filters are organization-wide, without company scope.
- `app/api/routes.py`: `/api/v1/analysis/pdf` performs extraction, AI analysis,
  scoring, history and synchronous indexing via `to_thread`.
  `/api/v1/rag/ask` retrieves interactively. Organization equivalents in
  `organization_data_routes.py` save/revalidate authorized history before indexing
  and recheck membership before returning answers. The old PDF response includes
  optional `rag_indexed_chunks` and warnings; those contracts remain unchanged.
- Company profile PDF preview/apply routes in `organization_company_routes.py`
  extract bounded PDFs and generate a company profile; they are not RAG ingestion.
  Their dashboard preview/apply flow is unchanged. Existing frontend/history
  flows remain on their existing synchronous contracts; no UI polling migration
  is required to preserve them. The new API is explicitly available to clients.
- `app/bot/documents.py`: downloads into `LimitedBuffer`, synchronously indexes
  off the bot event loop after analysis, or reconstructs a missing index from a
  re-upload. `app/bot/rag.py` asks about the latest history document interactively.
  No raw PDFs were retained by these history flows, and no safe reusable
  persistent raw-PDF document store was found.
- `app/jobs`: migration 9 provides durable jobs, account/org/company scope,
  small bounded JSON, scoped lookup, scoped SHA-256 idempotency, atomic claims,
  heartbeats, deterministic bounded retry backoff, expiration recovery and
  token/time-fenced completion/failure. Handlers must be synchronous callables.
  Registry is explicit and frozen on pool startup. Before this phase the CLI
  refused all work because no production handler existed; no public status API.
  Generic stored failure codes contain neither messages nor tracebacks.
- Migration framework is ordered/checksummed, SQLite and PostgreSQL capable.
  The durable jobs table already supplies reliable persisted completion state;
  no additional table or migration is necessary.
- `ApiRuntime` owns configured DB/cache, does not start job workers. AI composition
  is CachedAI over the provider-neutral gateway, GigaChat primary with optional
  Groq availability failover. Embeddings are separate from generation failover.
- Docker API/bot share `tenderlens_data:/app/data`; bot uses `qdrant-bot` because
  embedded Qdrant forbids concurrent opens. There was no worker service. Data
  directories are ignored by Git; existing security guidance excludes customer
  bodies and credentials from logs. Requirements already include PyMuPDF,
  qdrant-client/FastEmbed, GigaChat/httpx, SQLite/PostgreSQL support; no additions.
- Starting tests include `test_rag.py` (chunking/config, fake providers, local
  Qdrant/retrieval/citations), organization PDF/RAG authorization/revocation,
  PDF parser bounds and durable job claim/retry/fencing/migration tests.

## New architecture and application contract

```
authorized PDF upload -> atomic persistent staging -> rag.ingest.v1 durable job
explicit worker -> isolated PDF parser -> deterministic bounded chunks
                -> sequential bounded embedding batches -> idempotent Qdrant upsert
                -> lease-fenced durable job success = complete/ready

question -> scoped successful job lookup -> query embedding -> scoped retrieval
         -> existing grounded prompt -> existing provider-neutral AI generation
```

Canonical upload: `POST /api/v1/organizations/{organization_id}/rag/documents`,
multipart `file`, response **202**. Company-scoped counterpart:
`POST /api/v1/organizations/{organization_id}/companies/{company_id}/rag/documents`.
The authenticated session resolves the account; existing membership/company
services resolve authorization. A customer-supplied organization ID alone grants
no access. Writers must be owner/admin/member. Original filenames are ignored.
The upload only reads at most 10 MiB + 1, validates/stages and enqueues; no parser,
Qdrant operation, embedding or generation runs in this route.

Status: `GET .../rag/jobs/{job_id}` under the same organization/company prefix.
Response is `{job_id, document_ref, state, ready, result, failure_code}`; `result`
is null until succeeded. No payload, SHA, tokens, leases, filesystem paths,
tracebacks, PDFs, text or vectors are exposed. Lookups require **exact** account,
organization and company scope. Membership/company access is checked again
before responses. Wrong owner/company returns 404; unauthorized org returns 403.
Responses use `Cache-Control: no-store`.

Question: `POST .../rag/jobs/{job_id}/ask`, body `{question}` (1–2000 chars),
returns existing `{answer, sources:[{page_number,chunk_index,score}]}`.
Unfinished/failed/cancelled ingestion returns **409**. A historical generation
whose pipeline differs from current query settings also returns 409; re-upload
under the new configuration rather than querying with incompatible embeddings.
Membership is rechecked after generation. Questions are never queued.

Compatibility `/api/v1/analysis/pdf`, organization `/analysis/pdf`, old `/rag/ask`
and Telegram upload/ask remain synchronous. They preserve combined analysis,
scoring, history, frontend readiness contracts and old vector namespaces. The
new API is the canonical durable indexing path and indexes independently of AI
tender analysis. It does not invent history records or replacement semantics.
New vectors lack the old `owner_user_id` field, so old retrieval cannot accidentally
read new partial generations. Existing company-profile PDF flows are unchanged.

## Staging, identity and path policy

`RagDocumentStore` defaults to `DATA_DIR/rag-documents` (`project/data` fallback).
`VALYQON_RAG_DOCUMENT_DIR` is an optional **operator-only** override, shared by API
and worker. Relative configured paths resolve against the project, not customer
input. Root symlink/junction components are rejected. Customers supply no paths.

Files are `<opaque-reference>.pdf`; the reference is exactly 64 lowercase hex
characters. Traversal, absolute paths, malformed references, symlinks, junctions
and resolved-root escapes are rejected. Reads use regular-file/size and inode
checks, and POSIX `O_NOFOLLOW` where available; Windows uses lstat/fstat checks
under a trusted directory. The directory and its parents must be writable only
by trusted operators/application identities. This is not protection against an
administrator maliciously replacing trusted parent directories mid-operation.

Stage rejects empty/magic-invalid/oversized bytes, hashes SHA-256, writes a
server-created temporary file in that same directory, flushes/fsyncs it, then
atomically replaces the destination. Concurrent identical stages write identical
bytes. Existing files are bounded-read and fingerprint checked. Worker reads
rehash before extraction. Safe explicit single-file deletion exists for future
operator use; there is no customer delete API and no recursive deletion.

All JSON identities below use UTF-8 and compact separators `(',', ':')`:

- Content identity `D = SHA256(pdf_bytes).hexdigest()`.
- Scope `S = [account_id, organization_id, company_id_or_null]`.
- Embedding identity `[provider, model, "embedding-adapter-v1"]`, no credentials.
- Stable material version `rag-ingest-v1` covers current parser, chunking and
  vector payload revision. Effective pipeline `P = "rag-ingest-v1:" + SHA256(JSON([
  "rag-ingest-v1", embedding_identity, chunk_size, chunk_overlap,
  qdrant_collection, "page-payload-v1"])).hexdigest()`.
- Opaque document reference `R = SHA256(JSON([S,D,P])).hexdigest()`.
- Enqueue key `D + ":" + P`; the existing queue computes
  `SHA256(JSON(["rag.ingest.v1",S,enqueue_key])).hexdigest()`.
- Vector scope `V = SHA256(JSON(S)).hexdigest()`.
- Vector point ID is `UUID(bytes=SHA256(JSON([V,D,P,chunk_index])).digest()[:16])`.

Content hash, reference, scope and pipeline are separate fields/concepts. No
Python hash(), timestamp/random version, customer names or email in storage keys.
Account scope is intentionally stricter than the legacy organization-wide index:
another org member has no access to the uploader's new jobs/vectors. Identical
bytes in other accounts, organizations or companies get separate references,
jobs and vector IDs. Physical dedup is only within the identical authorized scope.

Changing embedding model/provider/adapter revision, chunk configuration or
collection changes P and permits a new indexed generation. Bump the material
version when extraction/chunking/payload semantics change; model weights changing
under the same model name also require an operator-controlled revision bump.
Old queued versions fail permanently on a differently configured worker; drain
old work before upgrades or explicitly enqueue the current version. No
destructive automatic replacement/deletion of old generations is introduced.

## Job, manifest, execution and retry semantics

Approved job type **`rag.ingest.v1`**, exact payload:

```json
{"schema":1,"document_ref":"<R>","sha256":"<D>","pipeline_version":"<P>"}
```

Tenant scope lives in durable job columns. Payload excludes PDF/base64, filenames,
extracted text, chunks, vectors, credentials and authorization tokens. The handler
rejects extra fields, wrong schema/types/version, invalid hash, scope/ref mismatch,
tampered file, inactive account, revoked/downgraded membership and foreign company.

Small successful result:

```json
{"schema":1,"document_ref":"<R>","status":"complete","chunk_count":12,"vector_count":12,"pipeline_version":"<P>"}
```

The durable jobs row is the minimal persistent manifest: queued = staged, running
= indexing, succeeded = complete, failed/cancelled = unavailable. Only existing
lease-fenced completion writes success/result. Its partial unique index collapses
queued/running/succeeded identities; same-scope COMPLETE re-upload returns the
same succeeded job without re-embedding/upsert. Failure/cancellation releases the
active identity for an explicit re-enqueue. Completion is never inferred from one
point or from `has_document`. No migration added; migration 9 and all existing
checksums unchanged, SQLite/PostgreSQL SQL queue behavior preserved.

`RagIngestionHandler` is an explicit synchronous callable registered only by the
opt-in CLI. It runs the current isolated parser with synchronous `subprocess.run`
and a 30-second timeout. It creates no asyncio loop, calls no `asyncio.run`, and
does not nest web loops. API enqueue/lookup run via `to_thread`; worker pool threads
own ingestion execution and heartbeats. Tests also exercise the adapter from a
caller with a running event loop.

Existing extraction bounds remain 10 MiB / 200 pages / 2 million characters.
Encrypted/corrupt/unsupported/empty or timed-out extraction is permanent. The
worker adds a 20,000-chunk hard stop during chunk construction, protecting extreme
overlap settings before embedding work. Accepted chunk normalization, ordering,
cuts, overlap and page citation semantics are unchanged. No OCR/new parser.

`VALYQON_RAG_EMBED_BATCH_SIZE` defaults to 16, strict range 1–64. Each job embeds
one batch at a time, validates finite vectors/counts/consistent dimensions and
upserts that batch with deterministic IDs. No per-chunk concurrent fan-out; job
concurrency is bounded by the existing worker pool. Stop/lease-loss is checked
before embedding and again before each upsert. Memory holds only the bounded
parser/chunk output and a batch of embeddings, not all document embeddings.

New Qdrant payload: `ingestion_scope`, `pdf_sha256`, `pipeline_version`,
`document_ref`, `chunk_index`, `page_number`, `chunk_text`. Collection names are
operator controlled. Schema ensures cosine/dimensions. New indexing never deletes
a scope/document slice: retries overwrite the same deterministic point IDs.
Retrieval filters **V AND D AND P**; it returns no vectors, preserves top-k (1–10),
context policy, source page/chunk metadata and grounded prompt.

At-least-once execution is intentional. A batch may commit before its acknowledgment
fails; retries rebuild and overwrite all batches without increasing point count.
An expired worker may still write identical-generation IDs; vector writes are not
transactionally fenced with SQL. SQL stale completion/failure remains rejected,
and only the authorized successful generation is served through the new API.
Physical partial batches exist in Qdrant; there is **no distributed atomic vector
visibility or exactly-once claim**. Direct operator Qdrant reads can see them.

| Failure | Policy | Persisted code |
|---|---|---|
| Embedding timeout/network/TLS, SDK HTTP 429/500/502/503/504 | Retry, bounded existing backoff/attempts | `handler_error` |
| Temporary Qdrant/open/lock/upsert unavailable | Retry | `handler_error` |
| Malformed/encrypted/empty/unsupported/oversized PDF, extraction timeout, integrity/ref/payload violation | Permanent | `permanent_failure` |
| Inactive account, revoked/downgraded membership, invalid scope/company | Permanent | `permanent_failure` |
| Authentication/authorization rejection, other deterministic provider errors, invalid vector payload/local model/configuration | Permanent | `permanent_failure` |
| Missing vector dependency, dimension/named-vector/schema mismatch | Permanent | `permanent_failure` |
| Lease expired | Existing recovery/replay or exhausted terminal failure | `lease_expired` |

Unexpected errors retain the existing fail-closed worker `handler_error` policy;
messages are never persisted. GigaChat mapping reads only numeric SDK status,
never raw response bodies. No document text/secrets in job failures or logs.
No embeddings/text SQL storage or Redis embedding cache is added.

## Worker startup and deployment prerequisites

Exact explicit command: **`python -m app.jobs.worker --rag`**.
No argument/unknown arguments refuse with exit 2. Disabled/invalid configuration,
unavailable model/store/dependencies or startup failure return a safe startup
message/exit 2. Fixed imports and fixed registry entry only; no eval, exec,
dynamic handler imports, web-lifespan worker or automatically started worker service.
SIGINT/SIGTERM trigger the existing bounded pool shutdown; DB is not closed under
a handler still running after the shutdown budget.

Operators must provision the same relational DB, effective RAG settings,
document directory and Qdrant index for API/worker. Mount `DATA_DIR`/staging into
both processes; the existing `/app/data` Docker volume convention accommodates
this. No compose worker service is auto-enabled by this change. Pre-provision
FastEmbed's model cache before an offline worker startup; optional GigaChat
configuration belongs to the existing secure operator setup, not jobs/examples.

Local embedded Qdrant remains the only active backend. A bounded 30-second
cross-process advisory lock (`msvcrt` on Windows / `fcntl` on POSIX), around every
short client open/use/close, serializes API/worker operations. Embedding happens
outside that lock. All processes sharing the index must run this locking code;
old binaries/bot deployments must not concurrently open the same directory.
Bot's separate index convention is unchanged. Use a filesystem with reliable
advisory locking; arbitrary multi-host/network-filesystem Qdrant deployments are
not validated. Local writes/retrieval serialize, so this is a durable worker and
bounded-work foundation, not a claim of unrestricted vector-store throughput.
No Qdrant server URL/backend is introduced or tested.

Staged PDFs are retained through retries and success (future citation/download
needs); no public PDF download is added. No retention cleaner. Failed enqueue may
leave an orphaned staged file. Operators own coordinated maintenance; never delete
files used by live jobs. Back up/restore durable jobs, staging and Qdrant together.
The reliable COMPLETE reuse assumes retained vector data; removing/restoring an
index independently can invalidate that assumption. Use a new collection/pipeline
generation for controlled reindex after data loss. No automatic repair/garbage
collector is included. Storage-directory access/backup protection is required
because PDFs and vector payload text are sensitive customer data.

## Generation boundary and phase limits

The answer prompt and `rag-answer:1` operation are unchanged. Query embedding is
latency-oriented and not queued. Final generation still calls the existing AI
Gateway/CachedAI composition: exact AI cache policy, GigaChat primary and opt-in
Groq failover remain intact. Embeddings do not use that generation failover or
Redis. Fallback was disabled throughout validation. No live credentials sought,
reconstructed, requested or printed; only examples and synthetic fixtures.

24S.1G connector workers, scoring separation, quotas, observability, 24S.2
monitoring matcher and Phase 25+ are untouched. This approved handler demonstrates
the durable worker extension point; it does not register connector jobs.

## Offline validation

`scripts/validate_rag_pipeline.py` forces `VALYQON_EMAIL_MODE=disabled` and
`VALYQON_AI_FALLBACK_ENABLED=false`, then reuses the existing socket/DNS guard.
It requires explicit `tests/test_*.py` files, never defaults to a full suite.
Only loopback needed for Windows asyncio/TestClient is allowed by the guard;
all provider/DB-server/cache-server calls are mocked. Qdrant exercises use only
embedded temporary-directory mode and deterministic fake embeddings.

New tests cover persisted staging/enqueue, cross-instance worker-readable PDFs,
safe payload/results, same-scope complete reuse, bounded batches/chunks,
transient embeddings and partial vector writes/retry without duplicates, expired
lease replay and stale completion rejection, invalid/encrypted/empty PDF,
integrity/path/size violations, symlink policy, provider HTTP failure taxonomy,
invalid vectors/config, production CLI registration/execution under controlled
fixtures, local Qdrant idempotency/locking, account/org/company isolation,
session-authenticated real API enqueue/status/ask, readiness gating, citations,
same bytes with renamed filename, CSRF, and no event-loop ownership hacks.

Final focused run: **246 passed, 1 skipped, exit 0** (128.59 seconds).
New ingestion file separately: **36 passed, 1 skipped, exit 0**. The skip is the
real Windows symlink fixture because creation privilege is unavailable; a separate
privilege-independent symlink-policy test passes. One existing Starlette/httpx
deprecation warning was emitted; no dependency was changed or installed.

Exact guarded command (use the configured local Python executable):

```text
python scripts/validate_rag_pipeline.py tests/test_rag_ingestion.py tests/test_rag.py tests/test_organization_pdf_rag.py tests/test_jobs.py tests/test_pdf.py tests/test_api.py tests/test_organization_data.py tests/test_organization_companies.py tests/test_database.py tests/test_postgresql_foundation.py tests/test_phase17_security_hardening.py tests/test_session_access.py tests/test_company_profile_pdf.py tests/test_organization_api.py
```

Compile **exit 0**, whitespace check **exit 0**. Compile:
`python -m compileall -q app tests scripts`; whitespace check: `git diff --check`.
The known pre-existing monitoring matcher failure is outside the selected files
and remains deferred; full suite was not run.

Real embeddings/GigaChat generation/Groq/Redis/PostgreSQL/Qdrant server/procurement/
email calls: **NO**. Real Qdrant server tested: **NO**. New dependencies: **NO**.
Database migration: **NO** (number/checksum not applicable). Production deployed:
**NO**. No implementation blocker identified; operational limitations above apply.
