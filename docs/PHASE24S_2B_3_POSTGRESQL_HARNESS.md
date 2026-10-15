# Phase 24S.2B.3 PostgreSQL harness readiness

## Separate real audit from normal Windows PowerShell

Use the existing isolated container only. Never create, remove or reconfigure containers.
Set VALYQON_PG_TEST_CONTAINER_ID to its independently verified full 64-character ID.
Set VALYQON_PG_TEST_ADMIN_URL through a secure prompt; never place credentials in
argv, shell history, documentation or chat. Required endpoint: 127.0.0.1:64628,
maintenance database postgres. Query options, localhost and ambient PG* are refused.
The explicit --confirm-local-test-server opt-in is also mandatory.

    $env:VALYQON_PG_TEST_CONTAINER_ID = Read-Host 'Full existing isolated container ID'
    $auditSecret = Read-Host 'Test PostgreSQL URL' -AsSecureString
    $auditPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($auditSecret)
    try {
        $env:VALYQON_PG_TEST_ADMIN_URL = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($auditPointer)
        & 'C:/Users/ramze/Documents/Codex/tender-ai/.venv/Scripts/python.exe' -B scripts/validate_phase24s2b3_postgresql.py --confirm-local-test-server
        $auditExitCode = $LASTEXITCODE
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($auditPointer)
        Remove-Item Env:VALYQON_PG_TEST_ADMIN_URL -ErrorAction SilentlyContinue
        Remove-Item Env:VALYQON_PG_TEST_CONTAINER_ID -ErrorAction SilentlyContinue
        $auditSecret.Dispose()
    }
    if ($auditExitCode -ne 0) { throw 'PostgreSQL audit failed.' }

## Docker Desktop NAT controls

The harness pins the local Windows engine npipe:////./pipe/docker_engine explicitly;
Docker context and DOCKER_HOST cannot redirect inspection.
Only docker container inspect FULL_ID and read-only docker exec FULL_ID are used.
No other containers are listed, inspected or modified. JSON inspection uses no
Go templates or shell; all Docker output/errors are captured and never printed.

The single inspect record must match the complete ID, be running and not restarting,
have label valyqon.test=phase24s2b3 and Config.Image exactly postgres:16-alpine.
This matches the existing valyqon-s2b3-test-e89b6dacd2 container; postgres:16,
other Alpine tags, custom images and wildcard matches are refused.
Host/container networking, privileged mode and PublishAllPorts are refused.
Configured HostConfig.PortBindings must contain exactly one 5432/tcp binding with
HostIp="127.0.0.1" and HostPort either "64628" or "". The empty string is Docker's
automatic-port configuration from --publish 127.0.0.1::5432.
Actual NetworkSettings.Ports must still contain exactly 5432/tcp -> 127.0.0.1:64628.
Other configured or actual ports, addresses, extra bindings and extra published
ports are refused; an empty actual HostPort is also refused. Full container ID,
exact image, label, cluster identity and every other guard remain mandatory.

Read-only pg_controldata /var/lib/postgresql/data with LC_ALL=C on that exact container
must report catalog version 202307071 (PostgreSQL 16).
The Alpine image requires no change to the PostgreSQL 16 catalog version,
pg_controldata command, data directory or SQL cases. LC_ALL=C keeps control
output parsing independent of locale; the audit does not require Bash,
Debian utilities or distribution-specific collation ordering.
Its database system identifier must equal SQL pg_control_system().system_identifier.
SQL uses host(inet_server_addr()) and host(inet_client_addr()) to return plain IPs.
Casting inet to text includes CIDR suffixes (such as /32), which Python
ipaddress.ip_address() rejects. An offline regression asserts the complete identity
query and verifies plain server and Docker Desktop NAT client addresses. All existing
identity and security checks remain unchanged.
SQL also requires major 16, database postgres, and a server address found in that
container's inspected network addresses. The client may have a Docker Desktop NAT
address; unspecified and multicast addresses are refused. Loopback alone is never proof.
The entire container preflight is repeated before CREATE and must return the same identity.
Missing Docker, denied permissions, custom image/data layout or mismatches fail closed.

The test role needs CREATE DATABASE, cleanup rights and access to pg_control_system()
(normally the isolated container's postgres role). No Python -O.
Trusted local Docker administration and independently verified container ID are assumed.
A malicious Docker administrator or physical clone with the same system identifier
is outside this boundary. A small check-to-CREATE race remains: do not restart or
reconfigure the container during the audit.

## Dependencies

The existing venv was checked: psycopg and psycopg_pool are BOTH absent.
Nothing was installed. Minimal operator step, using an approved package source:

    & 'C:/Users/ramze/Documents/Codex/tender-ai/.venv/Scripts/python.exe' -m pip install 'psycopg[binary]>=3.2,<4' 'psycopg-pool>=3.2,<4'

## Offline verification

Plain-IP SQL fix verification: 261 passed, zero failed, zero skipped, zero
deselected, one existing Starlette/httpx warning; 103 harness tests. The complete
focused set below ran with dotenv restricted to the synthetic settings.env inside
a unique Windows TEMP basetemp. Harness, harness tests and unchanged PostgreSQL
cases passed syntax checks; git diff --check and separate whitespace checks for
the three untracked target files passed. No real Docker/PostgreSQL execution.

Complete focused set: test_postgresql_phase24s2b3_harness.py, test_synchronous_usage.py,
test_quotas.py, test_jobs.py, test_postgresql_foundation.py.
Automatic-port fix result: 260 passed, zero failed, zero skipped, zero deselected,
one existing Starlette/httpx warning; 102 harness tests. The previous baseline was
213 passed; 47 added cases cover automatic-port acceptance, existing identity
guards with automatic ports, spoofed configured/runtime mappings and unresolved
runtime ports. Configured and runtime bindings use independent test fixtures.
test_environment_overrides_dotenv_and_redacts passed in this full run.

Use a unique Windows TEMP basetemp and -p no:cacheprovider. Keep real project .env
physically secured outside the repository. Synthetic settings.env is not a project secret.
The engineering run patched dotenv.load_dotenv before importing pytest: only an explicit
settings.env resolved underneath that unique basetemp was allowed. All other calls returned
False without opening files. PYTHON_DOTENV_DISABLED was removed only for the allowed fixture
call and restored immediately. This also handles harness.main setting it globally.
No tests or implementation files were changed to accommodate this dotenv isolation.
Python syntax checks passed for the harness, its mocked tests and the unchanged
PostgreSQL cases. git diff --check passed; the three updated, currently untracked
files were also checked separately for whitespace errors.

## Coverage and cleanup

Real cases cover migrations 1-13 and repeat checksums, daily/monthly/outstanding quotas,
12 threads and 8 spawned processes per quota, UTC windows, tenant and membership scope,
roles, cancellation/deadline/release/expiration, gateway retry with synthetic providers,
and durable-job independence, scoped lifecycle, leases, recovery and idempotency.
Offline SQLite and process doubles do not prove PostgreSQL SQL, locking or real IPC.

Writes target only a new valyqon_p24s2b3_test_UUID database created with template0.
Cleanup requires its exact generated name and saved OID; no prefix discovery.
DROP WITH (FORCE) touches only that database. Failed cleanup prevents PASS.
Crashes or uncertain CREATE can leave that one database for separately verified manual cleanup.
The container is never deleted.

Real PostgreSQL execution remains BLOCKED pending dependencies and a separate operator audit.
Real PASS requires exit 0 and the final integration-and-cleanup PASS message.
No Docker, PostgreSQL or external APIs were executed in the engineering session.

## Four-file summary

- scripts/validate_phase24s2b3_postgresql.py: pinned Docker preflight, NAT-aware cluster identity.
- tests/test_postgresql_phase24s2b3_harness.py: mocked NAT, forged identity and invalid-ID guards.
- tests/postgresql_phase24s2b3_cases.py: unchanged; syntax checked.
- docs/PHASE24S_2B_3_POSTGRESQL_HARNESS.md: corrected operator and readiness instructions.

All 12 pre-existing implementation files and other uncommitted changes are preserved.
Existing .tmp-phase24s2b-* directories are untouched. No commit, push, merge or deployment.
