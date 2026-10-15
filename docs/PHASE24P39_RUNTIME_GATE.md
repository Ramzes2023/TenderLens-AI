# P24P.3.9 resource/runtime gate â€” 2026-10-11

### P3.9C measured relevant regression and local checks

Exact command, fresh basetemp:
```powershell
python .cache/phase24p3/run_tests.py p39c-regression tests/test_analytics_process_isolation.py tests/test_analytics_admission.py tests/test_analytics_runtime_gate.py tests/test_analytics_api.py tests/test_analytics_compatibility.py tests/test_analytics_service.py tests/test_company_history_paging.py tests/test_analytics_fit.py tests/test_analytics_dates.py
```
**329 passed, 0 failed, 0 skipped/deselected, exit 0, 195.44s** on Windows;
includes all 25 process cases. Counts overlap the initial run; do not sum them.
One existing Starlette/httpx deprecation warning; no test errors or sandbox blocker.
No broad 1489-test rerun; historical totals are not new execution evidence.
`python .cache/phase24p3/p39c_checks.py`: exit 0; all six local Node suites
(company, discovery, discovery_full_ai, phase24r, premium, shortlist_ui) exit 0;
compileall of process_isolation.py and its test passes; git diff --check exit 0.
Git emitted existing LF/CRLF conversion warnings. Fresh helper/output names preserve
previous cached artifacts. No dependency installation or browser/server execution.

## P24P.3.9C independent Windows execution and narrow audit (2026-10-11)

**P3.9 PARTIAL; P4 BLOCKED. P39B remains an UNWIRED SYNTHETIC PROTOTYPE.**
This checkpoint independently executed the existing tests BEFORE any code change.
HEAD 93f02eb, branch phase24-professional-saas-core; implementation/tests unchanged.
Platform: win32, Windows 11 10.0.26200-SP0, Python 3.12.14 AMD64.

`python .cache/phase24p3/run_tests.py p39c-process-initial tests/test_analytics_process_isolation.py`
returned **25 passed, 0 failed, 0 skipped, exit 0, 5.58s**. No test errors.
Fresh basetemp; no Windows skip or runner/security modification. These are actual
Popen children and kernel32 Job Objects, not code-authoring/runner-exit claims.
Some invalid-input/setup fault tests deliberately mock failures; they are not
substitutes for the real process, memory, timeout and job-close cases.

Verified: job creation/set/query/assignment, 64 MiB OS process committed-memory
limit (64 MiB + 4096 VirtualAlloc denied; same fixed control child succeeds and
frees allocation without page touches), parent wall-clock timeout of an initialized
30-second sleeping child, cancellation/shutdown, job-close termination, owned
handle wait/reap, active-child/task cleanup and five-job handle-count stability.
Crash/exception, malformed/overlong output, result/PID checks and slot reuse pass.
Active-process limit 1 is read back; descendant enforcement is NOT demonstrated.
No CPU quota, RSS/peak whole-request/parent-memory bound or hostile-code sandbox
is proved. No unrestricted resource exhaustion or unrelated process termination.

Narrow audit: ctypes HANDLE/signatures and memory flags are consistent with the
exercised paths. Assignment precedes request input, but interpreter startup is
NOT suspended and occurs before assignment. stdout is bounded; stderr goes to
DEVNULL. Retained Popen handles own termination/reap; five repetitions show no
handle leak on exercised paths. Start/assignment faults are exercised, but arbitrary
Win32 cleanup failures and all races are not exhaustively proved. Cleanup has no
await and retains task ownership if it fails; synchronous startup, stdin write and
up-to-five-second reap cannot be preempted by the polling deadline. No fix was
needed or assertion weakened. Forced real-server parent death remains untested.

Offline/network/DNS/dotenv guards stayed intact; subprocess/Job Object operations
were allowed without elevation or security bypass. No real analytics/authentication,
connection acquisition, PostgreSQL, live HTTP disconnect or browser isolation proof.
Existing work and .tmp-phase24* preserved; no staging/commit/push/deploy or rollout.
Historical P39B reports below are retained; current independent evidence is here.

ONE next checkpoint: a bounded backend integration design for ownership across
auth/acquisition/calculation and disposable-server acceptance criteria, explicitly
settling startup and committed-memory versus RSS/CPU policy before any API wiring.
P4 requires explicitly accepted prerequisites; no P4/P5 implementation here.
PRODUCTION_TOUCHED=False.


## P24P.3.9B Windows isolated-process prototype (2026-10-11)

**P3.9 remains PARTIAL; P4 remains BLOCKED. Experimental proof only, no rollout.**
New independent `app/analytics/process_isolation.py` and
`tests/test_analytics_process_isolation.py` are not imported by API, admission,
startup/shutdown, DB, scoring or charts. All previous work is retained.

Environment: repository venv Python 3.12.14, MSC v.1944, AMD64;
`C:/Users/ramze/Documents/Codex/tender-ai/.venv/Scripts/python.exe`;
Windows 11 `10.0.26200-SP0`. Its own `sys._base_executable` is
`C:/Users/ramze/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`.
The Windows venv redirector creates another process, incompatible with an
active-process limit of one; child uses this SAME runtime base executable with
`-I -S`, not a different installation. Existing installed versions inspected:
pytest 9.1.1, FastAPI 0.142.2, Pydantic 2.13.5, httpx 0.28.1.
No package installs, admin, Docker, external network or environment-secret reads.
`rg` was unavailable; native PowerShell reads were used.

Protocol: fixed executable and absolute module path, argument-list Popen,
CREATE_NO_WINDOW, close_fds, minimal literal SystemRoot environment; no shell,
pickle, arbitrary executable data, DB handles/sessions or credentials. Synthetic
integer-list jobs only (128 values, absolute value <=10000), 2048-byte request,
1024-byte result plus two-byte fixed readiness header. Child independently checks
exact request fields/version, duplicate keys and nonfinite constants. Parent
checks exact response fields/types, own Popen PID, count and sum; errors are fixed
codes, stderr discarded. Child blocks socket/subprocess events and dotenv reads;
this is not a hostile-code/filesystem/access-token security sandbox.

Lifecycle: immediate capacity rejection, one event-loop owner, at most two owned
children per Prototype, no waiting queue. Create job -> set/query limits -> spawn
trusted child waiting for input -> assign job -> send bounded request -> verified
ready -> result/exit. Job assignment failure kills/waits the owned process.
Deadline starts before setup; polling uses bounded PeekNamedPipe reads. Cancellation,
wall deadline and shutdown terminate the job/owned process and wait for process
handle signaling, close pipes/process/job handles, THEN release ownership.
Cleanup contains no await, so repeated coroutine cancellation cannot release a
live slot. Failed cleanup retains ownership (fail closed). Shutdown rejects new
work and cancels/joins existing tasks. Receipts retain at most 32 synthetic
PID/exit records. No enumeration or termination of unrelated processes.

Verified locally without privileges: actual Job Object creation, setting/querying
KILL_ON_JOB_CLOSE, process committed-memory limit 64 MiB and active-process limit
1; assignment works within this sandbox's enclosing job. Normal results, child
exception, exit 17, initialized sleeping hang, malformed/overlong output, wrong
PID, invalid inputs, cancellation before spawn and after child ready, two concurrent
workers/third rejection, slot reuse and deterministic shutdown all tested.
Actual kill/reap uses retained process handles, not PID lookup. Job-close test
waits for death of a ready 30-second sleeping child within five seconds; Windows
returns exit status 0 on this kill path, so nonzero status is not the proof.
Five repeated jobs leave GetProcessHandleCount unchanged.

Memory evidence: child VirtualAlloc request of 64 MiB + 4096 committed bytes is
refused under the job cap, succeeds in the same fixed child without that job,
and is immediately freed without touching pages. This proves an allocation
commit limit, NOT RSS, peak whole-request memory, parent memory or CPU protection.
OS active-process setting is read back; application concurrency is exercised;
a descendant creation/active-count enforcement test is not claimed.
CPU quota/time accounting and RSS enforcement are **unsupported/unverified** in
this prototype. No CPU/memory exhaustion workloads were run.

Limits/blockers: CreateProcess and small blocking stdin writes are synchronous;
interpreter startup happens before assignment, with no suspended-start guarantee.
Trusted fixed child imports stdlib before its audit guard. Five-second reap waits
can briefly block the owning loop; forced parent termination under real server
conditions is not tested (job-close mechanism is tested). Wall deadline covers
polling/initialized child, not preemption of parent startup/system calls or cleanup.
No whole-request auth, connection acquisition, SQLite read, tenant authorization,
production analytics calculation, HTTP delivery or live-server disconnect proof.
No global replica cap, PostgreSQL server, browser, retention, D/R/P or consumer
acceptance. Current production H execution remains the original thread design.

Verification and exact selected counts are recorded below. Historical baseline
1489 passed + 2 skipped / 390 subtests and all earlier reports are unchanged and
are NOT claimed rerun by this prototype. Diagnostic runs: first 9 failed/9 passed
revealed venv redirector/one-process-job interaction; base-runtime repair gave
18 passed. Later 1 failed/20 passed corrected a new test's assumption that
kill-on-close must return nonzero; existing assertions were not weakened.
An initial existing-test command referenced nonexistent test_api_security.py:
no tests ran, exit 1; corrected selection uses test_phase17_security_hardening.py.

ONE next bounded checkpoint: backend-only suspended-start/lifetime and CPU-cap
acceptance for the SAME synthetic prototype, including startup failure cleanup,
with explicit policy for committed memory versus RSS; keep API disconnected until
that evidence and a separate integration decision. Auth/acquisition integration,
live disconnect, PostgreSQL and browser remain separate future gates.
PRODUCTION_TOUCHED=False.


### P3.9B final measured verification

All commands use repository `python .cache/phase24p3/run_tests.py`; external
network/DNS and dotenv guards remain installed. Final accepted results:

- `isolation-final-drain tests/test_analytics_process_isolation.py`:
  **25 passed**, 0 skipped/deselected, exit 0, **11.77s**.
- `isolation-existing-accepted tests/test_analytics_admission.py tests/test_analytics_api.py tests/test_analytics_compatibility.py tests/test_analytics_runtime_gate.py tests/test_phase17_security_hardening.py tests/test_web_auth.py tests/test_auth_api.py tests/test_auth_rate_limit.py`:
  **142 passed**, 0 skipped/deselected, exit 0, **216.82s**.
- `isolation-analytics-remainder tests/test_analytics_service.py tests/test_company_history_paging.py tests/test_analytics_fit.py tests/test_analytics_dates.py tests/test_analytics_normalization.py tests/test_discovery_history_api_behavior.py tests/test_discovery_history_repository.py`:
  **241 passed**, 0 skipped/deselected, exit 0, **36.92s**.

The final three selections have zero shared test-file/node IDs: 25 new cases,
383 existing selected cases. Existing cases overlap prior historical regressions;
none is an additional claim beyond these executions. Earlier successful prototype
reruns (18, 21, 21, 21, 25, 25 cases) overlap the final 25 and must not be added.
No new subtest count was reported. Existing tests show one preexisting Starlette
warning. Broad 59-file 1489+2 / 390-subtest regression was NOT rerun; no full
repository, live server/transport, PostgreSQL server or browser execution.

`python .cache/phase24p3/isolation_checks.py`: all six JS suites exit 0
(company, discovery, discovery_full_ai, phase24r, premium, shortlist_ui),
compileall app/tests/scripts and guarded runner PASS, git diff --check exit 0.
All **52 untracked app/tests/scripts/docs files** inspected (including both new
files): AST/JSON, merge markers, whitespace, SHA256 manifest at
`.cache/phase24p3/isolation-untracked-manifest.json`; no failures. One preexisting
official XML whitespace exception preserved. The isolated helper is a new ignored
copy with separate output names; prior helpers and .tmp-phase24* remain untouched.

## P24P.3.9A LIMITED admission checkpoint (2026-10-11)

**P3.8/P3.9 PARTIAL; P4 BLOCKED.** This section supersedes only the older
admission/event-loop/cancellation descriptions below; historical evidence remains.

Before: FastAPI parsed/validated controls, then H handler checked query bytes,
awaited session touch=False, membership/company and `_load` in the default pool.
Filter/signing/token/profile work, JSON expansion, up to two aggregates, Pydantic
output and serialization ran on the event loop. Final same-fence read preceded
independent session/membership/profile checks. Cancelled to_thread awaiters did
not stop workers. Startup built/injected runtime; shutdown only closed an owned
runtime. Repository pages acquire a connection before bounded_read, reauthorize
scope in the transaction, and load_history verifies the same fence twice plus a
final count; the handler repeats that load. No response-delivery storage lock.

After: HistoryRoute acquires immediately before FastAPI handler validation/auth
for all three H GET routes. Lifespan owns **two admitted operations and two dedicated
threads**. Normally one app per server process gives two per process; multiple
app instances/replicas have separate additive limits, NOT a global cap. Full or
closing admission rejects immediately: **503**, **Retry-After: 1**, **no-store**.
There is no admission waiting queue or worker submission at limit+1. Each lease
submits at most one operation at a time, so at most two submitted futures exist;
the executor queue cannot grow with incoming requests. Retry is a fixed suggestion,
not a completion ETA, fairness guarantee or per-tenant quota. Overload precedes
auth/validation and reveals no company existence.

Session lookup, membership/company, both loads, profile digest and `_calculate`
use this executor. Large JSON lexical checks/expansion, hashing, both aggregates,
Pydantic response construction and serialization execute in workers. A Response
contains only AnalyticsResponse.model_dump_json bytes, avoiding a second FastAPI
serialization; schema allowlisting is preserved. Small query/filter validation,
HMAC unseal and binding remain synchronous under existing query/token ceilings.
Admission covers response construction and final scope checks, not slow socket
sending. D/R/P capabilities and ordinary routes preserve their default executor
behavior. current_account's signature/touch contract stays unchanged. ContextVar
holds a lease only; lifespan tracks leases/futures, no credential/body cache.
Submitted auth calls transiently require normal inputs, not a global token store.

HTTP finally closes its lease. Close releases only when no submitted future is
pending. Shield prevents awaiter cancellation from cancelling that future; its
completion callback retrieves errors, removes it and releases only after actual
callable exit including repository cleanup. Cancellation stops further request
phases; no detached coroutine continues them. Pre-submit rejection, exceptions,
revocation/profile drift and normal completion unwind without slot leaks.
Lifespan closes admission, waits leases/workers and joins executor BEFORE owned
runtime/database close. **A stuck thread can make shutdown wait indefinitely.**
Forced event-loop/server/process teardown has no guaranteed worker cleanup here.
No timeout falsely frees a running worker's slot.

Cooperative ten-second deadline begins at admission, checked before/after each
worker phase. Handler's SQL/calculation budget also begins before initial auth.
Fingerprint phases, snapshot validation events, aggregate events/items,
serialization and final auth are checked; SQLite query_only/progress/busy guards
remain. Individual JSON/hash/model operations, connection acquisition, filesystem
IO and CPU cannot be forcibly preempted. Actual HTTP disconnect need not cancel
ASGI processing: tests prove disconnect-like coroutine cancellation, not live
transport behavior. Worker cancellation never means Python thread termination.

Existing ceilings remain: 16 KiB query; 500 events; 16 MiB combined stored JSON,
8 MiB one snapshot preflight; 5,000 occurrences/union; 200,000 lexical units,
depth 64 and 100,000 post-parse nodes/snapshot; 51 batches/load, two loads;
2 MiB serialized response. These are not hard peak-RSS limits. Python GIL/CPU
contention can still delay unrelated endpoints; barrier tests show responsiveness
while workers wait, not a general CPU/load benchmark.

SQLite-only bounded_read still rejects other backends before history SQL but after
connection acquisition/initial auth. Backend selection/migrations/network/scoring/
source crawling/UI are unchanged. Actual PostgreSQL pool/statement/cancellation
acceptance is untested. Hard CPU/RSS/wall-time needs separate process/OS isolation
with termination AND reap, including auth/acquisition. Retention and D/R/P,
P2/future consumer/browser blockers remain. P4/P5/widgets are not implemented;
no dev-only SQLite H rollout accepted. PRODUCTION_TOUCHED=False.

Verification: focused uses P39's nine p39-final-all-gates files plus runtime_gate
and analytics_admission; broad uses exact 57 p39-broad-final files plus those two.
No new exclusions/weakened assertions. Counts overlap. Measured results follow.

P3.9A measured focused evidence: `admission-focused` **335 passed**, exit 0,
234.14s, zero skips/deselections (nine documented focused files + runtime_gate
+ ten admission cases collected at start). `admission-extra-final` **13 passed**,
35.54s; final sleep-free barrier/owned-lifespan rerun `admission-barrier-final`
**13 passed**, 33.44s, exit 0, zero skips/deselections; `admission-lifespan-final` **1 passed, 12 deselected**, 5.52s, tests owned
runtime close after worker/executor join. Counts overlap. Initial repair runs
were 1 failed/60 passed (auth call signature), then 2 failed/8 passed (new fixture
profile type/settings constructor); both corrected without changing old assertions.
These failed exploratory runs are not acceptance evidence.

Six existing JS suites exited 0 using local Node/current dashboard_html:
company, discovery, discovery_full_ai, phase24r, premium, shortlist_ui.
`admission_checks.py`: compileall app/tests/scripts and runner passed; git diff
--check exit 0; 50 untracked app/tests/scripts/docs files inspected for AST/JSON,
merge markers/whitespace with SHA256 manifest at
`.cache/phase24p3/admission-untracked-manifest.json`. One existing official SDK
XML whitespace line preserved byte-faithfully. One existing Starlette warning.
No browser/live server/PostgreSQL result claimed.

`admission-broad`: **1489 passed, 2 skipped, 390 subtests passed**, zero
deselections, exit **0**, **481.93s**. Exact 57 documented P39 files plus
runtime_gate and analytics_admission (59 files). Skips remain only raw-deflate
checksum cases tests/test_source_http.py:805/:1000. Broad collected 13 admission
cases; final barrier-only handshake rewrite is additionally verified by the
13-case standalone rerun above. Production/runtime code did not change after
broad started. Selected offline regression is not whole-repository acceptance.

Recommended next checkpoint: bounded process/OS isolation with parent-enforced
CPU/RSS/wall limits, termination AND reap and auth/acquisition coverage; do not
open P4 from this thread-only evidence. PostgreSQL and browser remain separate
acceptance blockers.
Prior 48-file untracked SHA256 manifest comparison: no missing files, 44 unchanged;
only service, analytics_routes and the two gate documents changed intentionally.


## P24P.3.9A bounded admission checkpoint (2026-10-11)

**LIMITED improvement; P3.8/P3.9 PARTIAL; P4 BLOCKED.** Earlier sections below
record the pre-checkpoint implementation and results; this section supersedes
only their admission/event-loop/cancellation descriptions.

### Trace before and after

Before: FastAPI decoded/validated controls, then history handler checked raw query
bytes and awaited session touch=False, membership and company through default
`asyncio.to_thread`; small filter/signing/token/profile work ran on the event loop.
`_load` used that same default pool. JSON lexical checks, expansion, aggregate
(possibly twice), allowlisted Pydantic output and serialization ran on the event
loop. A final same-fence load preceded independent session/membership/profile
reauthorization. Cancelling any to_thread awaiter did not stop its running thread.

After: HistoryRoute acquires immediately before FastAPI handler validation/auth
for all three H GET routes. Admission is owned by create_app's lifespan, with an
explicit conservative **two admitted operations and two dedicated worker threads**.
One app per server process means two per process, NOT two globally across replicas;
multiple app instances have separate additive limits. There is no admission wait
queue and no worker submission on limit+1: safe **503**, **Retry-After: 1** and
**Cache-Control: no-store**. This is a fixed retry suggestion, not a completion ETA
or a fair/per-tenant scheduler. Capabilities D/R/P and ordinary routes keep their
existing behavior and default executor dispatch. Admission may return 503 before
an overloaded request's auth/validation; no company existence is disclosed.

Each lease submits at most one operation at a time. Thus the executor's internal
queue cannot grow with inbound requests: at most two submitted futures total.
Session lookup, membership/company, both history loads, profile hashing and the
whole `_calculate` phase use this executor. Small query decoding/filter validation,
HMAC token unseal and control binding remain synchronous and bounded by existing
query/token limits. Large JSON parsing/expansion, hashing, both aggregates, output
construction and one final serialization execute in workers. The returned Response
contains only AnalyticsResponse.model_dump_json bytes, avoiding FastAPI's second
serialization. The schema allowlist is still used to construct that response.
Admission covers response construction and final checks, not slow socket delivery.

A ContextVar holds only the request's lease, never credentials or bodies. The
lifespan holds leases/futures, not a token cache. Submitted calls transiently need
normal auth inputs, which are not retained as a global credential registry.
Nonanalytics current_account retains the same signature, touch behavior and
asyncio.to_thread fallback. Auth errors remain redacted.

### Cancellation ownership and cooperative limits

The HTTP task owns the lease until its finally block closes it. Each submitted
future is shielded from awaiter cancellation and owns the lease while running.
Close releases immediately only if there is no pending future; otherwise its
completion callback retrieves any exception, removes the future, and releases
only after actual callable exit (including repository connection cleanup).
There is no detached coroutine continuing the rest of a cancelled request.
Repeated cancellations cannot cancel the submitted future or release its slot.
Pre-submit rejection, ordinary errors, revoked membership/profile drift and
normal completion all unwind the lease. Tests release barriers in finally and
join/reap all worker work, including errors after cancellation.

Lifespan shutdown first rejects new admission, waits for existing leases and
workers, then joins its executor, BEFORE an owned runtime/database closes.
**Shutdown can wait indefinitely if a Python worker is stuck.** It is an orderly
join, not bounded forced termination; forced server/event-loop/process teardown
is not guaranteed. No timeout falsely releases a still-running worker's slot.

A cooperative ten-second deadline starts at admission, checked before/after each
dispatched phase; the history handler also starts its SQL/calculation budget before
initial authorization. SQLite statements retain query_only/progress/busy guards;
loads check around fingerprinting, snapshot validation checks each event,
aggregation checks each event/item, and serialization/final auth are checked
before success. Neither a deadline nor HTTP cancellation forcibly interrupts
one Python JSON decode/hash/model operation, connection acquisition, filesystem IO
or CPU execution. An actual transport disconnect may not cancel the ASGI handler;
we prove disconnect-like coroutine cancellation, not live-server disconnect.

Existing ceilings remain: raw query 16 KiB; 500 events; 16 MiB combined stored
JSON and 8 MiB one snapshot preflight; 5,000 occurrences/union; 200,000 lexical
units and depth 64; snapshot walk 100,000 nodes; 51 batches/load, two loads;
2 MiB serialized response. None is a hard peak-RSS ceiling. Two workers limit
multiplication but Python GIL scheduling/CPU contention can still delay other
endpoints. Barrier tests prove unrelated routes can complete while workers wait,
not a general CPU latency/load benchmark.

SQLite-only bounded_read still rejects non-SQLite connections before history SQL,
after connection acquisition and initial auth. Backend selection, schemas,
migrations, network, scoring, source crawling and UI are unchanged. Real PostgreSQL
pool/statement/cancellation acceptance remains untested. Hard CPU/RSS/wall-time
requires a separately accepted process/OS isolation checkpoint with termination
AND reap, including auth/connection work. P2 and future H consumer browser
acceptance remain pending; retention and D/R/P limitations remain unchanged.
P4 charts/P5/widgets are not implemented or authorized; no dev-only H rollout
policy has been accepted. PRODUCTION_TOUCHED=False.

### P3.9A measured verification

Results are recorded below after the guarded runs finish. Focused selection is
P39's nine `p39-final-all-gates` files plus runtime_gate and analytics_admission;
broad is its exact 57 `p39-broad-final` files plus those two files. No new exclusions
or weakened old assertions. Selections overlap and must not be summed.


**P3.8/P3.9 PARTIAL; P4 BLOCKED. Recommendation (b): further backend checkpoint.**
This does not authorize development-only charts. No charts were implemented.
Earlier compatibility evidence and uncommitted work remain intact.

## Actual request and storage path

FastAPI async history handlers first validate the new 16 KiB raw query ceiling,
then await session lookup (`current_account(touch=False)`), membership and company
lookup using `asyncio.to_thread`. The ten-second deadline begins only after initial
authorization, controls/token verification and profile hashing. `_load` runs in
the default executor. Repository pages acquire a connection BEFORE `bounded_read`.
Each page rechecks membership/company inside its transaction. `load_history`
performs an original pass, same-fence verification pass and final count check;
the handler later repeats the entire load and fingerprint before independent
session/membership/profile reauthorization. These are optimistic observations,
not a storage lock persisting through response delivery.

`ApiRuntime.build_runtime` constructs one `Database` from parsed settings and
passes it to repositories/services. `database_for` preserves that object;
`TenderRepository._connect` calls `Database.connect`. SQLite selection creates
a file connection with timeout=10 and foreign keys enabled. PostgreSQL selection
opens the pool and calls getconn with configured pool_timeout; there is no SQLite
fallback. Analytics `bounded_read` rejects a non-SQLite connection before its
history transaction, but AFTER acquisition and AFTER initial authorization.
Thus fail-closed history SQL is not proof that PostgreSQL connection/auth work
was avoided. No settings values, credentials or real DB were inspected here.

## Proven ceilings and their exact limits

Existing SQLite preflight limits selected history to 500 events, 16 MiB combined
snapshot/source-list UTF-8 bytes and 8 MiB per snapshot before fetching bodies.
It scans up to 501 matching rows with scalar byte lengths; existing scope index
plan coverage is fixture evidence, not a storage-size-independent latency proof.
Selected body pages fetch at most 21 rows. Query-only mode blocks writes; busy
timeout derives from remaining budget and progress callback checks every 1000 VM
instructions. Filesystem stalls and connection acquisition are not preempted.
Each load allows 51 repository calls; two handler loads allow 102.

This checkpoint adds a constant-extra-state lexical scan before JSON object
expansion: nesting at most 64 containers and at most 200,000 structural units
(container starts, string starts, commas, colons) cumulatively across all four
JSON fields of all selected events. Quoted/escaped punctuation does not count.
It is a conservative complexity ceiling, not a grammar validator or an exact
memory bound. Existing strict JSON parsing still rejects syntax errors, duplicate
keys and nonfinite values; the post-parse snapshot walk retains its 100,000-node
per-snapshot ceiling. The scan is synchronous and linear in already bounded text.
It precedes parsing, but not `_load`'s retained strings and fingerprint hashing.
The new raw query ceiling returns 422 before authorization dispatch inside the
handler; ASGI/server query decoding and FastAPI validation have already happened.
No request-body, header, transport or overall HTTP-memory bound is claimed.

Existing 5,000 item-occurrence/union ceiling is checked before aggregation for
snapshot items, and after aggregation for stored counters/union. JSON parsing of
one bounded snapshot still precedes its item count check. The 2 MiB response
ceiling is checked AFTER Pydantic construction and JSON serialization; FastAPI
serializes again after the handler returns. It is not a peak-memory ceiling.

## Remaining architectural blocker

Validation, JSON decode/expansion, pure aggregation (potentially twice), item
serialization, SHA256/HMAC, profile digest, output construction and serialization
run synchronously on the event loop. They have finite input ceilings but no hard
CPU/RSS ceiling and can delay unrelated endpoints. A timer check after completion
does not preempt them. Initial and final auth connection/crypto work is outside
the SQLite statement guard. No performance/load benchmark is claimed.

There is no analytics admission limiter or bounded dedicated worker queue.
Overlapping requests can multiply retained data and enqueue default-executor
work shared with unrelated routes. No explicit disconnect polling exists here;
client abort does not prove cancellation of processing. Task cancellation while
awaiting to_thread does not terminate a running worker; synchronous calculation
cannot observe cancellation until it yields. No new limiter/token ownership is
introduced, so no cancellation-release proof is asserted. Existing tests of
concurrent mutation, revocation, profile drift and foreign organizations prove
authorization/commitment handling, not overlapping-load or worker termination.
The new deterministic overlap/cancellation test exercises `to_thread` with
`BoundedHistory`: both workers enter, one awaiter is cancelled, both workers
remain alive until the test explicitly releases them. It uses events, not sleep
ordering, and joins cleanup. It does not simulate an HTTP transport disconnect.
These unmet criteria keep this checkpoint PARTIAL despite green regressions.

## Narrow next checkpoint design

Authorize a backend-only design/implementation checkpoint for an app-lifespan-owned
analytics executor/admission component with immediate rejection when full and no
waiting queue. Admission must cover initial/final authorization and worker lifetime;
on coroutine cancellation a submitted worker retains its slot until actual exit.
Test overlapping callers, exceptions, disconnect/cancellation before and after
submission, shutdown, revocation and profile changes with barriers/events and
synthetic SQLite fixtures. Move bounded calculation off the event loop and check
deadlines at phase/event boundaries; call this cooperative protection only.

If policy requires hard whole-request CPU/memory termination, use a disposable
process per admitted job (bounded concurrent processes, no queued jobs) with
parent-enforced wall deadline and OS memory/CPU controls, termination AND reap
before releasing the slot, and independently reauthorize in the parent before
return. Establish platform-specific acceptance; a thread timeout is insufficient.
Do not pass secrets/raw errors to responses or relax scope/read-only rules.
Connection/auth isolation must be included before claiming whole-request limits.
PostgreSQL remains a separate authorized disposable-server acceptance checkpoint:
real driver/pool, acquisition/statement cancellation, query-only transactions,
scope/replay/drift and cleanup evidence. Mocks do not substitute for that proof.

D/R/P positive analytics paths remain unavailable; industry crosswalk, durable
retention/lost-byte recovery and published TED context integration remain outside
this H gate. P2 browser acceptance and future H consumer/browser acceptance remain
pending. No production, full-platform or PostgreSQL readiness is asserted.
All analytics routes remain GET-only; existing read-only, source/scoring prohibition,
safe errors, session/token and tenant tests remain required regressions.

## Measured verification

`runtime-gate-focused`: 324 passed, 0 skipped/deselected, exit 0, 209.07s;
the nine P39 focused files plus `tests/test_analytics_runtime_gate.py`. It loaded
the ten new guard cases before the final overlap test was added.
`runtime-gate-cancel`: all 11 current new cases passed, 0 skipped/deselected,
exit 0, 6.73s. Counts overlap and must not be summed.

`runtime-gate-broad`: **1476 passed, 2 skipped, 390 subtests passed,
0 deselected, exit 0, 440.96s**. It repeats P39's exact 57 explicit files plus
the new runtime-gate file (58 files), no -k or added exclusions. Skips are exactly
tests/test_source_http.py:805 and :1000: raw deflate has no checksum.
This is selected offline regression, not full-repository acceptance. PostgreSQL
foundation/harness entries remain mocks/SQLite/SQL tests, not server verification.

Six current-dashboard local JS suites passed individually, exit 0: company,
discovery, discovery_full_ai, phase24r, premium, shortlist_ui. compileall of
app/tests/scripts and git diff --check passed. Separate untracked inspection
covered 48 files under app/tests/scripts/docs (AST/JSON/merge markers/whitespace
and SHA256 manifest). One preexisting copied SDK XML comment whitespace remains
byte-faithful. Helper/manifest names use `runtime-gate` under .cache/phase24p3.
One existing Starlette TestClient/httpx warning. No browser acceptance claimed.

All tests use offline fixtures. No dependency installs, external network, Docker, real DB migration,
secret inspection, staging, commit, push or deployment. Prior `.tmp-phase24*`
directories were not opened or modified. PRODUCTION_TOUCHED=False.

Reproduction: use `.cache/phase24p3/run_tests.py runtime-gate-broad` with the
57 file arguments in P39's documented `p39-broad-final` command, followed by
`tests/test_analytics_runtime_gate.py`. Focused selection uses the nine file
arguments in `p39-final-all-gates` plus that new file. Standalone new cases:
`python .cache/phase24p3/run_tests.py runtime-gate-cancel tests/test_analytics_runtime_gate.py`.
Local JS/artifact helper: `python .cache/phase24p3/runtime_gate_checks.py`.


## P24P.3.9D bounded offline real-H fixture spike (2026-10-11)

**Local development only. P3.9 PARTIAL; P4 full rollout BLOCKED.**
This appendix supersedes the earlier synthetic-only next-step recommendation,
without changing previous reports. HEAD 93f02eb / phase24-professional-saas-core.
The independently tested P39B synthetic prototype remains unchanged and unwired.

Delivered NEW `app/analytics/offline_fixture.py`, `offline_spike.py`,
`offline_worker.py`, `tests/test_analytics_offline_spike.py` and the pinned
`tests/fixtures/p39d_offline_history.json`. This is the explicitly permitted
fixed-fixture fallback, NOT a general trusted-history/process/API bridge.
`FixtureSpike().run('normal')` actually calls existing `aggregate_history()`
in a short-lived Windows Python child. The guarded pytest command below is
an executable offline demonstration. No analytics/admission/API/UI wiring.

Parent accepts only seven fixed fixture names; it checks pinned SHA256 bytes
and explicit organization 7/company 33 before constructing H. The child receives
versioned JSON DATA: one fixture event, fixed profile digest, UTC as_of,
Europe/Rome, 7-day deadline window, [start,end) history interval and a fixed
optional identity filter. No sessions/cookies/keys/connection strings/raw source
errors, environment contents or executable code are sent. Strict parsing rejects
duplicate keys, nonfinite/invalid JSON, overflow, extra fields, version/type,
identifier/profile/time/filter/provenance/score changes and duplicate events by
canonical equality to the independent pinned fixture. Scope labels and H evidence
are NOT client authorization; this adapter intentionally refuses arbitrary history.

Fixture scores 80 and 0 were generated by existing `_discovery_item()` and its
metadata scorer under the unchanged offline runner; no scores/formula were
fabricated or rewritten. Fixed timestamps stabilize provenance/enrichment.
Unknown removes scoring; legacy removes provenance; foreign/future intentionally
alter evidence, never the score. Exact direct trusted aggregate versus child
parity covers all six complete Metric records (value/numerator/denominator/
identities/reasons), population/scope, unknown/current fit, deadline grouping,
timezone/as_of/history bounds and selected identities. Normal KPI values are
4 / 2 / 2 / 1 / 1 / 1 in Discovered/Matched/High Fit/Active Sources/Countries/
Closing Soon order. Zero is eligible; unknown is unavailable with denominator 0.
Legacy/foreign/future cannot become current fit. Repeated result JSON is stable.
Outputs are allowlisted; stored items/titles/URLs/raw errors/tokens are excluded.
Input <=48 KiB, output <=24 KiB; actual inputs 837..15903 bytes, result JSON
3654..4798 bytes. The 32677-byte fixture is itself bounded before JSON decoding.

Worker uses the same base Python with -I -S, no site/.pth startup, an explicit
trusted installed Pydantic dependency directory, only SystemRoot in environment,
closed unrelated handles and stderr DEVNULL. Audit restrictions are installed
before application/dependency imports: dotenv opens, all socket/DNS events and
subprocess spawning are denied. In-child synthetic audit probes verify denial;
no secrets were opened and no external network attempt was made by those probes.
Importing existing service also loads source package definitions through their
existing __init__; no fetching or rescoring is invoked. This is NOT an OS file/
network security sandbox and uses the ordinary user token, not a restricted token.

Job limits are set/read back: one active process, kill-on-close, 128 MiB PROCESS
COMMITTED memory. Successful seven-case regression measurements: peak commit
35090432..35799040 bytes; peak working set 45592576..46178304 bytes. Evidence
is appended in `.cache/phase24p3/p39d-memory.jsonl` (last seven case records).
128 MiB is a deliberately finite development ceiling with >3x observed commit
headroom for this tiny fixture; 64 MiB synthetic coverage was not assumed adequate.
These runs prove runtime compatibility under the selected cap, not a maximum
production workload or hard RSS/CPU/parent-memory bound. No memory stress run.
Cap/import/setup failures fail closed; there is no uncapped retry/fallback.

**Residual startup blocker is concrete:** both old prototype and new spike call
Popen without CREATE_SUSPENDED, then AssignProcessToJobObject. Assignment-at-
suspended-start is NOT implemented or verified. No real process isolation or
whole-request guarantee is claimed. Parent fixture loading/direct reference,
Popen, synchronous pipe write and up-to-five-second reap are not preempted by
the polling deadline. Parent compares output to its exact trusted pure reference;
it does not authenticate a user. No DB/acquisition/auth isolation, HTTP disconnect,
restricted token, CPU quota, global admission, maximum RSS or PostgreSQL proof.
Future API integration MUST independently reauthorize session/membership/company/
profile in the parent at final delivery; fixture hashes cannot replace that.

### P39D measured evidence (counts overlap; do not sum)

- `python .cache/phase24p3/run_tests.py p39d-baseline tests/test_analytics_process_isolation.py tests/test_analytics_service.py`:
  **85 PASS, 0 FAIL/SKIP/deselected, exit 0, 21.07s**, before edits.
- `python .cache/phase24p3/run_tests.py p39d-targeted-final tests/test_analytics_offline_spike.py --tb=short`:
  **43 PASS, 0 FAIL/SKIP/deselected, exit 0, 7.74s**.
- `p39d-regression`: **372 PASS, 0 FAIL/SKIP/deselected, exit 0, 203.81s**;
  one existing Starlette/httpx warning, ten files including existing API/service/
  admission/process/runtime/compatibility/history/fit/date plus the new spike.
  Exact command: `python .cache/phase24p3/run_tests.py p39d-regression tests/test_analytics_offline_spike.py tests/test_analytics_process_isolation.py tests/test_analytics_admission.py tests/test_analytics_runtime_gate.py tests/test_analytics_api.py tests/test_analytics_compatibility.py tests/test_analytics_service.py tests/test_company_history_paging.py tests/test_analytics_fit.py tests/test_analytics_dates.py`.
- `python .cache/phase24p3/p39d_checks.py`: exit 0; six existing JS suites each
  exit 0 (company/discovery/discovery_full_ai/phase24r/premium/shortlist_ui),
  compileall all four new Python files PASS, git diff --check exit 0. No browser.
- New tests exercise real children for parity, pipe corruption/oversize/version/
  untrusted claims, redacted failure, initialized timeout, event-barrier repeated
  cancellation, admission rejection, shutdown/slot reuse, assignment failure and
  kill/wait/reap; owned PIDs are checked exited and handles/slots closed.
  Validation-only cases do not claim actual child execution. No assertions weakened.
- Exploratory runs were NOT acceptance: first 13 FAIL/26 PASS/4 setup ERROR
  (date JSON serialization and overly long pytest parameter IDs); next 1 FAIL/
  6 PASS (existing service requires frozenset filter). These adapter/test defects
  were fixed; then intermediate 41 PASS before final two lifecycle tests.

Preservation: 399 preexisting tracked/untracked files and original byte prefixes
of the three appended docs verified by SHA256, unchanged. Prior .tmp-phase24*
were not opened or modified. Manifest preparation inadvertently hashed two
tracked example templates `.env.example`/`.env.public.example` outside the runner;
no contents printed, actual .env not accessed. Those templates were excluded
from subsequent checks, which use the unchanged guarded runner. This deviation
is recorded rather than claiming zero dotenv-template access. No network/install/
Docker/elevation/live DB/migration/staging/commit/push/deploy; changes uncommitted.

ONE next checkpoint: an opt-in fixture-only LOCAL H charts preview consuming
this verified output, with a separate entry point disabled by default, bind ONLY
127.0.0.1/::1, disposable SQLite query-only fixture storage if needed, and tests
for default-off/non-loopback refusal, read-only/no-secret/no-network operation,
all-six-KPI/unknown/date/filter display and context invalidation. Actual PostgreSQL
is NOT required to draft/run this local fixture preview. No production app entry
or existing HTTP route is to be wired; broader P4 gate remains independently
blocked pending accepted safety policy/runtime/auth evidence. No chart code now.
PRODUCTION_TOUCHED=False.
