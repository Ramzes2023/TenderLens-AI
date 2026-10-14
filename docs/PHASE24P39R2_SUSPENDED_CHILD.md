# P3.9R2: suspended Windows child candidate

Production bridge remains **BLOCKED**. Disabled by default; explicitly instantiate
`SuspendedChild(enabled=True)`. This offline repair changes only the two R2
files and this note; production wiring is unchanged.

Uses existing process_isolation WinAPI bindings, error checks and Job structures:
kill-on-close, one active process, 64 MiB process committed-memory limit, verified
by readback. `_winapi.CreateProcess` returns the primary thread handle with
CREATE_SUSPENDED; assignment and IsProcessInJob verification precede ResumeThread.
No normal-Popen fallback. Fixed base Python image, -I -S, fixed synthetic script,
three allowlisted modes, no inherited handles, only SystemRoot environment.

New tests require real Windows: kernel suspend count before assignment, no ready
event before resume, controlled completion (exit 7), running cancellation,
initialized timeout, malformed completion, assignment/start failure cleanup and
exact parent handle balance. Duplicate process handles independently prove kernel
signaling after cleanup; PID or cancelled-future observations are insufficient.
Every child is owned and cleanup is in finally. Non-Windows explicitly skips.

R2 repair: successful Job termination now waits on the original owned process
handle before considering TerminateProcess. Both waits share a three-second
cleanup budget (up to one second for the Job, then the remaining budget for the
fallback). ERROR_ACCESS_DENIED (5) from TerminateProcess is accepted only after
the same owned process handle signals. An unsignaled process or failed wait
raises and retains ownership for retry. Terminal close is idempotent.

Handle instrumentation warms asyncio, UUID, path resolution and mock/exception
machinery once before counting, and requires an exact balance on a second
runtime-only pass. Both per-case snapshots collect reference cycles; acceptance
remains exact, with no tolerance. The fixture also checks all tracked children
released their handles and reaped every created process. Cancellation, timeout
and malformed runs repeat three times with exact balance after each; successful
operations repeat five times inside one loop with independent kernel proof
handles closed each time. New access-denied regressions use actual owned process
handles to prove both signaled acceptance and live-process rejection.

Reported host result before this repair: 2 failed, 6 passed, 4 fixture errors;
the cancel/timeout failures were terminate_owned_winerror_5. The immediate
post-Job TerminateProcess call raced asynchronous termination. The reported
parent handle growth, including a no-spawn case, is not yet proven to be runtime
initialization rather than a leak: the revised exact checks must settle that on
the host. No repaired Windows PASS or persistent-growth proof is claimed here.

Observed for this repair: Python/pytest commands, `.venv/Scripts/python.exe`
and `venv/Scripts/python.exe` were not available in this sandbox. No alternate
interpreter was searched for or installed, and no test command was launched.
**No pytest executed; no Windows PASS claimed.**
Host launcher must run once with its existing venv:
`python -B -m pytest -p no:cacheprovider tests/test_p39r2_suspended_child.py -q`
Only this new targeted suite is authorized. Expected bounded runtime <40 seconds;
observed runtime and counts remain pending. Existing R1 xfail stays unchanged.

Limitations: ordinary user token; no OS network/file sandbox, hard RSS or CPU
quota. Synthetic exit/event protocol is not analytics or authenticated PostgreSQL
proof. Startup WinAPI calls and up to 3-second synchronous reap are not preempted
by the async deadline. Cleanup failure retains handles for retry and raises;
there is no unsafe release/retry without limits. Same-owner use is required.

Remaining P3.9 gate: real HTTP disconnect plus PostgreSQL acquisition/statement/
pool cleanup and full initial/final authorization resource proof. Python threads
cannot be killed by cancelling their waiter. Next one engineering task: host-run
this targeted Windows kernel suite and resolve any concrete failures before any
separate integration checkpoint. PRODUCTION_TOUCHED=False.
