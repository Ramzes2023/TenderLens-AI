# Phase 24S.1E — AI Cache + Deduplication Foundation

## Audit before implementation

Starting branch `phase24-professional-saas-core`, HEAD
`65a9ae42e243e09f3c815e14938d1a58c8413640`, clean worktree verified.
No AGENTS.md was present. Audit covered:

- `app/cache/backend.py`: synchronous runtime-owned Cache; async clients must use
  `asyncio.to_thread`. MemoryBackend is mutex-protected, capacity bounded (10,000
  entries), expires entries against monotonic time and never evicts live locks.
  RedisBackend uses existing redis dependency, PX TTL, SET NX and owner-token
  compare-and-delete Lua release. Cache.acquire_lock supports timeout=0; this layer
  uses that mode and implements cancellation-aware async polling. No lock code,
  Redis imports, private result dictionary, or alternate key builder duplicated.
- `app/cache/config.py`: explicit optional/required Redis policy. Required startup
  outage raises CacheUnavailable; optional startup outage creates UnavailableBackend,
  never implicit memory fallback. Absent Redis URL explicitly selects memory.
  TTL range is 1 ms–7 days. Serialization is tagged JSON (`j:`) or text (`t:`),
  no pickle; backend had no independent byte limit. Keys hash identifiers and use
  `valyqon:<namespace>:cache|lock:<domain>:<sha256>`.
- `app/llm/gateway.py`, registry, config, base and models: gateway owns selection,
  retries, semaphore, total deadline (including admission/backoff), validation and
  safe errors. Default deadline 30 s, concurrency 4, attempts 2. Prompt bound
  400,000 characters, max_tokens 1–4096, response bound 100,000 characters, model
  256, finish reason 64. LLMResponse is frozen project-owned primitives; consumers
  do not require attempts >= 1. Previously no stable provider cache identity.
- `app/llm/gigachat.py`: configured model supplied to request; sole variable
  generation option max_tokens; one user message, storage=False, SDK retries=0.
  Credentials/scope/TLS/network settings are transport/authentication, excluded
  from identity. Adapter logs fixed error class only, no prompts/results/tracebacks.
- `app/services/tender_analysis.py`: exact bounded document plus schema and
  truncation indicator in prompt; max_tokens=4096; downstream schema validation.
  `company_profile_analysis.py`: bounded company text/schema prompt, 2048 tokens.
  `app/rag/service.py`: authorized scoped retrieval precedes generation; question,
  selected chunks, page numbers, rounded scores and instructions are all in prompt;
  700 tokens. No retrieval/embedding caching introduced.
- `app/api/support_routes.py`: message/history/page-path prompt; conservative bypass
  for conversational/live semantics and possible future account state. Diagnostic
  `app/llm/health.py` constructs core gateway directly for deliberate live probe.
- `app/api/runtime.py`: owns existing cache; provider composed independently, injected
  ApiRuntime fields remain untouched. Bot main previously built gateway independently;
  now owns a cache and uses same decorator factory. run_bot injected contracts remain
  unchanged. Cache is closed at normal shutdown and database startup failure.
- Environment uses dotenv override=False; gateway loads it before AI cache settings.
  Added settings use finite numeric bounds and fixed sanitized configuration errors.
  Provider errors remain normalized LLM errors; cache errors remain app/cache errors.
- Document SHA-256 already exists in API/PDF/bot ingestion, authentication digests,
  queue identity and migrations. None represents complete AI request semantics.
  Job queue owns durable jobs and its own lease policy; no AI job handler or worker
  startup changed. Existing storage persists structured tender analyses, PDF hashes,
  RAG text/chunks and embeddings. No raw prompt/result logging added. SECURITY.md
  treats data/vector volumes as sensitive. Bot redacts tokens/proxy credentials and
  suppresses vendor HTTP logs. Cached generated text is sensitive ephemeral data:
  opaque keys do not make Redis values public-safe.
- Existing tests use injected fake providers, mocked SDK/Redis, memory clocks.
  `scripts/validate_ai_gateway.py` forbids external DNS/connect/connect_ex and disables
  email; permits loopback for Windows asyncio/API machinery. Used unchanged.

## Architecture and explicit cacheability

Business service → CachedAI → AIGateway → provider adapter. Core gateway remains
usable alone. CacheIdentityProvider documents optional safe identity; gateway exposes
that identity without importing Redis. generate_operation preserves legacy injected
provider.generate signatures and only passes semantic context to CachedAI.

| Current operation | Cacheable | Namespace/version | Reason and tenant policy |
| --- | --- | --- | --- |
| Tender analysis | YES, opt-in | tender-analysis:1 | All extraction content/schema/instructions in exact prompt; no hidden tenant input |
| Company search profile | YES, opt-in | company-search-profile:1 | Company document/schema entirely in prompt; draft result independent of account |
| RAG final answer | YES, opt-in | rag-answer:1 | Actual selected context/question in prompt after scoped authorized retrieval; sources returned from current retrieval |
| Support assistant | NO | none | Conservative live/conversational bypass; hidden account state must never become accidentally cacheable |
| Live diagnostic | NO | none | Direct core gateway must probe actual provider, never old result |
| Embeddings/retrieval | NO | none | Outside phase; remain existing paths |

Operation constants are code-owned, validated namespaces and positive integer versions.
Bump version when semantic prompt/schema/business contract changes. Never infer it
from user text. No new endpoint accepts arbitrary operation identities. The three
cacheable operations safely share exact results across tenants because no hidden
account input affects generation; authorization/retrieval still run before cache use.
Cache is never an authorization source. Future hidden tenant-dependent operations
must bypass or extend the versioned schema with a safe hashed scope before opting in.

## Fingerprint and provider identity

Canonical UTF-8 JSON, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
allow_nan=False, SHA-256 lowercase hexadecimal. Exact input object:

```json
{
  "schema": "valyqon-ai-request-v1",
  "operation": "tender-analysis",
  "operation_version": 1,
  "provider": "gigachat",
  "identity": {"model": "<configured model>", "adapter": "gigachat-chat-v1"},
  "prompt": "<exact prompt, no trimming or normalization>",
  "generation": {"max_tokens": 4096}
}
```

Provider comes from AIGatewaySettings.provider; model identity comes explicitly from
GigaChatProvider.settings.model. Adapter identity `gigachat-chat-v1` versions the fixed
request/generation configuration. Increment it if role/message/options configuration
changes. Future providers must explicitly supply exactly model/adapter nonempty string
fields <=256 chars; missing/invalid/throwing identity safely bypasses. No fallback to
provider name. Provider settings are expected stable during an execution; model changes
between requests change digest. Credentials, scope, tokens, endpoints, TLS/proxy paths,
retry/admission timing do not enter identity. Configured model aliases can be remapped
by a vendor; operators should use pinned model identities where supported and bump
identity/version or invalidate if the alias changes externally. Cache is bounded,
not a guarantee of permanently reproducible stochastic generation.

## Keys and value schema

Reuse Cache.key with domain `ai-result`, identifier=request fingerprint:

- Result: `valyqon:<namespace>:cache:ai-result:<sha256(fingerprint UTF-8)>`
- Lease: `valyqon:<namespace>:lock:ai-result:<sha256(fingerprint UTF-8)>`

The second digest is intentional reuse of the existing key builder. Keys contain no
prompt/document/question/tenant ID/credentials. No KEYS, wildcard flush, or key logging.

Tagged existing JSON encoding stores exactly:
`schema=1`, `text`, `provider`, `model`, `input_tokens`, `output_tokens`, `finish_reason`.
No SDK objects, attempts, prompt, metadata blobs or pickle. Exact shape/types required;
provider must equal current selected provider (<=32 chars); response fields reuse
gateway bounds, counts nullable exact ints 0–1,000,000,000. Cached attempts=0 describes
zero provider attempts in this request; owner returns actual gateway attempts. No
public response field added. Reads reject extra keys, wrong types, encoding errors,
empty/oversized text, oversized model/finish reason, token anomalies; invalidate exact
entry and treat as miss without exposing contents. Invalidating/read outages follow
required/optional policy. Cache values are untrusted and construct only LLMResponse.

Encoded AI values limited to 524,288 bytes; gateway response limit remains 100,000
characters. Valid gateway responses exceeding cache byte/count limits or failing JSON
encoding are returned without storage. No cache success for provider invalid responses,
errors/timeouts/cancellation. No negative caching. Business schema validation remains
at the business boundary; the cache stores validated gateway generation, not a claim
that downstream tender/profile JSON is valid.

## Settings, TTL and single-flight

Default **disabled**, preserving existing product behavior. Explicit settings:

| Environment | Default | Bounds |
| --- | --- | --- |
| VALYQON_AI_CACHE_ENABLED | false | true/false/1/0 |
| VALYQON_AI_CACHE_TTL_SECONDS | 3600 | 1–604800 |
| VALYQON_AI_CACHE_LOCK_TTL_SECONDS | 60 | 1–600 |
| VALYQON_AI_CACHE_WAIT_SECONDS | 65 | .01–600 |
| VALYQON_AI_CACHE_POLL_SECONDS | .05 | .01–2, <=wait |

Result TTL fixed; cache reads never refresh it. Effective lease TTL is
max(configured lock TTL, gateway total request deadline + 10 seconds); default 60 s
for default 30 s gateway. Gateway includes semaphore wait, all retries and backoff in
its total deadline. At maximum gateway deadline 300 s effective lease >=310 s. The
10-second margin covers normal cache write/release and scheduling; leases cannot stop
an already-running provider during process pauses/network anomalies or cancellation-
uncooperative adapters. Cross-process exactly-once external execution is not guaranteed;
downstream correctness must not depend on it.

Algorithm:

1. Bypass if disabled, explicit bypass=True, no operation, or unsafe/missing identity.
2. Validate request; canonical fingerprint; read/validate result. Hit skips gateway,
   retry loop and concurrency permit entirely.
3. Attempt existing Cache.acquire_lock(ttl=effective lease, timeout=0).
4. If busy, await bounded poll sleep and check cache/try ownership again. Total waiter
   budget 65 s by default; expiry raises fixed LLMTimeoutError, never launches a
   duplicate just because waiting timed out. Cache I/O retains backend socket bounds;
   an in-progress thread operation can add bounded backend I/O latency to wait budget.
5. Upon acquisition, **check cache again**. If populated, return without inference.
6. Otherwise execute gateway normally once; validate there, serialize bounded response,
   write fixed result TTL and return.
7. Finally compare-and-delete token-owned lease. Never release another owner's token.

Cancellation during acquisition waits for the short thread call and releases any
acquired token; cancellation during inference propagates and releases. Cancellation
while writing completes the bounded write then invalidates before releasing. Backend
outage can prevent cleanup; finite lease/result TTL bounds retention and no strong
atomic cancellation guarantee exists during an unreachable distributed write. Waiter
cancellation never cancels the owner. Failed owner releases when possible; waiter can
then acquire and retry; orphan lease expires. No busy-spin, no indefinite waiting.

## Failure policy, health and invalidation

Required Redis unavailable: CacheUnavailable stays fail-closed at startup and runtime;
no local fallback and no inference on failed cache admission. Required write/release
outage after generation returns cache error without re-executing inference. Primary
provider failures/cancellation are preserved even when cleanup is unavailable.
Optional unavailable backend: bypass cache/dedup and call gateway normally. Optional
write/release outage after successful inference returns the existing result, never
re-executes it. No claim of distributed dedup while unavailable. Memory is used only
when explicitly configured by absent Redis URL. CacheValueError during serialization
skips storage. Provider failures remain normal sanitized LLM errors, not Redis errors.

Existing cache health remains authoritative; llm health is local configured readiness.
No added health fields, no inference from health, no hashes/keys/URLs exposed.
`await CachedAI.invalidate(fingerprint)` accepts only exact lowercase 64-hex digest;
optional outage returns False, required outage raises. Version bump is broad semantic
invalidation; no admin UI/global flush.

## Integration, validation and remaining work

API composition reuses runtime.cache; bot main uses the same compose_cached_ai factory
and owns/closes its cache. Explicit injected runtime/run_bot providers are preserved,
and direct legacy injected providers remain uncached by design. Support goes through
decorator with no operation and bypasses. Diagnostic remains direct gateway. No workers
started, no AI jobs migrated, no DB/job schemas changed, no dependency added.

Offline tests cover deterministic material-input digests, canonical identity ordering,
process hash seeds, credential exclusion, bounds, expiry, attempts, bypass/invalidation,
corrupt encodings/shape/fields, provider failures and cancellation, concurrent identical
calls across separate wrappers (12), independent fingerprints under gateway concurrency,
waiter cancellation/takeover, second check, expired orphan lock, no busy-spin, unavailable
required/optional cache, write outage avoiding re-execution, unencodable/oversized values,
Redis PX/NX and existing token-owned Lua release through mocked RedisBackend. Provider,
Redis and procurement/email network activity are not performed.

Use existing sibling tender-ai/.venv/Scripts/python.exe; bare python alias on this machine
is unavailable. No install. Validation uses scripts/validate_ai_gateway.py with explicit
focused files. Full regression deliberately deferred for independent run; known Monitoring
matcher failure untouched. Real PostgreSQL and real Redis integration remain pending.
REAL_REDIS_AI_CACHE_TESTED=NO, REAL_AI_CALLS_MADE=NO, PRODUCTION_DEPLOYED=NO.

Operator steps before enabling: configure finite TTL/settings and shared cache namespace,
use isolated Redis integration validation, review cache text retention/access/TLS and pinned
model policy, run independent final regression/security/load validation and controlled
production change review. Default flag remains false; no production environment changed.
24S.1F owns RAG scale; 1I owns quotas/fair usage; 1J owns observability. No metrics/dashboard,
embedding cache, retrieval change, connector/scoring/billing work included here.

Final validation: **229 passed, 48 subtests passed, 0 failed, 0 skipped**, exit 0,
with one pre-existing Starlette/httpx deprecation warning. Focused files:
`test_ai_cache.py` (66 tests), `test_ai_gateway.py`, `test_redis_cache.py`,
`test_tender.py`, `test_company_profile_pdf.py`, `test_rag.py`,
`test_organization_pdf_rag.py`, `test_support.py`, `test_api.py`, `test_bot.py`,
`test_llm.py`. Final bounds-order/label cleanup was followed by an additional guarded
cache-only run: **66 passed**, exit 0. Compileall app/tests/scripts exit 0;
git diff --check exit 0. All tests used email disabled and the external-network guard.
No full suite, real Redis server, real AI call, deployment, commit or push performed.
