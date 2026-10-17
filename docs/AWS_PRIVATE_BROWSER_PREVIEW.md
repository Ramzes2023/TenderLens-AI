# Windows → AWS isolated private browser preview launcher

User-operated: a single PowerShell script to deploy the current repository main
to an isolated private preview on the existing AWS VPS. This is NOT a public
production deployment, not an autonomous GitHub runner action, and does not
connect to real procurement sources or payment gateways.

## Launch
From a fresh checkout of main on the Windows laptop:

    & .\ops\private_preview\launch_aws_preview.ps1 -PlanOnly
    & .\ops\private_preview\launch_aws_preview.ps1

Defaults: ubuntu@63.189.75.15, SSH private key at
$HOME\.ssh\tenderlens_vps_ed25519. Supply -Server if the current VPS public IP
has changed. The key remains on the user's laptop; strict known_hosts and batch
authentication are required. Do not share or commit the key.

The launcher fetches a NEW isolated current-main checkout, uses the project's
source-only archive builder to exclude all credentials, uploads solely to
/home/ubuntu/valyqon-personal-preview/releases/<commit>, and builds the
existing isolated Docker Compose project valyqon-private-preview. The preview
has its own Postgres16 volume, Mailpit and separate env. It does not update
production repos, volumes, secrets, container projects, data, public port
bindings, DNS or firewall. The shared existing private-preview volume can be
migrated to the latest schema: it is TEST data only.

Server acceptance checks:
- API and mailbox port mapping must be 127.0.0.1-only (18765, 18766).
- Real GET /, /login, /scoring-methodology, /status.json all respond HTTP 200.
- /private-preview/ready must verify database/auth/support/Mailpit and say
  external integrations disabled.
- /status.json must show real DB ready, external tender sources unverified and
  payments disabled. Mailpit must serve HTTP 200.
- Local SSH tunnel must then serve the readiness endpoint as well.

Result (on the user's Windows laptop only):
- UI: http://127.0.0.1:18765/
- Login: http://127.0.0.1:18765/login
- Status: http://127.0.0.1:18765/status
- Captured email: http://127.0.0.1:18766/

The launcher prints TUNNEL_PID. Close only that SSH process with
Stop-Process -Id <PID>. The preview containers can be stopped without wiping
test data with docker compose -p valyqon-private-preview ... down (NEVER -v).

Optional real Chromium browser acceptance after connecting the tunnel:
    $env:VALYQON_PREVIEW_BASE_URL = 'http://127.0.0.1:18765'
    $env:VALYQON_PREVIEW_MAILPIT_URL = 'http://127.0.0.1:18766'
    & py -3.12 ops/private_preview/browser_smoke.py

This requires Playwright installed in that exact Python and an already installed
Chromium browser, per docs/VALYQON_PERSONAL_PREVIEW_HANDOFF.md. The HTTP smoke is
NOT the Chromium 7-gate end-to-end test. Do not claim the 7 browser gates passed
until that script exits 0. Use an @example.test account and only synthetic data.

## Updating an already opened local browser preview

If the previously verified SSH tunnel is still running and holds **both** loopback
ports, run the launcher with `-ReuseExistingTunnel`. This redeploys new current
`main` only to the isolated preview Docker project, checks remote readiness, then
verifies that the same trusted `ssh.exe` process owns both local 18765/18766
forwards and confirms the live ready response. It does not terminate the tunnel
or clear browser sessions. If ownership is ambiguous the launcher stops rather
than manipulating the listener. `-PlanOnly` still performs no network action.

```powershell
& .\ops\private_preview\launch_aws_preview.ps1 -ReuseExistingTunnel
```

**Limit:** this is server update / HTTP readiness, not a full Chromium UX journey.
After updating, refresh the live guest page and Support while keeping the tunnel.
