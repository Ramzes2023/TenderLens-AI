# VALYQON Asia: fully self-hosted, no GitHub-hosted minutes

## Completed in this branch

The dedicated Linux runner `VALYQON-RU-01` (WSL2) has already run the
full Linux pytest suite in read-only, non-root disposable Docker containers,
six **real** official Hong Kong procurement RSS adapters, SQLite storage and
keyword searches, and six actual `connector.sync.v1` worker tasks.
The true release `Dockerfile` also built on the same runner.

- Green Linux proof: https://github.com/Ramzes2023/TenderLens-AI/actions/runs/38909142631
- Green release build: https://github.com/Ramzes2023/TenderLens-AI/actions/runs/38909688659

There is no requirement to purchase GitHub-hosted runner minutes for
these tests. **Older failed hosted workflows are not a Python CI verdict.**

## Native Windows-only fixture is a separate security domain

A Linux WSL2 runner cannot prove `tests/test_p39e_local_preview.py`,
which calls Win32 Job Objects and kernel32 functions. Even a Linux Docker
container cannot reproduce Win32 process-isolation semantics. The trusted
`VALYQON-RU-01` probe confirms no `powershell.exe` / `cmd.exe`
interop, so remote GitHub/WSL workflow execution cannot register a native
Windows runner on the physical host.

A **fourth separate, low-privilege, repo-scoped native Windows runner** is
staged for this direction only:

- Runner name: `VALYQON-WIN-ASIA-01`
- Dedicated label: `valyqon-asia-windows`
- Registration: `scripts/dev/setup_valyqon_windows_asia_runner.ps1`
- Native Windows acceptance:
  `.github/workflows/asia-windows-selfhosted.yml`
- Sandbox-only test entry point:
  `scripts/dev/asia_windows_sandbox_guest.ps1`

Only an authenticated GitHub repository administrator on Windows can
request the short-lived registration token and start the new runner.
The connector cannot access that Windows desktop or GitHub's runner
registration-token creation endpoint. **Do not include the token in chat,
a commit, PR comment or CI output.**

The Windows runner must not run as SYSTEM, must not reuse the existing
three WSL runner folders, and must not run a PR's Python code directly on
the host. The staged workflow checks out the pinned branch
without persisted GitHub credentials, verifies relevant Windows test and
dependency files against `main`, then launches a disposable Windows
Sandbox with source/cache folders **read-only**, networking **disabled**,
clipboard/audio/printer redirection disabled and only a minimal result
directory writable. Python 3.12.10's official Windows installer is
signature-checked; binary-only wheels are prefetched in advance, and
the native Win32 pytest suite runs in the disposable guest, not the host.

**Windows Sandbox requires a supported Windows Pro, Enterprise or
Education edition. Windows Home is not supported.** If Windows Sandbox
cannot be enabled, use an isolated, licensed Windows VM as an equivalent
gate. The Windows test is not to be skipped or passed using Wine/Linux.

Run the setup script locally after reviewing it:

```powershell
# In a native, non-elevated Windows PowerShell, with an authenticated gh CLI:
.\scripts\dev\setup_valyqon_windows_asia_runner.ps1
.\scripts\dev\setup_valyqon_windows_asia_runner.ps1 -Install
# In the newly-created runner folder, launch run.cmd as a dedicated account.
```

The registration script is designed to fail closed for unexpected release
assets, missing published SHA256 or a runner already configured in that
folder. **Running this script is an explicit local administrative action,
not something the GitHub connector can perform silently.**

## Release / merge policy

- Verify full Linux CI, six real adapters, six real worker jobs and Docker
  build on the **final commit SHA**, not an earlier SHA.
- Verify native Windows Sandbox job passed on the final SHA.
- Review changes against the current `main` HEAD and all concurrent
  Russia/CIS/source PRs; never clobber another developer's branch.
- Verify no AWS / production changes and default opt-in flags remain off.
- Do not merge PR #36 while any required gate is not proven.

The three existing WSL runner installations are untouched. The original
`ci.yml` and Russia/CIS workflow triggers remain unmodified in this
branch until coordinated adoption of the tested self-hosted equivalents.
