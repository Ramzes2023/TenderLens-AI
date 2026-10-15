# Phase 24S.1D — AI gateway / router foundation

## Starting-state audit (before edits)

Verified clean worktree, branch `phase24-professional-saas-core`, HEAD
`2dd70a0727468faaabf0eeb1e202b115cf3e80c2`. No AGENTS.md files were found.

The existing `app/llm/base.py` Protocol already expressed the application's one
async text operation, `generate(prompt, *, max_tokens=512) -> LLMResponse`.
`app/llm/models.py` already returned project-owned text, model, provider, token
counts and finish reason. Reused both; no speculative domain operations added.

Exact generation paths found:

* `app/services/tender_analysis.py::analyze_tender`: prompt plus JSON schema,
  4096 output tokens; called by API personal and organization PDF routes and
  `app/bot/documents.py::pdf_handler`. Documents are prepared/truncated at
  20,000 characters by default, configurable 1..50,000. Response JSON rejects
  duplicate keys, nonfinite values, oversized responses and schema errors.
* `app/services/company_profile_analysis.py::analyze_company_search_profile`:
  prepared document plus schema, 2048 tokens; personal and organization company
  PDF routes. Uses the same document preparation and bounded JSON parsing.
* `app/rag/service.py::RagService.answer` (including organization wrapper):
  retrieved fragments plus question, 700 tokens; personal/organization API
  RAG routes and `app/bot/rag.py::ask_handler`. Retrieval runs with
  `asyncio.to_thread`; context limit defaults to 7000, configurable 1000..20000.
* `app/api/support_routes.py::support_assistant`: support prompt builder,
  bounded message/history/page fields, 700 tokens.
* `app/llm/health.py::main`: explicitly invoked live diagnostic CLI, 32 tokens.
  This is separate from HTTP `/health`; never executed during validation.

Only API runtime and bot composition directly constructed the text GigaChat
adapter outside `app/llm`. Business callers already depended on LLMProvider.
Other inference is embeddings: `app/rag/embedding.py` implements the separate
`EmbeddingProvider` contract (local FastEmbed by default, optional synchronous
GigaChat `client.embeddings`); `RagService.index_pdf/retrieve` and the explicit
`app/rag/health.py` diagnostic use it. Embedding adapters/composition in
`app/rag/service.py`, `app/rag/__init__.py`, and `app/rag/health.py` remain
unchanged for 24S.1F. They do not supply text generation SDK objects to business
code. No other generate/chat/complete/invoke/analyze inference paths found;
job repository `complete` is a storage operation.

GigaChat 0.2.3 uses async `client.achat.create`, native network timeout and an
adapter-level `asyncio.timeout` covering OAuth/generation/cleanup. It sets
`max_retries=0`, `verify_ssl_certs=True`, configured CA bundle, model/scope,
max_tokens and `storage=False`. No temperature override existed; none added.
There was no application retry loop or AI semaphore. Adapter errors used safe
messages and logged only error class names, with no raw payload/tracebacks.
Bot startup suppresses vendor HTTP diagnostics. Prompt builders are inline in
the services/support route; prompts, parsing and retrieval are unchanged.

Config uses dotenv `override=False`, provider-specific credential repr
suppression and existing proxy/TLS configuration in `app/network.py`.
Requirements already contain GigaChat/httpx/python-dotenv; no dependencies
installed or added. Dockerfile and Compose were inspected: API/bot load `.env`,
configure CA/proxy, and perform HTTP application health checks. New settings
therefore need no image/Compose changes. `.env.public.example` contains no
provider settings; the canonical `.env.example` is extended.

24S.1C jobs use synchronous handlers, a frozen explicit handler registry,
durable leases and explicitly started bounded workers. No production AI handler
exists. 24S.1B cache is runtime-owned, optional Redis infrastructure with bounded
pools/timeouts. Neither is invoked or modified by this gateway.

## Contract and architecture

Business service -> `AIGateway.generate` -> explicitly resolved `LLMProvider`
-> GigaChat adapter -> SDK. The existing Protocol is the explicit provider-neutral
contract. The gateway implements the same signature, preserving injected fakes
and public API behavior. A request dataclass is unnecessary: prompt is a string,
is not retained or logged, and has no generated repr containing documents.

`ProviderRegistry.register(name, provider)` accepts explicit objects, rejects
duplicate/invalid names, synchronous generation methods and registration after `freeze()`. Names match
`[a-z][a-z0-9_-]{0,31}`. Resolve rejects unknown names with fixed safe text.
Locks protect registration, freezing and resolution across threads. No dynamic
module loading, eval, import strings, API selection or fallback. Gateway startup
resolves the configured object and freezes the registry. `build_gateway()`
registers only GigaChat; unknown selection fails before credentials are loaded.

Normalized response is the exact `LLMResponse` type, freshly copied after primitive
field validation: text, registered provider name, model, optional input/output
token counts, optional finish reason, and 1-based successful attempt count.
Raw SDK objects, subclasses, empty/oversized text, invalid metadata types are
rejected. No prompt/response persistence or new telemetry is introduced.

## Configuration

Environment overrides dotenv. Canonical selection `VALYQON_AI_PROVIDER` defaults
to legacy `LLM_PROVIDER`, then `gigachat`; canonical wins when both are supplied.
Credentials/scope/model/CA/native timeout remain in GigaChatSettings.

| Setting | Default | Bounds |
| --- | --- | --- |
| VALYQON_AI_MAX_CONCURRENCY | 4 | integer 1..64 |
| VALYQON_AI_REQUEST_TIMEOUT_SECONDS | 30 | finite >0..300 |
| VALYQON_AI_MAX_ATTEMPTS | 2 | integer 1..5 |
| VALYQON_AI_RETRY_BASE_SECONDS | 0.25 | finite >0..30 |
| VALYQON_AI_RETRY_MAX_SECONDS | 2 | finite >0..60, >= base |

Invalid configuration errors never echo supplied values. Gateway prompts must
be nonempty strings <=400,000 characters (allows existing 50k documents after
JSON escaping plus schema); output token limit is integer 1..4096. Normalized
response text is <=100,000 characters. Existing domain preparation and parsing
limits are preserved; gateway never alters document text or prompts.

## Admission, deadline and retries

Each gateway owns one asyncio semaphore. The limit applies to actual provider
attempts, releases before backoff and on success/error/cancellation. Admission
wait, all attempts and all sleeps share one total gateway deadline. Concurrent
requests progress on the same event loop; gateway use from another event loop
fails safely, rather than sharing an asyncio semaphore unsafely across threads.
Registry alone is thread-safe. Different gateways/processes have independent
capacity; this is process-local concurrency, not distributed or billing quotas.

Native GigaChat timeout remains unchanged; whichever native/adapter/gateway
deadline occurs first wins. Gateway deadline maps to LLMTimeoutError. Async SDK
calls receive cancellation and perform async context-manager cleanup. No executor
or background threads are created by the gateway. **Limitation:** asyncio timeout
depends on cooperative cancellation. Blocking event-loop code, providers that
suppress cancellation, or unusually slow cleanup can exceed the deadline. Python
cannot forcibly terminate such code; this implementation does not claim that
guarantee. Future adapters must support cooperative async cancellation. The current
async GigaChat adapter does, as verified with mocked cancellable SDK calls.

Retries only: LLMNetworkError (transient transport), LLMProviderUnavailable
(GigaChat ServerError/5xx), LLMRateLimited (identifiable 429). At most max_attempts,
with deterministic `min(retry_max, retry_base * 2**(attempt-1))` seconds. Total
deadline still bounds retries. No timeout retries, auth retries, config/request
retries, arbitrary SDK/API failure retries, empty/invalid response retries or
domain JSON/schema retries. No Retry-After header or raw exception is propagated.
Unknown exceptions become permanent LLMAPIError. No external-provider fallback.

## Errors and security

Retained LLMError taxonomy: LLMConfigurationError, LLMAuthenticationError,
LLMNetworkError, LLMTimeoutError, LLMAPIError. Added LLMProviderUnavailable,
LLMRateLimited, LLMInvalidRequest, LLMInvalidResponse. Availability/rate-limit/
invalid-response errors subclass LLMAPIError, preserving existing catches.
Gateway replaces all provider exception messages with fixed project messages,
including project exceptions supplied by custom adapters. It raises outside the
provider exception handler with no raw cause/context. Adapter retains safe
`from None` mapping and class-only logging. No prompts, credentials, URLs,
headers, tokens or raw SDK exceptions are emitted by gateway logs (it has none).

## Runtime and roadmap boundaries

ApiRuntime.provider and bot tender_provider now contain a gateway constructed
in `app/llm/gateway.py`. All existing personal/organization tender PDF, profile
PDF, RAG generation and support inference uses that shared capability. RAG
generation is migrated by composition only; embeddings/retrieval remain unchanged.
The live LLM diagnostic also routes generation through a local gateway.
No gateway persistent resources require close. Existing database/cache lifecycle,
injected-runtime ownership, component errors and shutdown remain unchanged.
HTTP `/health` never calls AI; llm ready means locally configured capability,
not verified external reachability. Missing configuration remains unavailable.

No queue migration or production job handler (24S.1C); future async worker
composition can own a gateway/event loop, while current sync handler contract
must not be silently converted. No AI cache/dedup (24S.1E), RAG scaling or
embedding cache (24S.1F), quotas (24S.1I), or usage dashboard (24S.1J).

## Validation and remaining prerequisites

`scripts/validate_ai_gateway.py` requires explicit focused files, sets
VALYQON_EMAIL_MODE=disabled, and blocks external sockets/DNS. Loopback is allowed
for Windows asyncio and local tests. Deterministic fakes/mocked SDK calls cover
successful/retry/permanent/auth/timeout/invalid responses, bounded backoff,
concurrent admission/progress, cancellation/permit release, instance isolation,
thread-safe registry/security, safe traceback text, configuration and health.
The existing SDK construction test opens/closes without inference/network.
No real AI calls or real credentials are required. No full suite is run here.

Run focused files listed in the final report using the existing Python environment
and validation script; then `python -m compileall -q app tests scripts` and
`git diff --check`. Clean full regression remains a separate operator step.
Known Monitoring matcher failure stays deferred to 24S.2. Real PostgreSQL/Redis
integration, approved live provider verification, security/load validation and
controlled deployment remain pending. Operators should review process counts
when tuning local concurrency, gateway deadline versus GIGACHAT_TIMEOUT, and
retry behavior/cost before 24T. Production is untouched; nothing committed/pushed.

Final focused validation: **220 passed, 50 subtests passed, 0 failed, 0 skipped**,
exit 0; one pre-existing Starlette/httpx deprecation warning. Files:
`test_ai_gateway.py`, `test_llm.py`, `test_tender.py`, `test_company_profile_pdf.py`,
`test_api.py`, `test_bot.py`, `test_rag.py`, `test_organization_pdf_rag.py`,
`test_support.py`, `test_network.py`, `test_postgresql_foundation.py`,
`test_redis_cache.py` (all under `tests/`). Compileall and diff whitespace checks
exit 0. Used the existing sibling `tender-ai/.venv/Scripts/python.exe` interpreter;
the shell's bare Python alias was unavailable. No installation was performed.
An initial guard blocking even loopback was stopped because it prevented Windows
asyncio setup; the final guard permits only loopback and the final run passed.
