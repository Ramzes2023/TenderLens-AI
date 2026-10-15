# VALYQON AI personal preview — host verification pending

2026-10-13. Branch audited: `phase24-professional-saas-core`.
**Public release / P3.9: BLOCKED.** This is a private, synthetic-data preview,
not a production deployment or a marketing-ready release. No SSH, remote action,
external HTTP call, live email, billing, production DB or existing deployment was
used by this delivery. Existing user edits were retained; nothing was staged or committed.
No applicable AGENTS.md was found in the workspace or checked parent directories.

## Existing source reused

| URL / capability | Existing implementation | Preview behavior |
| --- | --- | --- |
| `/` | `app/api/landing.py`, `routes.py` | Actual guest website, accessible without authentication |
| `/login`, `/register` | `auth_pages.py`, `auth_routes.py` | Real password authentication and registration |
| `/verify-email` | Existing page and verification API | **One-time email link**, not a numeric OTP/code |
| `/forgot-password`, `/reset-password` | Existing pages and reset API | One-time password-reset email link |
| `/dashboard` | `dashboard.py`, `saas_shell.py`, existing JS/CSS | Authenticated SaaS workspace; guest redirected to login |
| Organizations and companies | Existing auth/organization/company repositories and routes | Genuine isolated workspace creation and persistence |
| Company PDFs, Discover, scoring, Saved, analytics | Existing services/assets preserved | Local capabilities retained; external AI/tender retrieval is disabled here |

The current auth core uses scrypt passwords, random opaque sessions, hashed
verification/reset tokens, atomic single-use consumption, 30-minute link expiry,
resend cooldowns, same-origin checks and route/client/identifier rate limits.
Password reset revokes existing sessions. Authentication and tenant checks remain
mandatory. Fresh databases start accounts unverified; no legacy customer DB is copied.
Earlier Resend configuration and external delivery are **not verified or used**.

## Changes delivered

`ops/private_preview` contains a Dockerfile, its separate build-context allowlist,
Compose configuration, minimal API dependencies, preview app factory, meaningful
health probe, exclusive preview env generator and host browser smoke script.

The factory uses the existing app/runtime and migrations. It disables every tender
catalog registration, AI/RAG/model downloads and notification workers. Real local
monitoring status reads remain available with zero feeds and background monitoring
disabled. All three services share an internal Docker network. API and Mailpit
also use a publishing bridge with outbound masquerading disabled; the API installs
a Python socket allowlist before application startup (DB, Mailpit SMTP, loopback).
No external sender, relay or notification credentials are configured. There is no billing integration/checkout in the audited source;
the existing billing UI explicitly says it is unavailable. No invented billing
environment setting is used.

Preview registration returns the same generic acknowledgement for a new or
existing address. It does not expose delivery flags or a token; actual delivery
must be proven independently by Mailpit. The existing registration page accepts
that response and directs to the truthful verification-link page. These are the
only two small common auth-page changes; the production registration API is unchanged.

The existing app has no global signing-secret setting: its sessions are opaque
and persisted as hashes. The preview adds HMAC integrity to those real sessions
using `PREVIEW_APP_SECRET`, while preserving DB expiry/revocation. It does not use
the secret as a legacy API key or authorize guests. Malformed/tampered cookies fail closed.

Readiness at `/private-preview/ready` checks the actual database, auth, companies,
organizations and support runtime components, plus a real Mailpit SMTP EHLO.
Missing services or SMTP failure produce HTTP 503. `/health` continues to describe
the existing component status; unavailable external integrations are intentional.

## Isolation and resource budget

Exactly `api`, `db` (`postgres:16`) and `mailpit` services. Compose project must be
`valyqon-private-preview`. The only published host ports are:

- `127.0.0.1:18765` → API port 8000.
- `127.0.0.1:18766` → Mailpit browser UI port 8025.

SMTP 1025 and PostgreSQL 5432 have no host publication. The database volume is
project-scoped `preview_db`, normally `valyqon-private-preview_preview_db`. Mailpit
capture is ephemeral. No fixed container names, bind mounts, external volumes,
host networking, Docker socket or privileged containers are configured.

Memory caps are API 512 MiB, DB 256 MiB, Mailpit 128 MiB (896 MiB combined).
API uses one worker, DB a small pool/buffers, and model downloads are omitted.
Actual free VPS memory, image build/startup, published-port reachability on the
publishing bridge and effect on the already occupied VPS require wrapper checks;
these caps alone do not prove host capacity. The Mailpit `latest` tag avoids
claiming a remotely validated version; the wrapper should record its resolved
image digest for reproducibility. No image pull/build occurred in this sandbox.

The Dockerfile-specific `.dockerignore` starts with deny-all and admits only app
Python/static assets, SQL migrations, CPV JSON resources, the example company
profile and preview scripts/dependencies. It excludes `.env`, keys, caches and
logs. Source is copied into the image. No owner configuration or dataset is needed.

## Wrapper build and access

### Browser startup incident: missing host dependency (2026-10-13)

Latest targeted incident audit: `round1-browser-output.txt` explicitly reports
`browser dependency missing: playwright`. This is raised by `load_playwright()`
at `from playwright.sync_api import sync_playwright`, before Chromium launches
or any preview/Mailpit endpoint is requested. No application assertion failed;
all six subsequent gates are unreached. `round1-browser-errors.txt` is empty.
The supplied prior files are named `prior-0/1/2-stdout.txt` and `-stderr.txt`,
not `prior-*-browser-*.txt`; they contain summaries, not Chromium tracebacks.
Consequently these artifacts cannot establish any later browser failure or an
outdated AWS application. The expected secondary tunnel port error is unrelated.

Rechecked with the available repository-adjacent Python 3.12.14:
`importlib.util.find_spec('playwright')` returns `None`; the existing offline
`tests.test_private_preview_browser` regression passes (1 test). No runtime or
test source change is warranted by this evidence. The duplicate-registration
privacy fix and all pre-existing edits remain intact. Installation into that
interpreter is outside this sandbox's writable workspace, so the trusted host
must execute the exact-interpreter installation/import/smoke sequence below,
using the already verified tunnel and installed Chromium. No AWS redeploy is
needed to resolve this import failure. Host browser validation remains blocked
until that dependency is installed; require exit 0 and all seven VERIFIED gates.

The supplied `private-preview-auth-rescue` directory contains
`prior-0/1/2-stdout.txt` and `round0-browser-output.txt`. All four report
`PRIVATE_GUEST=FAIL ModuleNotFoundError during browser startup`; all other
gates are unreached. Their error files contain only `[LOG_EMPTY]`. The named
`prior-*-browser-*.txt` files and full Chromium tracebacks are absent, so there
is no evidence here of a failing auth endpoint, Mailpit lookup or assertion.
Source imports Playwright at this stage, before browser launch or HTTP requests.
The available repository-adjacent Python 3.12.14 interpreter
(`tender-ai/.venv/Scripts/python.exe`) has no `playwright` module. This confirms
a local harness dependency blocker, not a proven deployed application defect.
The duplicate-email privacy implementation is unchanged.

The smoke now names a missing dependency safely and continues to fail nonzero.
`requirements.browser.txt` supplies the host-only dependency; it is separate
from API image dependencies. The trusted host must use the same explicit
interpreter for installation, import validation and smoke execution:

```powershell
# $python is the wrapper's existing explicit Python 3.12 executable.
& $python -m pip install -r ops/private_preview/requirements.browser.txt
if ($LASTEXITCODE -ne 0) { throw 'Host browser dependency installation failed' }
& $python -B -c "from playwright.sync_api import sync_playwright"
if ($LASTEXITCODE -ne 0) { throw 'Host Playwright import failed' }
# Retain existing browser path/executable settings and the verified tunnel.
& $python -B ops/private_preview/browser_smoke.py
if ($LASTEXITCODE -ne 0) { throw 'Private preview browser journey failed' }
```

Do not download Chromium automatically, start a second tunnel, rotate secrets,
delete volumes or redeploy the app to resolve this import failure. If there is
no installed compatible browser, the host browser prerequisite remains blocked.
All seven gates must report VERIFIED before claiming success. A subsequent
journey failure requires new sanitized evidence; these logs cannot diagnose it.

### Targeted host-stream repair after server checks passed (2026-10-13)

The latest supplied wrapper log reports private port validation, guest HTTP 200,
Mailpit HTTP 200, `PRIVATE_SERVER_STAGE=VERIFIED`, and both expected loopback host
ports. These are wrapper-reported server checks, not sandbox browser verification.
The subsequent `bash: line 95: $'\r': command not found` indicates a carriage
return in the script streamed by the Windows host wrapper to Bash. Changing
Docker COPY inputs or application startup does not repair that host stdin stream.
The checked recipe still copies app, example config and preview runtime sources;
Compose and both build recipes are unchanged by this repair.

The failing wrapper is outside this workspace and was neither read nor modified.
To apply the repair, its owner must replace the existing `"bash -s -- $runId"`
remote-command argument with the command from the new host-only helper:

```powershell
. (Join-Path $repoRoot 'ops/private_preview/host_bash_transport.ps1')
$remoteCommand = Get-ValyqonPreviewBashCommand -RunId $runId
$remoteText | & $ssh @sshOpts $userhost $remoteCommand 2>&1 | Out-String
# Retain the wrapper's existing logging and nonzero exit-code checks.
```

Here `$repoRoot` is the wrapper's existing local checkout path. This generates
`tr -d '\015' | bash -s -- '<validated run ID>'`: receiver-side normalization of
the supplied stdin only, without changing any server files. It also handles the
CRLF that Windows native piping may add after a string was normalized locally.
The Bash exit status remains the pipeline's last command status. Do not suppress
SSH errors or add `|| true`. Include the helper in the host source package if
that package uses an extension allowlist; it is not needed in the Docker image.

Local PowerShell regression
`& ./ops/private_preview/test_host_bash_transport.ps1` passed: exact command,
single-line output and rejection of whitespace, CR/LF, quote/semicolon injection,
leading option and overlong run IDs. It executed no SSH or network calls. Python,
Docker and Bash are unavailable on this sandbox PATH; no remote transport or
Chromium result is claimed. The host-wrapper edit and rerun remain required.
The full browser verification/email/reset/workspace journey is **NOT VERIFIED**
by the latest log. Public release / P3.9 remains **BLOCKED**.

### Targeted repair after healthy containers had no published ports (2026-10-13)

The supplied log shows successful Uvicorn startup and healthy API, DB and Mailpit.
However, API and Mailpit `Publishers` contain `PublishedPort: 0` and an empty URL;
host guest HTTP was `000`. This is a host reachability failure, not evidence of an
application import, migration or authentication failure. The internal-only bridge
is the configuration implicated by this evidence; the exact Docker engine cause
cannot be confirmed without the wrapper's inspection.

Compose now attaches API and Mailpit to an additional ordinary bridge for NAT
port publishing, retaining the explicit `127.0.0.1` bindings. DB stays exclusively
on the internal network with no published port. The additional bridge disables
outbound IP masquerading and defaults host bindings to loopback. Since absent
masquerading alone is not an application egress policy, `egress_guard.py` adds a
permanent Python audit hook before real app startup. It permits resolved DB:5432,
Mailpit:1025 and loopback connections, rejects external DNS/connections/UDP, and
fails startup if Docker service resolution fails. It is a Python socket guard,
not a host firewall or a guarantee against arbitrary native extension code.
Existing external adapters remain disabled; Mailpit has no configured relay.
No auth pages, tokens, secrets, resource limits, build recipe or production files
were changed for this repair. The guard is included by the existing Docker COPY
and both Dockerfile-specific Python source allowlists.

Local validation: `python -B -m unittest tests.test_private_preview_packaging
tests.test_private_preview_egress -v` passed **7 tests** using an available local
interpreter. These dependency-free tests cover build packaging/permissions,
publishing topology, restricted connection destinations, blocked DNS/UDP,
idempotent hook installation and startup failure on unresolved services. They
open no network sockets and do not verify Docker behavior or browser flows.

The wrapper must rebuild/recreate the same isolated preview project, confirm API
publication at `127.0.0.1:18765` and Mailpit at `127.0.0.1:18766` in Docker inspect,
and fail if either publication is missing or bound to another interface. Then
repeat host HTTP/readiness and the existing complete browser/email smoke test.
Container health alone does not establish host reachability. Docker, captured
mail and Chromium checks remain **NOT VERIFIED** here. P3.9 remains **BLOCKED**.

### Targeted repair after non-root import failure (2026-10-13)

The subsequent host build reached container startup, but the API restarted with
`PermissionError` reading `/app/ops/private_preview/preview_app.py`. DB and Mailpit
were healthy; API HTTP/readiness failed. The copied source was not readable by
the non-root runtime. The log does not establish the original archive mode.

Both Dockerfile copies now normalize `/app` traversal and all copied app, config
and ops directories to 0755 and files to 0644, after COPY and before `USER preview`.
This removes dependence on uploaded archive modes for Python imports, SQL,
configuration and static assets. Source stays root-owned; only `/app/data` is
owned by the runtime user. Compose, authentication and isolation are unchanged.

Added a packaging regression for permission scope and instruction ordering.
PowerShell static checks passed for those rules, byte-identical recipe copies
and matching allowlists. The Python unittest could not run in this repair sandbox:
neither `python` nor `py` is available on PATH and checked interpreter paths were
unavailable. Docker is also unavailable. These static checks do not prove runtime
startup. The wrapper must rebuild the image and repeat readiness, Mailpit and
Chromium checks; all remain **NOT VERIFIED**. Public release / P3.9 is **BLOCKED**.

### Targeted repair after host build failure (2026-10-13)

The host validated private port bindings, then failed before any Dockerfile
instruction ran: `failed to read dockerfile: open Dockerfile.preview: no such
file or directory`. The local canonical recipe exists; the provided log proves
the selected recipe was absent from the host build context, but does not prove
whether packaging or host path rewriting caused the omission.

Compose now selects `ops/private_preview/Dockerfile.preview.txt`, a byte-identical
text-suffixed copy of the retained canonical `Dockerfile.preview`. Its adjacent
`Dockerfile.preview.txt.dockerignore` is byte-identical to the canonical dedicated
deny-all allowlist. The wrapper package must include both files and retain the
repository-relative directory layout, without rewriting the Compose build paths.
Build context remains `../..` relative to `ops/private_preview/compose.yaml`.
No application, auth, service isolation, port, secret or resource settings changed
in this repair.

`python -m unittest tests.test_private_preview_packaging -v`: **1 passed** locally.
This dependency-free regression verifies the selected recipe resolves relative
to its build context, both copies remain identical, and the recipe/allowlist
survive a staged source package. The broader private-preview test rerun stopped
at import because this sandbox interpreter lacks `python-dotenv`; no auth pass
is claimed for this repair. Docker is unavailable here. The failed host build,
readiness, actual captured mail and Chromium journey remain **NOT VERIFIED**
pending the wrapper's rerun. Public release / P3.9 remains **BLOCKED**.

The owner-provided host wrapper performs these actions; **Codex did not run them**.
Package safe source files only, including the Dockerfile-specific `.dockerignore`,
all `app/database/schema/*.sql` and app assets/resources. Use only the isolated
directory `/home/ubuntu/valyqon-personal-preview`; never operate on the old deployment.

From that isolated directory on Ubuntu 24.04, create the preview-only env once:

```sh
python3 ops/private_preview/generate_env.py /home/ubuntu/valyqon-personal-preview/.private-preview.env
docker compose -p valyqon-private-preview --env-file /home/ubuntu/valyqon-personal-preview/.private-preview.env -f ops/private_preview/compose.yaml config --quiet
docker compose -p valyqon-private-preview --env-file /home/ubuntu/valyqon-personal-preview/.private-preview.env -f ops/private_preview/compose.yaml up -d --build --wait --wait-timeout 180
```

The generator creates two independent random hex secrets with mode 0600 on
Ubuntu, refuses to overwrite an existing env and prints no values. Hex prevents
database-URL interpolation ambiguity. Reuse this env with the same preview volume;
do not rotate its DB password inadvertently. Do not print expanded Compose config.
No root-repository `.env` is loaded (`PYTHON_DOTENV_DISABLED=1`).

After verifying loopback-only port bindings, the host wrapper establishes SSH
forwarding. The equivalent owner access command is:

```sh
ssh -N -L 127.0.0.1:18765:127.0.0.1:18765 -L 127.0.0.1:18766:127.0.0.1:18766 ubuntu@63.189.75.15
```

With forwarding open, visit **http://127.0.0.1:18765/** for the guest website and
**http://127.0.0.1:18766/** for the private mailbox. Register a synthetic
`@example.test` address, open its captured verification link, use the workspace,
then try Forgot password and its captured reset link. Both kinds of email link
point to `http://127.0.0.1:18765`. Mailpit captures messages; it does not send to
external recipients. Keep the mailbox private because it contains account links.

## Tests and evidence

Executed locally with installed Python 3.12 and offline cached packages,
`PYTHON_DOTENV_DISABLED=1`:

- `test_private_preview.py`: **13 tests passed** (isolation scaffold, fresh env,
  trusted mailbox links, missing mail failure, signed-cookie tampering/rotation,
  expiry, one-use tickets and reset session revocation).
- Existing `test_auth.py`: **8 passed**.
- Existing `test_email_verification.py`: **7 passed**.
- New Python files and auth-page change: syntax compilation passed; scoped diff
  whitespace check passed. Compose YAML was also inspected locally; Docker
  interpretation and runtime remain the wrapper's responsibility.

`test_private_preview_api.py` adds six isolated API tests for guest pages, the full
auth/reset/company journey, tenant separation, nonenumeration, failed delivery,
rate limiting, cross-origin rejection, disabled adapters and readiness. Its local
execution is **NOT VERIFIED**: import stopped because sandbox Python lacks
`pymupdf`. No dependency stub or fake API pass was substituted. The Dockerfile
includes PyMuPDF; the host must run these tests with its installed app dependencies.
Existing password-reset/API/rate-limit regressions also require the host's pytest
and application packages. Suggested host command (no real email/network fixtures):

```sh
python -m pytest -q tests/test_private_preview.py tests/test_private_preview_api.py tests/test_auth.py tests/test_auth_api.py tests/test_email_verification.py tests/test_email_verification_api.py tests/test_password_reset.py tests/test_password_reset_api.py tests/test_auth_rate_limit.py tests/test_web_auth.py
```

The host Windows smoke command needs no flags or downloads:

```powershell
$env:VALYQON_PREVIEW_BASE_URL = 'http://127.0.0.1:18765'
$env:VALYQON_PREVIEW_MAILPIT_URL = 'http://127.0.0.1:18766'
$env:VALYQON_PREVIEW_SCREENSHOT_DIR = 'C:\Users\ramze\Documents\Codex\tender-ai-phase19\ops\private_preview\screenshots'
# Preserve the wrapper's existing PYTHONPATH and PLAYWRIGHT_BROWSERS_PATH.
python ops/private_preview/browser_smoke.py
```

The wrapper may use its explicit Python executable; optional
`VALYQON_PREVIEW_BROWSER_EXECUTABLE` selects an already installed Chromium.
Optional `--screenshot-dir` overrides the screenshot env setting. This script
uses real Chromium, rejects non-loopback origins, blocks external browser HTTP,
and creates a unique synthetic account. It checks pages, unverified login
rejection, actual Mailpit delivery, UI link verification, replay rejection,
password login, organization/company creation, reload/reselection persistence,
forgot/reset mail, old-session/old-password rejection and replacement-password
login. It never substitutes authentication or external AI. Missing mail fails.

It prints all seven `PRIVATE_*` gates as VERIFIED / NOT_VERIFIED / FAIL with
redacted diagnostics and exits nonzero unless every gate passes. Screenshots are
`guest.png`, `login.png`, `register.png`, `forgot.png`, `workspace.png`; auth forms
are captured before entering credentials. Verification/reset/mailbox pages,
tokens, passwords, traces and HAR files are not captured. Synthetic accounts and
messages remain confined to the preview and make repeated runs independent.

**Docker startup, VPS preview, real Mailpit SMTP capture and all seven Chromium
gates are NOT VERIFIED until the host wrapper supplies passing evidence.** No
browser execution against the private server was claimed inside this sandbox.

## Integration limits

External tender retrieval, AI inference/PDF AI drafting, embedding models, real
email delivery, Telegram notifications and billing are intentionally unavailable.
Their end-to-end external behavior is **NOT VERIFIED**. Local auth/workspaces and
captured link emails are the acceptance target. Existing Discover/scoring/Saved
implementations were retained; this smoke does not repeat the prior Customer MVP
gate or manufacture tender results. Public Caddy/443 and the existing deployment
must remain untouched. P3.9 remains BLOCKED after a successful private preview.
