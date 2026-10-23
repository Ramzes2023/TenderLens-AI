# VALYQON AI — test the redesign in a real browser on Windows

**Status:** a real local app preview (not a screenshot/mockup). It uses the
actual landing Python route, CSS, JavaScript and guest REST endpoints from
PR #264. No production data, SMTP/Telegram delivery, payments or source
workers are attached. Guest result list is empty until legitimate notices are
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
the Telegram bot or background ingestion. The only local endpoint published
is 127.0.0.1:18865; it is not a public HTTPS domain.

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
