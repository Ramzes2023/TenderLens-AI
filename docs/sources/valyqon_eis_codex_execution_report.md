# EIS 44-FZ / 223-FZ execution report

Date: 2026-10-30, observations approximately 19:47–19:54 UTC.

Verdict: **EIS_PUBLIC_DEPLOYMENT=BLOCKED_NETWORK**. No public EIS activation,
merge, service restart, enqueue, application deployment or Caddy reload occurred.
Both legal categories remain unverified as current official sources.

## Git and release state

- Work branch: `codex/eis-public-20261030-204538`.
- Diagnostic implementation/report commit: `50f96528f74ba9cd5af47515c4b45a2e092f6d09`.
- [Draft follow-up PR #386](https://github.com/Ramzes2023/TenderLens-AI/pull/386)
  targets the review branch of #379, so its diff contains only this diagnostic
  and report. No force push, main merge or release was performed.
- Inspected EIS baseline: `8b8828941ebe600c5ff4a4583a31ccaaf0bbe5b8`.
- Fetched current main: `cf84479e030017abf2db51db4a11c9698b36f79c`.
  Main has subsequent STAN/Lenobl and operator-safety work; it is not this EIS branch.
- [PR #379](https://github.com/Ramzes2023/TenderLens-AI/pull/379) is OPEN,
  MERGEABLE, but UNSTABLE. It is neither merged nor proof of VPS deployment.
- [Real EIS run 41115072038](https://github.com/Ramzes2023/TenderLens-AI/actions/runs/41115072038)
  failed both listing/Worker and 44/223 RSS gates. The RSS log explicitly reports
  `ConnectorTransportError`, zero records/DB/query results for each law and
  `EIS_44_AND_223_LIVE_PROOF=FAILED`. General CI and isolated offline bridge passed.
- First-party main workflow run `41108039693`, job `eis-verified-ru-runner`,
  was still queued when checked. It supplies no current upstream proof.
- GitHub required-status-checks API returned 404 `Branch not protected` for main.
  This does not waive the user-mandated genuine-source release gates.

## Trusted access and actual runtime

Existing SSH identity and known_hosts were used with `BatchMode=yes`,
`StrictHostKeyChecking=yes`, bounded connect timeout, and non-root login.
No keys, environment files, tokens or notice/customer contents were printed.

Production `tenderlens-vps` API remained healthy and its Caddy remained running.
The same separate `valyqon-public-sources` project contains different generations:

| Service | Observed state | Image / volume / egress |
| --- | --- | --- |
| `worker` | exited 137, OOMKilled=false, RestartCount=0; finished 2026-10-28T10:15:09Z | image `6fe1fc70dbef`; volume `valyqon-public-sources_public_source_data`; network `valyqon-public-sources_publisher_outbound` |
| `guest-sources` | exited 0, finished one second later | same older image and source volume |
| `worker-v6` | running, RestartCount=0 | image `25afcd9a23b0`; volume `valyqon-lenobl-trial_public_source_data`; network `valyqon-lenobl-trial_publisher_outbound` |
| `guest-sources-v6` | running, healthy | same v6 image/volume; existing `tenderlens-vps_edge` network |

Older Compose labels point to the `valyqon-public-sources-9fad89f/source`
checkout. V6 labels point to `valyqon-public-sources-f6a75d3` and the resolved
`release-v6-fe4c66bbd553.json` descriptor. No generic Compose restore was attempted:
starting the older services risks competing generations and different databases.

Exit 137 is not proof of OOM. The last 150 old-Worker log lines contained no
matched shutdown/SIGTERM/SIGKILL/error/OOM signature; the bounded historical Docker
event query returned no events. A kernel-journal query returned no OOM matches,
but retained journal access/coverage was not established. Running v6 cgroup
memory.events showed `oom=0`, `oom_kill=0`; those counters do not describe the old
container. The historical stop actor/cause remains unknown. Old services stayed stopped.

## New actual transport comparison

Executed `ops/public_sources/VALYQON_EIS_ROUTE_COMPARE.ps1` against the VPS.
The standard-library probe uses fixed origins, one address per family, five-second
socket timeouts, no proxies, no redirects, verified TLS and header-only HEAD.
Each vantage point has an outer 25-second timeout including DNS. Docker probes
use each exact Worker image by digest and its attached Docker-managed non-internal
`publisher_outbound` network, `--pull never`, no mounts, read-only root filesystem,
unprivileged user, dropped capabilities and memory/PID limits. No deployed service
is executed, restarted or reconfigured by this probe.

| Vantage | zakupki.gov.ru IPv4 | Control example.com IPv4 | IPv6 |
| --- | --- | --- | --- |
| VPS host | DNS: one address; TCP timeout 5.01s | verified TLS; HTTP 200 | EIS: no AAAA returned; control: errno 101 |
| exact old Worker image/network | DNS: one address; TCP timeout 5.01s | verified TLS; HTTP 200 | same |
| exact running v6 Worker image/network | DNS: one address; TCP timeout 5.00s | verified TLS; HTTP 200 | same |

Host default IPv4 route exists; no IPv6 default route was returned. EIS never
reached TLS or HTTP, so these observations cannot establish a certificate,
parser, 403, 404, feed-format or legal-identity failure. They establish an
origin-specific TCP reachability blocker common to host and both egress networks.
The responsible network/provider/publisher filtering point is not established.
The running v6 Worker reports no configured outbound proxy among the inspected
proxy variable names. No approved working Russian route was established; the
existing first-party Action is queued. No arbitrary proxy, firewall change,
trust relaxation, mirror or paid access was introduced.

## Worker and SQLite evidence

Executed only aggregate SQL inside the running v6 Worker, opening the fixed
isolated database via SQLite URI `mode=ro` and `PRAGMA query_only=ON`:

| Source | source_opportunities rows | connector.sync.v1 jobs matching payload source_id |
| --- | --- | --- |
| `eis` (44-FZ) | 0 | none |
| `eis_223` (223-FZ) | 0 | none |

`EIS_223_ENABLED=false`, `EIS_DIRECT_ENABLED=false`; public EIS opt-in flags
are unset. No jobs were submitted and no source rows were inserted. Consequently
there is no actual lease-fenced EIS acceptance, dedup, keyword-query or future
deadline evidence for either law. Synthetic offline tests below are not live proof.

## Validation and changes

Added the mount-free host/old/v6 comparison operator script and its fixed-origin
standard-library probe, plus this report. Existing law gates, parsers, pinned
trust, source identity, deadlines and default-off behavior were retained.
Changing a parser cannot resolve the observed TCP failure.

- 160 targeted EIS/public/scheduler/operator/Compose regression tests passed.
  This includes RSS 223 persistence, 44/223 isolation, canonical identity,
  deadline/projection gates, read-only runtime audit and fail-closed activation.
- 35 additional auth, guest locale, guest AI language/Latin and authenticated
  team/source roundtrip tests passed. One existing Starlette deprecation warning.
- Initial pytest invocation hit Windows temp-directory permission errors:
  137 passed, 23 fixture errors. Re-run with a new workspace-local `--basetemp`
  passed all 160; no test was removed or weakened.
- VPS Docker Compose resolved the worktree's six-source overlays and optional
  EIS overlay in a temporary directory. Both default-off and opt-in variants
  passed explicit checks for isolated SQLite, no published service ports,
  no customer DB volume, empty Telegram token, monitoring disabled and scheduler
  network_mode=none. This was `config` only, with synthetic URL selectors for
  configuration validation, not a real official-feed or deployment test.
- `git diff --check` passed. The route comparison itself ran successfully at all
  three vantage points. No new source URL or procurement record was invented.

## Public HTTPS and rollback status

External anonymous HTTPS with certificate verification returned:

| GET | Status | Evidence |
| --- | --- | --- |
| `/` | 200 | HTML, no-store |
| `/health` | 200 | JSON |
| `/login` | 200 | HTML, no-store |
| `/api/v1/auth/me` | 401 | unauthenticated access rejected |
| `/api/v1/public/opportunities?limit=2` | 200 | preview JSON, no-store/max-age=0 |

These are baseline availability checks, not EIS source receipts. No tenant
login credentials were used. Guest AI container health was observed and its
offline regressions passed; a current external generated AI answer was not
requested. Source-specific identity cannot be inferred from redacted guest rows.

Current Caddyfile SHA256:
`3ba4a4cbebdbe95b7ae5bc375a3114756c39c42a8d52a1e8ba0b7192d7c87ee9`.
The on-disk file contains the exact public opportunities and help/ask paths.
Read-only access to its localhost admin API was unavailable; effective live
upstream mapping was therefore not independently proved. No Caddyfile contents
were logged. No candidate configuration or public routing change was made.

No Caddy or volume backup was created because the release stopped before any
mutation requiring rollback. No snapshot/restore proof is claimed. Before a later
release, back up and restore-test the actual serving source volume and exact
effective Caddy configuration, confirm service generations and upstream mapping,
then prove both official laws, current deadlines, real Worker/SQL/dedup/query and
anonymous HTTPS. On failure, restore only that reviewed Caddy configuration and
isolated services; never restart production API or remove volumes.

Required external next step: restore lawful verified TCP/HTTPS reachability to
the official EIS publisher from the target runtime, or make an already approved
first-party route operational and repeat the real gates. Reachability alone will
still not prove that the official RSS interfaces contain eligible current notices.
Authenticated SOI coverage remains unimplemented and is not claimed by RSS.

**EIS_PUBLIC_DEPLOYMENT=BLOCKED_NETWORK**
