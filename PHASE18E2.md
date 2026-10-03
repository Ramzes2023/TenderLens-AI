# Phase 18E2 - Organization PDF Analysis and RAG Boundary

Base commit: `1956727` - organization tender data boundary.

Phase 18E2 connects organization-scoped PDF analysis and semantic RAG to the
shared organization data namespace introduced in Phase 18E1.

Legacy personal/Telegram PDF and RAG behavior remains unchanged.

## Organization PDF analysis

New session-authenticated endpoint:

- `POST /api/v1/organizations/{organization_id}/analysis/pdf`

The workflow:

1. requires an authenticated organization member;
2. requires owner/admin/member write permission;
3. requires a shared active organization company;
4. computes SHA-256 inside the organization namespace;
5. reuses an existing organization analysis for duplicate PDFs;
6. parses and analyzes a new PDF when no duplicate exists;
7. scores the result using the shared active company profile;
8. persists the analysis in the organization tender namespace;
9. optionally indexes the document into organization RAG.

Viewer remains read-only and cannot upload/analyze organization PDFs.

## Duplicate isolation

PDF SHA-256 deduplication is organization scoped.

The same PDF hash can independently exist in:

- a legacy personal/Telegram owner namespace;
- organization A;
- organization B.

A duplicate in one namespace does not suppress analysis or access in another
namespace.

## Organization RAG

New session-authenticated endpoint:

- `POST /api/v1/organizations/{organization_id}/rag/ask`

The request contains:

- `pdf_sha256`
- `question`

It does not accept `owner_user_id`.

The organization must already contain the requested tender record before RAG
is queried.

Viewer members may use organization RAG because it is a read operation.

Cross-organization documents remain hidden.

## Qdrant namespace

No destructive Qdrant migration is required.

The existing vector payload/filter contract remains:

- `owner_user_id`
- `pdf_sha256`

Organization vectors use the internal synthetic owner:

`8_000_000_000_000 + organization_id`

Therefore existing legacy vectors and organization vectors remain separated
inside the existing Qdrant collection.

Point IDs are also different because the synthetic owner participates in the
deterministic point ID.

## Authorization around long-running work

PDF parsing, LLM analysis, embeddings and RAG generation may take longer than
ordinary database operations.

For PDF analysis:

- write membership is checked before work begins;
- SQLite persistence re-checks membership inside the same `BEGIN IMMEDIATE`
  transaction as the organization tender write;
- RAG indexing happens only after the authorized organization tender has been
  persisted;
- membership is checked again before returning the final analysis response.

If membership is revoked before the final SQLite save, no tender record or RAG
index is created.

If membership is revoked after the authorized SQLite save while RAG indexing is
already running, the organization-owned tender may remain persisted and the
started organization indexing may complete, but the revoked caller does not
receive the final response.

For RAG questions:

- organization tender access is verified before RAG/LLM work;
- membership is checked again after the RAG answer is produced;
- if membership was revoked during the external operation, the answer is not
  returned to that account.

## Browser and legacy security

Organization PDF and RAG endpoints require Web session authentication.

Legacy `X-API-Key` alone is not organization identity.

The reserved synthetic organization owner namespace remains blocked from legacy
owner-scoped HTTP APIs.

Explicit cross-origin browser POST requests are rejected.

## Compatibility

Phase 18E2 does not change:

- existing Telegram PDF analysis;
- existing personal Web PDF analysis;
- legacy owner tender history;
- legacy owner Qdrant vectors;
- Qdrant collection name;
- Qdrant payload schema;
- background monitoring subscriptions.

No production data migration is required by this checkpoint.

## Validation

Initial Phase 18E2 focused regression:

`58 passed`

Final PDF/RAG security and namespace regression:

`39 passed`

Full suite after Phase 18E2:

`259 passed, 1 skipped, 38 subtests passed`

The remaining warning is the existing Starlette/httpx deprecation warning.

`compileall` passes.

`git diff --check` reports no whitespace errors; Windows may display
LF-to-CRLF working-copy warnings.
