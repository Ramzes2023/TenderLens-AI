# VALYQON AI — test the redesign in a real browser on Windows

**Status:** a real local app preview (not a screenshot/mockup). It uses the
actual landing Python route, CSS, JavaScript and guest REST endpoints from
PR #264. No production data, external email delivery, Telegram, payments or source
workers are attached. Local Mailpit captures only test verification/reset email. Guest result list is empty until legitimate notices are
ingested into this isolated database, and no fake tenders are substituted.

## Launch without touching main or existing Docker volumes

Run these commands in **PowerShell** with Docker Desktop running:

```powershell
cd C:\Users\ramze\TenderLens-AI
git fetch origin refs/heads/feat/real-guest-search-gated-20261023
git worktree add --detach "$HOME\VALYQON-WEB-REVIEW" FETCH_HEAD
cd "$HOME\VALYQON-WEB-REVIEW"
& .\ops\website_preview\start.ps1
```

The script builds and starts *only* a new project named
`valyqon-website-review` and checks the real app homepage, then launches
the default browser at:

**http://127.0.0.1:18865/**

It does **not** use the existing AWS private-preview ports 18765/18766,
modify the original checkout or use production databases. It does not start
the Telegram bot or background ingestion. The only published listeners are 127.0.0.1:18865 (site) and 127.0.0.1:18866
(local Mailpit inbox); neither is a public HTTPS domain.

### If you forgot the local preview password

The isolated website preview now includes a local-only Mailpit test inbox.
No test email is sent to Gmail or other external providers.

1. Start/restart the preview with the updated code; it retains the existing
   website_review_data volume and original test accounts.
2. Open http://127.0.0.1:18865/forgot-password and enter the email address
   of **your existing local preview account**.
3. Open http://127.0.0.1:18866/ to view the test message titled
   **Reset your VALYQON AI password**.
4. Open the reset link in that local message, set a new password
   (at least 12 characters) and sign in at http://127.0.0.1:18865/login.

For a *new* local user, use http://127.0.0.1:18865/register; the verification
message also appears at http://127.0.0.1:18866/. The inbox is local and
unprotected beyond its localhost bind: never use personal secrets or
production emails for a demo account.

Do not delete the review volume or run Docker prune; this would erase
local test accounts. These reset links apply only to the separate preview
database, not production/AWS accounts.

### Mailpit is empty after requesting a reset?

The app intentionally responds generically for unknown or inactive accounts
and for requests within the 60-second cooldown. An accepted response is not
proof that a reset email has been sent.

Update the local review worktree and run the latest start.ps1, then run:

```powershell
& "$HOME\VALYQON-WEB-REVIEW\ops\website_preview\diagnose-mail.ps1" -SendProbe
```

The diagnostic confirms the API and local Mailpit are running, verifies the
application's actual SMTP environment, checks HTTP reachability, and sends
one synthetic test email to Mailpit only. At the prompt, enter the TEST
account's email used at http://127.0.0.1:18865 (not a password). It checks
local storage read-only and displays account existence, active and
verification flags without printing the address.

- REVIEW_SMTP_TO_MAILPIT=VERIFIED: test email transport works.
- ACCOUNT_IN_18865_DATABASE=NO: create a new synthetic account at
  http://127.0.0.1:18865/register, then verify via local Mailpit. Accounts
  from the separate AWS private preview on port 18765 are not present.
- ACCOUNT_IN_18865_DATABASE=YES: request reset only once via
  http://127.0.0.1:18865/forgot-password and reload
  http://127.0.0.1:18866/. Wait at least 60 seconds before repeating.
- REVIEW_EMAIL_CONFIG=OLD_OR_INCORRECT or MAILPIT_HTTP=UNAVAILABLE:
  rerun the UPDATED start.ps1 and check the Docker Desktop engine/ports.

The diagnostic does not change passwords, cookies, database rows or any
other VALYQON deployment. Do not copy reset links or tokens into chat.
### Browser acceptance

- Confirm homepage header, gradient, interactive three-step demo and hover/focus.
- Check Guest Search and popular keywords: zero results is **correct** for a fresh
  database. The test window is for the actual UI, not proof of source delivery.
- Check 14-day market chart empty (zero records), support help drawer and
  disabled/unconfigured public AI response.
- Check RU/EN language toggle, mobile viewport and keyboard controls.
- Check that original procurement URLs, buyer names, documents and source
  identities do not appear in guest cards.
- Any paid details must return locked status until merchant-backed
  subscription entitlements are implemented.

### Stop the isolated preview safely

```powershell
& .\ops\website_preview\stop.ps1
```

The isolated test data volume remains intact. Never run
`docker compose down -v` or `docker system prune` against existing stacks.

### If you already have a test worktree

Do not run worktree-add over existing files. Check `git worktree list`, then
update a review-only worktree with `git fetch` and `git -C <worktree> reset
--hard` **only if you are certain it contains no personal changes**.
Otherwise create a different empty review folder.

### What remains blocked for a real launch

- Verify real upstream source → scheduled Worker → shared DB → guest API on a
  *different, authorized integration staging stack*. The UI-only preview
  deliberately has no external source integration.
- Merchant payments, webhooks and subscription entitlements across every
  source-derived delivery channel (issue #266).
- Independent browser E2E and production review before merge/deployment.


## Refresh the existing review worktree for the redesigned version

The initial review checkout (2026-10-23, f7012a6) does NOT automatically receive
new commits. In Windows PowerShell:

```powershell
cd C:\Users\ramze\TenderLens-AI
git fetch origin feat/real-guest-search-gated-20261023

$review = Join-Path $HOME 'VALYQON-WEB-REVIEW'
$pending = @(git -C $review status --porcelain)
if ($LASTEXITCODE -ne 0) { throw 'Review worktree unavailable' }
if ($pending.Count -gt 0) { throw 'Review has local edits; do not overwrite them.' }

git -C $review switch --detach origin/feat/real-guest-search-gated-20261023
if ($LASTEXITCODE -ne 0) { throw 'Review checkout update failed' }

& (Join-Path $review 'ops\website_preview\start.ps1')
```

Open http://127.0.0.1:18865/ after the script confirms
VALYQON_BROWSER_PREVIEW=READY. Docker may take some time rebuilding, but
the commands do not touch the production compose project or original checkout.

### Rich illustrative chart layout in the *local preview only*

For a fresh isolated database, all REAL analytics values are zero and the
guest search correctly returns no notices. The analytics section includes a
visible "LOCAL DESIGN REVIEW ONLY" bar with a
"Show illustrative chart layout" button. Clicking it paints clearly flagged
*invented design values* in the visualization cards for style review. The
yellow disclosure remains visible and repeats that these are NOT real
procurement statistics. Click again to return to the honest DB view.

The button is displayed only when the web process is launched with
VALYQON_WEBSITE_REVIEW_ONLY=1, as it is in the isolated review compose.
Real public deployments do not enable it. No fake tender records are inserted,
the guest search still fetches only actual DB data, and the source/buyer/link
redaction policy is unchanged.


## Public marketing demonstration until a verified data launch

The public launch Compose explicitly sets:

\`\`\`yaml
VALYQON_PUBLIC_ANALYTICS_MODE: "demo"
\`\`\`

This means the public analytics wall **and** the smaller 14-day market-pulse
chart show visibly labelled, invented illustrative values. They are an
**interface demonstration, not actual procurement market counts**. Each area
displays its own disclosure; the premium product hero is watermarked.

It does **not** seed fake tenders into SQLite/PostgreSQL, alter
\`/api/v1/public/opportunities\`, bypass any buyer/source/detail lock, or change
\`/api/v1/public/market-intelligence\` and \`/market-pulse\` API responses.
The real guest search remains empty until actual source records have been stored.

**Switch to real statistics only after verification, not simply after 30 days.**
Requirements: one or more independently verified live source adapters and
Worker ingestion; persisted, dated notice IDs in the shared database; at least
one full source-to-worker-to-database-to-guest-HTTP acceptance; clearly
communicated coverage, freshness and missing-data limitations. Then update
\`VALYQON_PUBLIC_ANALYTICS_MODE\` to \`real\` and redeploy, retaining the
commercial paid-source-details gate until verified billing exists. No date-based
switch or imaginary market growth is implemented.

## Authenticated workspace navigation refresh

The workspace uses the **same existing routes, permissions and data**. New
progressive features include grouped collapsible nav, persistent compact
desktop sidebar, route-highlighted quick shortcuts, and an overview action hub
to discover, saved, monitoring and team. The \`Ctrl+K\` menu remains
navigation-only, not procurement search. No fake tender counters appear in
the signed-in dashboard.
