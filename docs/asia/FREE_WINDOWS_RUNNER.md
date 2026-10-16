# VALYQON Asia: free testing and native Windows 11 Home completion

## Already verified on the user's self-hosted Linux runner

- `VALYQON-RU-01` handles this PR's Linux checks at no hosted-runner cost.
- A full Linux test run passed (2,877 passed; 85 skipped; 1 expected xfail).
- Real official Hong Kong tender feeds passed 6/6 using both direct adapters
  and the actual `connector.sync.v1` worker into temporary SQLite/search.
- The real production `Dockerfile` built successfully.
- The three separately assigned WSL/Linux runners belong to their existing
  development teams; do not repurpose them.

Previous evidence (not a substitute for rechecking the final commit):
[Linux/live-worker proof](https://github.com/Ramzes2023/TenderLens-AI/actions/runs/38909142631) and
[production Docker build](https://github.com/Ramzes2023/TenderLens-AI/actions/runs/38909688659).

## One pending native Windows-specific check

`tests/test_p39e_local_preview.py` uses real Win32 Job Objects and cannot
be tested with a Linux/WSL runner.

The user's **Windows 11 Home** has no Windows Sandbox. Do not recommend
purchasing Windows Pro, fake the test under Wine, or require GitHub-hosted
Windows Actions for this particular integration.

A separate **free native Windows self-hosted runner** is prepared:

- Runner name: `VALYQON-WIN-ASIA-01`
- Single custom label: `valyqon-asia-windows`, no generic/default labels.
- Installer: `scripts/dev/setup_valyqon_windows_asia_runner.ps1`
- CI: `.github/workflows/asia-windows-selfhosted.yml`

The Windows Home workflow checks runner identity and requires the shell to be
**non-elevated**. It checks that the fixture source files, dependency manifests
and relevant supporting modules have no changes relative to protected `main`.
It then executes **only source from an independent detached checkout of
protected `main`** in a temporary local Python 3.12 virtual environment.
The Windows runner never executes unreviewed pull-request application code.
It cleans the temporary worktree and dependencies afterward. The fixture
itself exercises actual native Win32 APIs, so this is a real Windows result.

**Important:** this is *not* VM isolation; code from the trusted protected
`main` branch runs as an ordinary non-admin Windows process. GitHub Actions
self-hosted runners still have access to files of the OS account running the
runner. For stronger isolation, a distinct low-privilege Windows user and/or
a licensed Windows VM is recommended. Avoid sharing personal credentials with
the runner account. There is no claim of sandbox isolation on Windows Home.

The installer obtains a short-lived registration token through the
authenticated GitHub CLI, checks the official GitHub Actions runner release
asset's published SHA256, configures the fourth dedicated runner (without
overwriting any prior WSL runner), **logs out the GitHub CLI after
registration**, and starts the runner interactively (not a Windows service).
Keep the runner window open for the test.

A **one-time browser login in native Windows** is unavoidable: the connected
GitHub API cannot operate on the user's Windows desktop and must not expose
a runner registration token in chat. No GitHub billing purchase is needed.

### Fastest one-time local setup

In native Windows PowerShell, *not* Run as Administrator:

1. Install the free GitHub CLI (`winget install --id GitHub.cli -e`).
2. Sign in using `gh auth login --web -h github.com -p https`.
3. Obtain the pinned `setup_valyqon_windows_asia_runner.ps1` via authenticated
   GitHub and run it with `-Install`.

Never paste the resulting registration token into chat. The setup command
should be run only from a specific, reviewed commit of this PR.

## Final release gate

The last **same** branch commit must have successful free self-hosted:

1. Full Linux CI, including source contracts and official reference checks.
2. Real six-source app adapters → queue/Worker → isolated SQLite → search.
3. Production Dockerfile build.
4. Native Windows Win32 process-isolation fixture.
5. Compatibility/conflict review with current main and other open PRs.

Older GitHub-hosted checks may fail before runner allocation because the
account has no billing capacity. They are NOT proof that the source code
fails. The shared default workflows and branch-protection requirements need
coordinated adoption of safe equivalent self-hosted jobs; no check should
be deceptively marked as passed or silently skipped.

**No merge until each necessary gate is genuine and green.**
No AWS/production changes, and Asian sources remain opt-in disabled
by default pending deployment decision.
