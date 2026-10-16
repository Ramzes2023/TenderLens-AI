# VALYQON AI — seven Asian sources in operational discovery

**16 October 2026.** Seven official feeds: six Hong Kong procurement/lease/consultancy RSS feeds plus JETRO's *own* Japanese competitive bid RSS. This is **not** seven countries, Japanese nationwide coverage or production activation.

## What is supported

- Six Hong Kong adapters: \`hk_ha_works\`, \`hk_ha_leasing\`, \`hk_emsd_tenders\`, \`hk_emsd_consultancy\`, \`hk_dsd_current\`, \`hk_cedd_tenders\`.
- Japan: \`jp_jetro_bid\`, the official \`https://www.jetro.go.jp/rss/proc_bid.xml\` feed for JETRO's own competitive bids.
- Idempotent hourly UTC job identities, bounded safe network fetching by the existing \`connector.sync.v1\` Worker, lease-fenced writes to \`source_opportunities\`, exact-source stored keyword search and existing organization-scoped discovery/scoring API.
- The user-facing company discovery endpoint already supports **live remote search** when adapters are explicitly enabled; \`POST /api/v1/organizations/{organization_id}/discover/tenders?snapshots=true\` reads the shared persistent connector snapshots in authenticated organization/company context instead. Snapshot mode never secretly fetches HTTP and may return historical results if a worker has not synced.

## Explicit operator enablement (NOT set automatically by merge)

The host must already have a configured, migrated VALYQON database and worker secrets in its trusted deployment environment. Never commit \`.env\` or production credentials.

Set **all** the following in that trusted environment:

\`\`\`sh
VALYQON_ASIA_SOURCES_ENABLED=1
VALYQON_ASIA_JETRO_BID_ENABLED=1
VALYQON_ASIA_OPERATIONS_ENABLED=1
\`\`\`

Verify the seven keys before any storage mutation:

\`\`\`sh
python -m app.sources.asia_seven
\`\`\`

Run the connector worker under your **approved existing process supervisor** (separate foreground process; it must remain running):

\`\`\`sh
python -m app.jobs.worker --connectors
\`\`\`

In a second operator process, enqueue the seven feeds for the current UTC hour:

\`\`\`sh
python -m app.sources.asia_seven --enqueue
\`\`\`

The output includes a distinct job UUID/state for each feed. Jobs process asynchronously in the existing worker. **A queued job is not a successfully fetched tender**; inspect job status with \`python -m app.sources.enqueue --status <UUID>\`. The queue deduplicates repeated submissions of the same source and UTC hour. Configure a trusted external scheduler on the approved host to invoke the **same** enqueue command once per hour, *only after production egress/rate-limit acceptance*. Do not use GitHub Actions as a production database or put production credentials on the personal WSL2 self-hosted runner.

Search previously stored notices locally:

\`\`\`sh
python -m app.sources.asia_seven --search "equipment" --limit 20
python -m app.sources.asia_seven --search "maintenance" --source hk_emsd_tenders
\`\`\`

The search returns bounded real stored notice titles, original verified public links and known metadata; it never sends your private keyword to an upstream website. It does **not** guarantee that notices remain open, or that anything has been fetched recently. The existing organization-scoped UI is for end users; the CLI is an operator diagnostic and not a substitute for customer authorization or subscriptions.

## Acceptance and remaining infrastructure gates

- PR's independent hosted job \`asia-seven-real-queue-search\` must demonstrate all 7 anonymous upstream fetches → actual Worker → disposable SQLite → keyword search → UTC-hour duplicate-job gate (7/7). No fixtures or synthetic result substitution.
- Previous six-source and JETRO individual hosted jobs are separate evidence, not proof of permanent source reachability. Full Linux, Windows, Russian/CIS compatibility checks must also be green on the exact merged commit.
- **Not performed by repository changes alone:** set runtime env on real AWS/production; establish network access to all seven sites from that host; initialize persistent PostgreSQL 16 or intended store; run and supervise connector worker; schedule enqueue; observe failures and stale feeds; verify authenticated tenant search and customer notifications. Do not advertise automatic production delivery or hourly reliability until actually observed.
- Source IDs remain default-off; no AWS resources, user data or prod credentials are modified by this PR.
