# Phase 24S.1D.1 — Multi-provider backup AI / automatic failover

Inserted after completed 24S.1E and before 24S.1F. Production is untouched.

## Audit before implementation

Starting branch: `phase24-professional-saas-core`; clean worktree at
`63a7438c6018f09dc02e383b7f978dc24679ea86`. No AGENTS.md was found.

Inspected `app/llm/base.py`, `models.py`, `gateway.py`, `gigachat.py`,
`cache.py`, `config.py`, `health.py`, API runtime, bot main, cache backend/config,
network conventions, existing gateway/cache/LLM tests, validation script,
requirements, env example, Dockerfile and Compose configuration. Reviewed AI
call sites in tender analysis, company profile analysis, RAG generation and
`app/api/support_routes.py`. Business callers already use provider-neutral generation.

The existing provider protocol returns project-owned frozen LLMResponse values.
Gateway construction is centralized in `build_gateway()` for API and bot; both
place `CachedAI` outside it. Registry registration is explicit object registration,
not import strings. The production builder permits only GigaChat as primary.
The GigaChat adapter uses its existing SDK with SDK retries disabled, verified TLS,
its existing model/options/parsing, and per-generation session ownership.

AIGateway has a total deadline encompassing admission, retries and backoff. It
retries network/unavailable/rate-limit failures up to its configured attempts;
timeouts terminate immediately. Unknown exceptions become permanent safe API
errors. Cancellation propagates. Defaults are 4 concurrent calls per gateway,
2 attempts, 30 seconds total, and exponential .25-second backoff capped at 2.

24S.1E fingerprints canonical JSON containing operation/version, provider,
`{model, adapter}` identity, prompt and max_tokens into SHA-256. Cache backend keys
hash that digest again. Semantic operations remain `tender-analysis:1`,
`company-search-profile:1`, `rag-answer:1`. Support, live diagnostics and embeddings
remain uncached. Cache hits reconstruct responses with attempts=0. Failures are
uncached. A lease owner performs generation; waiters poll the same fingerprint.

Two single-provider assumptions required changes: cache reconstruction formerly
required the primary provider, and lease TTL inspected a concrete gateway setting.
These now use `result_providers` and `maximum_generation_seconds` contracts.
The narrow identity contract and existing fingerprints/namespaces remain intact.
No Redis structures or backend changes are needed; memory and mocked Redis are
sufficient for validation.

HTTPX 0.28.1 is already installed/pinned. Startup networking config propagates
OUTBOUND_PROXY_URL into HTTP proxy environment variables and preserves NO_PROXY
and CA configuration. Groq uses verified HTTPX defaults and inherited environment;
it does not reuse GigaChat's provider-specific CA bundle or disable TLS. Compose
already passes `.env` to both services; no Docker change is needed.

## Architecture and exact policy

Business → CachedAI → optional FailoverGateway → GigaChat AIGateway,
then Groq AIGateway on eligible terminal error only.

Disabled fallback returns the original primary AIGateway. An API key's presence
does not enable it. Enabled fallback constructs exactly two independent gateways.
Only concrete AIGateways with ordered providers GigaChat and Groq are accepted;
nested failover routes and cycles are rejected. Gateways own concurrency, retries,
timeout and error normalization. Failover owns only ordered availability routing
and route identity. There is no extra retry loop or lock in the composition.

| Terminal primary error | Backup attempted? |
| --- | --- |
| LLMNetworkError | Yes, after bounded primary attempts |
| LLMProviderUnavailable | Yes, after bounded primary attempts |
| LLMTimeoutError | Yes, immediately after primary timeout policy terminates |
| LLMRateLimited | Yes, after bounded primary rate-limit retries |
| LLMAuthenticationError | No |
| LLMConfigurationError | No |
| LLMInvalidRequest | No |
| LLMInvalidResponse | No |
| Permanent LLMAPIError | No |
| Unknown/programmer exception | No; gateway normalizes as permanent API error |
| asyncio.CancelledError | No; immediately propagates |
| Business JSON/schema parsing failure after successful text | No |

Timeout inherits network error; rate limit inherits provider unavailable. The
explicit eligibility function uses these two transient families. Primary success
skips backup entirely. If backup fails, its sanitized gateway error category wins,
including authentication/configuration errors. It is raised outside the primary
exception handler, with no combined vendor messages or primary exception context.
Cancellation during backup also propagates immediately.

For configured attempt count A (1..5), maximum adapter calls are A primary + A
backup, sequentially, at most 2A; defaults 2+2=4. Timeout/permanent failures can
stop earlier. There is no return to primary, recursive backup, load balancing,
racing, dual inference, quality judging or business parsing fallback.

Both gateways use the existing VALYQON_AI_* policy with only provider replaced
for backup. Let D be VALYQON_AI_REQUEST_TIMEOUT_SECONDS (positive, at most 300).
Primary-only maximum generation deadline is D; enabled route is D+D=2D.
Defaults: 30 seconds primary + 30 seconds backup = 60 seconds, plus minimal
switching/cleanup scheduling overhead. Upper configured deadline sum is 600
seconds. Groq's own total adapter deadline T (GROQ_TIMEOUT) includes client
construction, HTTP request and cleanup, and is subordinate to its gateway's D.
These are cooperative asyncio deadlines, not hard real-time guarantees during
process pauses or non-cooperative transport cleanup.

## Groq wire contract and security

Fixed endpoint, never environment-configurable:
`https://api.groq.com/openai/v1/chat/completions`.

POST with Authorization bearer key and HTTPX-generated JSON content type:

```json
{
  "model": "openai/gpt-oss-120b",
  "messages": [{"role": "user", "content": "<VALYQON prompt/context>"}],
  "max_tokens": 512,
  "stream": false
}
```

Model and max_tokens come from validated settings/caller. No temperature, tools,
web search, execution, streaming or model-list request. Redirects are disabled.
One AsyncClient per generation, matching the small existing adapter architecture,
is explicitly closed by async context management. No persistent client, runtime
shutdown hook, executor or injected-client ownership ambiguity is introduced.
MockTransport injection is code-only for deterministic tests.

Successful JSON must be an object with exactly one choice, assistant message and
nonempty string content (at most 100000 characters). Model must match bounded
safe model syntax. Optional usage must be an object; prompt_tokens and
completion_tokens must be nonnegative integers (bool rejected) or absent/null.
Optional finish_reason must be a nonempty safe string of at most 64 characters.

Mapping: content → text; literal `groq` → provider; response model → model;
usage.prompt_tokens → input_tokens; usage.completion_tokens → output_tokens;
choice.finish_reason → finish_reason. Adapter attempts defaults to 1; gateway
records its own attempt number. Gateway then validates/copies the normalized
LLMResponse. No vendor dict, response, headers or request metadata is returned.

| Condition | Project error |
| --- | --- |
| 401, 403 | LLMAuthenticationError |
| 429 | LLMRateLimited |
| 500..599 | LLMProviderUnavailable |
| HTTPX timeout / adapter total timeout | LLMTimeoutError |
| HTTPX RequestError | LLMNetworkError |
| Other non-2xx, including other 4xx and redirects | Permanent LLMAPIError |
| Invalid/malformed successful JSON | LLMInvalidResponse |
| Invalid adapter input | LLMInvalidRequest |

Errors contain fixed messages and are raised outside upstream exception handlers.
No body, key, prompt, URL query, authorization or vendor exception is logged.
GroqSettings.api_key is repr=False. It must be a nonempty bounded printable
ASCII token without whitespace when the enabled route is constructed. Settings
validate model syntax `[A-Za-z0-9][A-Za-z0-9._/-]{0,255}` and finite timeout
0 < T <= 300. Secrets are absent from identity, fingerprints and health.

## Cache route identity, result provider and lease duration

Disabled route preserves existing primary identity exactly. Enabled route hashes
canonical JSON (sorted keys, compact separators, UTF-8) of:

```text
{
  revision: "valyqon-failover-v1",
  route: [
    {provider: "gigachat", identity: {model, adapter}},
    {provider: "groq", identity: {model, adapter}}
  ]
}
```

The existing narrow identity receives
`{model: <64-character SHA-256>, adapter: "valyqon-failover-v1"}`.
Fingerprint's provider remains the deterministic primary route anchor `gigachat`.
Enabling fallback or changing either model/adapter changes the fingerprint.
Credential changes do not. Endpoints, proxy/TLS values and credentials are not
inputs. If either adapter lacks a valid narrow identity, caching is bypassed.
Response provider is never used to choose the request fingerprint after execution.

CachedAI accepts only the configured route's result_providers: primary-only
accepts its one provider; failover accepts gigachat/groq. Thus cached backup
results remain truthful groq responses, and later hits invoke neither provider.

Effective lock TTL = max(configured VALYQON_AI_CACHE_LOCK_TTL_SECONDS,
maximum_generation_seconds + 10). Default enabled route TTL is max(60,60+10)=70
seconds; primary-only default is max(60,30+10)=60. At maximum gateway deadlines,
enabled TTL can be 610 seconds; backend TTL supports this. Configured lock input
bounds remain unchanged. Waiter timeout is independently configured (default 65);
operators should allow enough wait time for their route if they want duplicates
to wait through long generations. Waiter timeout never launches another chain.

Twelve-duplicate tests prove one owner performs the bounded primary/backup chain,
waiters share the same lease/fingerprint, fallback success is cached, cache hit
attempts=0, and failed chains remain uncached. No exactly-once claim under process
pause, lease expiry or network anomalies is made.

## Health, diagnostic and configuration

HTTP health reports only local configured AI capability ready/unavailable. It
never calls either AI provider, returns keys, fingerprints, endpoint details,
model permissions or claims Groq reachability. Existing degraded API/bot behavior
reports AI unavailable if configuration fails; it never substitutes a primary-only
capability for an explicitly requested but invalid backup configuration.

`python -m app.llm.health` remains an explicit uncached GigaChat-only live
diagnostic. It constructs the primary adapter/gateway directly and ignores
fallback. A failing primary cannot appear healthy through backup. It was not run
live during implementation. No separate live failover diagnostic was added.

Added environment variables:

```dotenv
VALYQON_AI_FALLBACK_ENABLED=false
VALYQON_AI_FALLBACK_PROVIDER=groq
GROQ_API_KEY=
GROQ_MODEL=openai/gpt-oss-120b
GROQ_TIMEOUT=30
```

Enabled flag accepts true/false/1/0, case-insensitive. Only groq is an approved
backup; unknown selections fail configuration even if disabled. Disabled fallback
does not load or require Groq settings/key and emits no missing-key warning.
Enabled fallback with absent/invalid key raises a configuration error before
constructing primary. Primary remains GigaChat; selecting Groq as primary is not
supported in this phase. No env-controlled imports/plugins are introduced.

Before enabling, operator must verify current account/model permissions and
external account limits, provide a secret key through deployment configuration,
confirm model/timeout and route/wait deadlines, verify trusted TLS/proxy settings,
set enabled=true explicitly and restart the appropriate processes. Perform any
authorized live diagnostics separately from health and offline tests. Free
limits are provider-controlled and may change; correctness never relies on a
specific free quota. 429 is a bounded provider condition, not a quota tracker.
SaaS quota/fair-use work remains Phase 24S.1I.

## Scope and validation

Validation uses `scripts/validate_ai_gateway.py`, which disables email and blocks
external DNS/TCP. Groq uses HTTPX MockTransport; GigaChat uses mocks/fakes.
No key is requested; no real AI/Redis/PostgreSQL service or Docker is contacted or
started. REAL_REDIS_AI_CACHE_TESTED=NO. No packages installed or dependencies
changed. No business caller, prompt, GigaChat semantics, RAG chunking/retrieval/
embedding/citation, monitoring matcher or job queue changed. AI remains in its
current execution path. No commit, push or deployment.

Focused validation covers Groq, failover, AI gateway/cache, LLM, Redis foundation,
API/bot, tender, RAG and support. Compileall and git diff --check are required.
Known baseline monitoring failure remains deferred to 24S.2; the full suite is
not run. Upcoming 24S.1F work is intentionally excluded.

Final focused run: **291 passed, 48 subtests passed**, exit 0, with one existing
Starlette/HTTPX deprecation warning. Files: `test_groq.py`, `test_ai_failover.py`,
`test_ai_gateway.py`, `test_ai_cache.py`, `test_llm.py`, `test_redis_cache.py`,
`test_api.py`, `test_bot.py`, `test_tender.py`, `test_rag.py`, `test_support.py`.
API and bot composition tests execute their entrypoints with mocked AI and
temporary local SQLite storage; no external infrastructure is used.
`compileall -q app tests scripts` exit 0; `git diff --check` exit 0.
The Windows `python` alias was unavailable; validation used the already-existing
`C:/Users/ramze/Documents/Codex/tender-ai/.venv/Scripts/python.exe` interpreter.
No installation was performed. HEAD remains the starting commit; work is uncommitted.
