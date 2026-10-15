# Phase 24S.1B Redis / cache foundation

Starting worktree: clean, branch `phase24-professional-saas-core`, HEAD
`c0f06ce6305c922f4376ae0ae794365799860d64`. This is ephemeral infrastructure
only. Production, PostgreSQL behavior, the known Monitoring matcher bug,
auth semantics, tenant boundaries, one-time tokens and authorization remain unchanged.

## Audit before editing

| Area inspected | Existing state and decision |
| --- | --- |
| `app/api/security.py`, `main.py`, `auth_routes.py`; `tests/test_auth_rate_limit.py` | `AuthRateLimiter` holds lock-protected, bounded hash-only sliding-window event buckets. Dual client/identifier admission, capacity fail-closed, denied-request window behavior and login-success clearing need a dedicated distributed algorithm. Intentionally unchanged; distributed auth limiting needs an explicit later hardening/quota step. |
| `app/auth/repository.py`, `service.py` | Verification/reset cooldowns, session expiry, Telegram linking and one-time tokens already belong to relational storage with atomic transactions. Never move these to cache as authorization truth. |
| `app/sources/multi.py`, `registry.py`; organization workflow/source-health routes and tests | Source reports, duration/failure lists and per-fetch semaphores are request-local; registry dictionary is configuration, not TTL cache. Source-health UI reads persisted discovery snapshots/configuration. No cache migration. |
| `app/monitoring/service.py`, `repository.py`, bot monitoring | Seen claims and subscriptions are database-owned; matches/reports are transient local values. Existing monitoring scheduling remains unchanged; no new loops. Matcher fix remains deferred to 24S.2. |
| `app/bot/main.py`, handlers and company flows | Bot has its own database composition and Telegram-session/monitor-task shutdown. It does not consume the API runtime. No cache consumers justify adding another dependency/lifecycle here. Bot unchanged. |
| `app/services`, `app/rag`, `app/llm`, currency/source adapters | Analysis and parsing state is request-local; FastEmbed model file cache and Qdrant persistence are separate vendor-owned resources. No custom application TTL cache abstraction or Redis client/reference existed (only roadmap documentation mentioned Redis). No AI/embedding/procurement caching added. |
| `app/api/runtime.py`, `main.py`, routes/schemas, deployment healthcheck | Phase 24S.1A runtime owns created database resources; FastAPI closes only its created runtime. Injected runtimes remain externally owned. Component health uses safe status strings; Docker checks overall status. |
| Database/config loaders, other dotenv loaders | Existing convention: `load_dotenv(..., override=False, encoding="utf-8-sig")`; explicit environment wins. Reused for cache. |
| Requirements, Dockerfile, `.env.example`, `compose.yaml`, `compose.public.yaml`, `compose.postgresql.example.yaml` | Official psycopg dependencies retained. Existing deployment examples unchanged. Safe local defaults added to `.env.example`. Separate review-only Redis override added, no Redis container/image/service started. |
| PostgreSQL foundation, API, security, source-health, auth rate-limit, Telegram concurrency/runtime tests | Temporary SQLite fixtures and concurrent claims must keep database correctness. New offline Redis fakes and bounded local concurrency tests cover the new boundary without an external server. |

No real `.env` credentials, customer data or backups were read. Cache is unsafe as
an authorization source, as a replacement for database transactions/advisory locks,
or as an implicit replacement for vendor RAG locking/persistence. None were changed.

## Architecture and operation

`app/cache` provides a small synchronous `Cache` API: `get`, `set`,
`set_if_absent`, `exists`, `delete`, `acquire_lock`, `release_lock`, `status`, `close`.
Calls take a fixed domain and identifier. Async consumers must use `asyncio.to_thread`,
matching the repository's synchronous infrastructure pattern. Redis commands stay
behind `RedisBackend`; application consumers use the cache boundary. There is no
global client registry. No business feature was invented to exercise infrastructure.

`ApiRuntime.cache` is available to future consumers and included in live health.
`build_runtime` creates and owns it (`owns_cache=True`). Explicitly injected cache
resources are externally owned by default (`owns_cache=False`); callers may explicitly
transfer ownership. FastAPI's existing injected-runtime ownership rule is preserved.
Required/cache-config startup failure closes the already-created database before raising.
Runtime shutdown attempts cache cleanup and always closes its owned database.

### Configuration

| Variable | Default / accepted values |
| --- | --- |
| `VALYQON_REDIS_URL` | Empty means local memory. `redis://` or `rediss://`, optional numeric DB path. Query options, fragments and whitespace rejected to prevent overriding bounds. |
| `VALYQON_REDIS_REQUIRED` | `false`; accepts `true`, `false`, `1`, `0`. Required without a URL is invalid. |
| `VALYQON_REDIS_POOL_MAX` | 10; integer 1–100 |
| `VALYQON_REDIS_CONNECT_TIMEOUT` | 2 seconds; finite, >0 and <=120 |
| `VALYQON_REDIS_SOCKET_TIMEOUT` | 2 seconds; finite, >0 and <=120 |
| `VALYQON_CACHE_NAMESPACE` | `local`; lowercase letter followed by up to 63 lowercase letters/digits/underscore/hyphen. Operators must choose a unique project/environment namespace. |

Settings omit the URL from repr. Parser/backend diagnostics are fixed credential-free
messages, raised without raw exception chaining. No URL, host, username, password,
TLS detail or lock token is logged or returned in health.

No URL: bounded deterministic memory backend, no redis-py import or server needed.
Configured required Redis: startup PING/import/pool/connection failure raises
`CacheUnavailable`, aborts runtime startup, and never falls back to memory.
Configured optional Redis: failed startup yields an explicit unavailable backend;
all cache/lock operations fail with `CacheUnavailable`. No pretend memory success.
It does not automatically reconnect after failed initialization; rebuild the runtime
after fixing infrastructure. An initialized Redis client can recover from subsequent
connection failures; every status check probes PING, operations surface safe errors.
Required Redis loss after startup also rejects operations; health becomes unavailable.

### Keys, values, TTL and invalidation

Keys are `valyqon:<namespace>:cache:<domain>:<sha256(identifier)>` or the separate
`lock` space. Domains follow namespace validation. Identifiers are nonempty strings
up to 4096 characters and always hashed; user punctuation cannot inject Redis key
structure. Use internal IDs when possible; include tenant/scope in the identifier.
Do not pass raw tokens/secrets even though keys hash identifiers. Email normalization
is caller-owned; hashing is deterministic, not encryption or authorization.

Values are version-like tagged UTF-8: `t:` text or `j:` deterministic JSON
(sorted keys, compact separators). JSON supports null, booleans, finite numbers,
strings, lists and string-key dictionaries. Objects, tuples, bytes, non-finite values,
and non-string dictionary keys are rejected. No pickle or Python repr serialization.
Malformed stored data raises `CacheValueError`; a stored JSON null may return None,
so use `exists` when distinguishing null from a missing key matters.

Every write/lock requires explicit TTL, 1 ms–7 days inclusive, rounded up to
millisecond precision for Redis PX. No permanent application entries. Memory uses
an injected monotonic clock, serializes operations under RLock, purges expired keys
on every data operation, and caps live entries at 10,000. Full capacity raises an
explicit unavailable error; it never evicts a live lock. Idle expired entries remain
bounded until the next operation or close. No background cleanup loop is added.

`delete` explicitly invalidates one cache key. No KEYS, wildcard deletion, prefix
scans or namespace flushes exist. Locks are deliberately isolated from cache deletion.

### Pool and distributed locks

Official redis-py is lazily imported. One bounded `ConnectionPool.from_url` per
runtime is reused by a client, with explicit connect/socket timeouts and byte responses.
Shutdown closes the client then disconnects the pool, including partial-startup failures;
cleanup is idempotent and pool cleanup is attempted even if client close fails.
Stop consumers before runtime shutdown; no operations are permitted after close.

Lock acquire uses SET NX PX with a fresh cryptographically random 32-byte token.
Returned `LockLease` excludes its key/token/owner from repr. Release is a single Lua
compare-and-delete operation; stale owners cannot delete a renewed acquisition.
Local locks use the same TTL/token rules with atomic lock-protected compare/delete.
Default acquisition timeout is zero (one attempt); optional finite timeout is 0–120s,
with bounded 10 ms polling. Backend failure is distinct from contention timeout.
No renewal or indefinite lease exists. Release returns false if expired/already released.
Leases must be released through their creating cache instance.

These are leases, not fencing tokens or a consensus lock. Work outliving a lease can
overlap with a later owner; Redis failover/eviction can also invalidate exclusivity.
Future workers must design idempotency/fencing for their own effects. PostgreSQL
transaction/advisory locks remain database-owned and are not replaced.

### Health and errors

Cache reports `ready` (live Redis PING), `memory` (local), `disabled` (no injected
cache), or `unavailable`. Unavailable cache makes overall `/health` degraded while
database status is independently computed. Public health still returns HTTP 200;
the existing container healthcheck rejects degraded status. Memory/disabled cache
does not make local development unhealthy. Errors differentiate invalid configuration,
backend unavailability, invalid values/encoding/TTL and lock contention timeout.

## Validation, prerequisites and later phases

Dependency declaration added exactly: `redis>=5.2,<7` in `requirements.txt`.
Nothing was installed/downloaded; psycopg declarations remain unchanged.
Ordinary tests fake Redis commands, pool construction and Lua ownership semantics;
they do not establish real-server Lua/TLS/failover integration.

No local listener on port 6379 was found. No known isolated Redis service was supplied;
no unknown/production server was probed. `REDIS_INTEGRATION_TESTED=NO` and
`REAL_REDIS_DATA_WRITTEN=NO`. PostgreSQL real-server integration also remains outstanding.

Operators must install declared dependencies in the intended isolated deployment,
provision isolated Redis, choose distinct namespaces, configure credentials/ACLs and
TLS securely, review capacity/eviction and availability policy, and validate real-server
pool/TTL/NX/Lua/shutdown behavior before production use. Lua EVAL, GET, SET, DEL and
PING permissions are needed. The example override only targets API; bot currently
has no cache consumer. Production cutover is Phase 24T.

24S.1C may build worker coordination on this boundary; 24S.1E may add explicitly
designed AI cache/dedup consumers; 24S.1I may add quota/fair-usage algorithms. None
are implemented here. This cache supplies primitives, not sliding-window distributed
rate limits, job durability, authorization caching, workers or AI routing.

Validation used the existing adjacent `../tender-ai/.venv/Scripts/python.exe`
(Python 3.12.14), because the shell's `python` points to a nonfunctional Windows
Store alias. No environment was created or modified. With `VALYQON_EMAIL_MODE=disabled`:

```text
python -m pytest -q tests/test_redis_cache.py tests/test_postgresql_foundation.py tests/test_api.py tests/test_auth_rate_limit.py tests/test_phase17_security_hardening.py tests/test_telegram_link_runtime.py
158 passed, 0 failed, 0 skipped (60 new cache tests; 98 existing relevant tests)
TARGETED_TESTS_EXIT=0
python -m compileall -q app tests scripts
COMPILE_EXIT=0
git diff --check
GIT_DIFF_CHECK_EXIT=0
```

One existing Starlette/httpx TestClient deprecation warning was reported. No full
regression was run. Full regression/load testing and the known Monitoring failure
remain deferred to 24S.2. No phase-foundation blocker remains; real Redis integration
and production operator prerequisites are still outstanding. No commit/push/deployment,
real emails, AI calls or procurement calls were performed.
