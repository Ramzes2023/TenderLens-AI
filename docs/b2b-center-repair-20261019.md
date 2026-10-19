# B2B-Center repair verification — 2026-10-19

Status: code regressions pass; live integration remains BLOCKED. No live tender
has been proved through the complete Worker → SQLite → search → authorized
company scoring chain during this repair session. Fixtures do not establish
live acceptance.

Branch: `fix/ru-b2b-two-request-worker-budget-20261019`.
Unchanged HEAD: `66bb76777cfb3299d412ad8dfd75667c587fe478`.
Changes are uncommitted and unpushed. No merge, production database, Docker
volume, Telegram recipient, Samara adapter or ARMEPS adapter was changed.

## Changed files

- `.github/workflows/ru-real-data-acceptance.yml`
- `app/sources/b2b_center.py`
- `app/sources/http.py`
- `app/sources/ru08_integration.py`
- `scripts/ci_ru_b2b_real_worker.py`
- `scripts/ci_ru_b2b_user_scoring.py`
- `scripts/diagnose_ru_b2b_transport.py` (new)
- `tests/test_b2b_foreign_aggregate.py`
- `tests/test_b2b_transport_acceptance.py` (new)
- `tests/test_ru08_integration.py`
- `docs/b2b-center-repair-20261019.md` (new)

## Repairs

The previous scoring acceptance retried every ConnectorTransportError,
including permanent rejections, and inserted fetched notices directly into
the database. Both live acceptances now use one actual durable connector job,
real leases and fenced writes. Retryable failures follow production queue
backoff, with at most three claims. Permanent failures stop immediately.
Scoring consumes the resulting SQL records through the authenticated API and
the actual scoring Worker. Replays, exact stored identities and cross-tenant
result/revision/create access are checked.

The transport error now exposes a fixed reason category: policy, response size,
HTTP status, transient HTTP status, public-IP rejection, certificate verification
or network failure. Certificate failures are permanent; verification remains
enabled. Existing exact-host, DNS-answer validation, TCP-peer validation,
redirect prohibition, two-request and 2 MiB limits remain enforced. The shared
transport classification changed; no source allowlists were expanded.

The second request can only target the already approved official office URL.
It is used for oversized root responses or structured foreign-only listings.
Login/challenge/unrecognized HTML, unsafe origins and permanent HTTP/security
errors cannot trigger fallback. Cookies are cleared before fallback. Office
coverage is explicitly partial and its `listing_url` now survives persistence.
The local RU08 wrapper also permits two B2B requests while reducing its B2B
byte cap from 5 MiB to the production 2 MiB.

A same-host `/search/number/l…/` URL does not establish B2B ownership. The parser
now requires a matching procurement number and a validated HTTPS native
`/market/…/tender-N/` or `/app/market-next/…/tender-N/` reference. Foreign,
unverified, mismatched, query-bearing and malformed references cannot become
native B2B records. The unchanged historical capture contains ten aggregate
cards, of which only `l4639392-4-12-1` has validated native B2B provenance.
Its acceptance here is OFFLINE evidence only. Tests that formerly treated all
ten as B2B records were corrected; explicitly synthetic input is clearly marked.
Existing production records were not deleted or rewritten.

The CI live gate is retained and strengthened with offline regressions and
post-failure official transport diagnostics. No required check was disabled.

## Local checks

Python 3.12.10; dependencies installed from `requirements-dev.txt` into the
ignored workspace `.venv`. Test databases live in isolated temporary locations.
The default pytest temp root was inaccessible; later runs used fresh directories
under workspace `data/`. Initial collection/setup failures are not reported as
successful checks.

- Combined B2B, RU08, source contracts, HTTP transport/cleanup, scoring Worker
  and auth suite: **555 passed, 2 skipped**. The two existing skips are the
  impossible checksum-corruption cases for raw deflate, which has no checksum.
- Connector Worker and strengthened native-provenance tests: **98 passed**.
- Final B2B fallback/challenge, RU08, scoring Worker and auth suite:
  **115 passed** after the final source safety change.
- Daily source health workflow contracts: **6 passed**.
- Final terminal-attempt evidence and transport acceptance suite: **15 passed**.
- Compilation, workflow YAML parsing, unconditional live-scoring-step assertion
  and `git diff --check`: passed.

Counts overlap and must not be added as a count of unique tests. Offline
authorization coverage uses synthetic accounts and procurement input and is
not claimed as live scoring proof. A pre-existing Starlette/httpx deprecation
warning remains.

Ignored local evidence files: `data/b2b-tests-final.log`,
`data/b2b-connector-tests-final.log`, `data/b2b-safety-tests-final.log`,
`data/b2b-transport-final.json`, `data/b2b-transport-latest.json`,
`data/b2b-worker-final.log`, `data/b2b-worker-latest.log`,
`data/b2b-scoring-final.log`, `data/b2b-scoring-latest.log`.

## Real public-network evidence

Official URLs, queried without proxy inheritance, redirects or TLS bypass:

- `https://www.b2b-center.ru/search/`
- `https://www.b2b-center.ru/search/industry/ofis/`

DNS returned `91.206.127.243`. Initial production-transport probes received
HTTP 200 over verified TLS 1.3: root 306140 decoded bytes, office 552705 bytes,
both below 2097152. Neither payload produced a usable native record under the
strict parser; their contents were not used as successful acquisition.
Subsequent probes failed while reading response headers, with the explicit
cause chain `httpx.ReadTimeout → httpcore.ReadTimeout` and `retryable=True`.
The latest completed diagnostic received **HTTP 502 from BOTH official URLs**,
again over verified TLS 1.3, classified as `http_transient`. The diagnostic
used exactly two dispatched requests. This proves an HTTP endpoint failure
from this environment at that time; it does not establish a permanent outage.

Windows curl failed locally in Schannel with `SEC_E_NO_CREDENTIALS` before
HTTP. It is not evidence of a server certificate failure. Python transport
successfully verified TLS, so no certificate bypass or new trust root was used.

Standalone real Worker acceptance and the repeated real authenticated scoring
acceptance exited nonzero. Acquisition did not succeed, so no real notice
identity, live SQL/search roundtrip or live tenant scoring result is claimed.
The official site was also inspected in the browser-backed public web tool;
browser-visible notices were not injected into the Worker or database.
The latest standalone Worker AND authenticated scoring runs each explicitly
reported three claims followed by `B2B_CONNECTOR_STATE=failed` and exited 1;
exhausted retries remain failed live gates. The pipeline stops at acquisition,
before any real B2B SQL/search/scoring success can be claimed.

## GitHub evidence and remaining green-CI conditions

The original failing #224 scoring run is
https://github.com/Ramzes2023/TenderLens-AI/actions/runs/39288784361 . Its log
only reports ConnectorTransportError, without DNS/TLS/HTTP cause information.
It cannot establish the precise historical cause retrospectively. The new
diagnostics distinguish the currently reproduced timeouts and HTTP 502.

At inspection, #224 SHA `33857b758f3a89c72fdfc95e5525c3a3f84eac09` had 24
successful and 2 failed workflows: B2B scoring and Armenia/Tajikistan ingestion.
Current branch HEAD had 37 successful and 3 failed workflows: JETRO bids,
Asian public procurement, and Asia seven official feeds. Its old B2B gates
were green, but predate these stricter provenance checks and cannot validate
the uncommitted changes.

Full green requires a genuine native B2B response within the existing limits,
successful real leased Worker/SQLite/search/authorized scoring runs, and all
required checks green on the final published commit, including independent
source checks. These changes must first be reviewed and published separately
by the owner as requested. No GitHub workflow was rerun against unpublished
local changes and no status was altered. Samara and ARMEPS remain out of scope.

Final Git status: eight tracked files modified, three new untracked files (the
new diagnostic, regression suite and this report); no staged files or commits.
The eleven paths are listed above. `.venv/` and local `data/` evidence are ignored.
