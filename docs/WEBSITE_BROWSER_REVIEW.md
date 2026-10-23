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
