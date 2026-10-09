# Phase 24S.2B.1: legacy API authentication remediation

## Audited contracts

- Legacy `/api/v1` company, tender history/detail, scoring, RAG, monitoring,
  and PDF routes use `_protected` -> `require_api_or_session` and
  `resolve_owner` before accessing owner data.
- A valid session takes precedence over the integration header. Its account
  determines the personal owner; explicit mismatches return 403. Existing
  browser origin checks apply to session writes.
- The legacy configured key authenticates an integration, but configuration
  contains no credential-to-owner mapping. Previously an absent key disabled
  authentication, and a matching key could select arbitrary personal owners.
- Organization APIs require their own session/membership authorization.
  The legacy owner resolver also rejects the reserved organization namespace.
- `/health`, public pages, and authentication entry points have separate access
  contracts; their routing and dependencies are unchanged.

## Minimal remediation and intentional compatibility changes

- Missing, empty, or whitespace-only configured keys no longer enable anonymous
  legacy access. Without a valid session or a matching nonblank configured key,
  protected requests return 401.
- Owner resolution independently verifies integration authentication when there
  is no session. A configured shared key has no personal owner scope, so
  personal-owner requests return 403, including reads and writes. Reserved
  organization owners retain their existing 403 response.
- Authenticated ownerless scoring remains supported with the configured key.
  A valid session continues to resolve its own owner, including when the
  integration key is absent or an unrelated key header is present.
- Legacy integrations that supplied `owner_user_id` must use a valid owner
  session. No new owner-scoping configuration or migration is introduced.
- API regression fixtures now authenticate with real local sessions instead of
  relying on anonymous access. Cross-owner assertions require 403; a separate
  same-owner missing-record assertion retains 404 coverage. The previous test
  permitting key-only arbitrary-owner access now asserts denial.

## Verification

Offline tests cover all ten legacy owner route/method combinations, anonymous
reads/writes, invalid sessions, absent/blank/configured keys, key-only personal
owner denial, session/header precedence, cross-owner denial, session creation
and scoring, ownerless integration scoring, public health, and owner resolution
without a route authentication dependency. Existing organization isolation and
session-origin security tests are included in the focused run.

Python is invoked from PATH. External socket connections are blocked in the
test process; loopback is allowed for Windows asyncio's internal socket pair.
Dotenv file loading is disabled. For the full regression, synthetic dotenv
content written by tests to temporary `*.env` files is captured at write time
and parsed from memory to preserve existing precedence tests; no dotenv file
is opened for reading. The full runner is a temporary Python file with a
guarded entry point so Windows multiprocessing tests execute unchanged.
No security assertions or skip directives were weakened or added. The host's
existing symlink-privilege skip remains a verification limitation, recorded
explicitly below; no successful execution of that check is claimed.

Focused command: `pytest -q tests/test_api.py tests/test_session_access.py
tests/test_phase17_security_hardening.py tests/test_organization_api.py
tests/test_organization_companies.py tests/test_organization_data.py
tests/test_organization_pdf_rag.py tests/test_no_company_guard.py`, invoked
through the offline Python harness described above.

- Focused: **70 passed, 390 subtests passed, 1 warning**, exit **0**;
  **141.60 seconds**. No skipped tests. Warning: existing Starlette/httpx
  TestClient deprecation.
- `python -m compileall -q app tests`: exit **0**.
- `git diff --check`: exit **0** (Git emits LF-to-CRLF conversion notices).
- Full offline regression: **1178 passed, 5 skipped, 440 subtests passed,
  1 warning**, exit **0**, **299.83 seconds**. Command:
  `python -u %TEMP%/valyqon_phase24s2b1_offline_runner.py -q -rs -o
  faulthandler_timeout=45 tests`.
- Four existing Node-dependent skips were subsequently executed using the
  already installed local Node **v24.19.0** added to the process PATH:
  **4 passed, 1 warning**, exit **0**, **8.12 seconds**. Exact checks:
  `test_phase24r_browser_behavior`, `test_discovery_browser_contracts`,
  `test_company_profile_ui_preserves_constraints`, and
  `tests/test_telegram_ui_js.py`.
- The remaining existing skip is
  `tests/test_rag_ingestion.py::test_symlink_escape`: Windows symlink privilege
  unavailable. Its assertions and skip directive are unchanged. All other
  collected tests executed successfully across the full run and Node rerun.

Verification harness corrections: an initial all-socket block also blocked
Windows asyncio's internal loopback socket pair; it was narrowed to external
connections. Inline full-suite runners stalled at Windows multiprocessing
manager startup and were interrupted (exit 1, no complete suite summary).
The unchanged concurrent owner-isolation test passed with the file-backed
runner: **1 passed**, exit **0**, **8.33 seconds**. An initial memory-only dotenv
harness omitted synthetic `settings.env`; the unchanged precedence test passed
after extending write-time capture: **1 passed**, exit **0**, **0.83 seconds**.
The new session-write fixture also needed distinct company names between
configuration cases; its success assertions remain intact.

## Remaining limitations

Personal-owner integration operations are intentionally unsupported until an
explicit credential-to-owner authorization model is designed. The shared key
still authorizes ownerless scoring against the configured fallback profile.
Authentication-storage failure retains its existing fail-closed 503 response;
an unavailable store is not treated as an anonymous authenticated request.
No production, external integration, or deployment verification is claimed.
No Phase 24S.2C work is included.
The pre-existing symlink-escape regression could not execute on this Windows
host, so that security check remains unverified here. No host privilege or
system configuration changes were made to bypass the limitation.
