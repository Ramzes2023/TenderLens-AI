# VALYQON AI — guest search and website release acceptance

2026-10-23 • Feature branch feat/real-guest-search-gated-20261023 • PR #264

## What is implemented

- Guest search GET /api/v1/public/opportunities reads real saved connector notices from the shared source_opportunities table, not synthetic/demo tender cards and not private tenant data. It scans a bounded recently updated subset; it is NOT an exhaustive procurement portal search or an external live fetch on every request.
- Guests receive only title, initial_price, currency and deadline. There are no per-notice original links, platform names, buyer, external IDs, documents, full summaries or participation terms.
- Matching uses a redacted title only. URLs, emails and exact normalized buyer strings (when detected) are removed. Unstructured upstream titles may still leak unknown embedded names; manually review real connector notice headlines before public release.
- Hero product scene is explicitly illustrative; the 14-day market chart instead uses real first-observed persisted notices from a bounded recent sample.
- Guest product AI uses a configured LLM only when explicitly enabled; disabled by default with VALYQON_PUBLIC_AI_ENABLED=false. This does not inspect source or tenant DB content. Its in-process rate limit is not sufficient for public internet abuse protection without edge controls.

## Before public exposure

- The public Docker Compose config explicitly sets VALYQON_RESTRICT_PAID_SOURCE_DETAILS=true. This deliberately blocks source-derived detailed web API access in discovery, history, shortlist, activity, analytics, source scans, exports and scoring runs while there is no verified merchant billing. Even registered users cannot open these endpoints yet.
- This is NOT a real subscription system. Merchant-signed checkout/webhooks, cancellation, expiry, entitlement verification and notifications/Telegram gating are still required. Never turn off the temporary lock just to make paid data accessible. Track in issue #266.
- Existing user-owned uploaded document workflows are separate from source-derived tender records.

## Staging E2E gate (operator only)

1. Deploy the exact reviewed feature commit in an isolated authorized STAGING environment (not production). For real source evidence, use a separate integration staging database and Worker; the isolated AWS private preview deliberately blocks external sources and is for UI-only testing.
2. Prove approved upstream platform => queue => actual Worker => normalized source_opportunities writes with genuine original IDs, URLs and persisted observations. Keep restricted evidence confidential.
3. Point the API at that same database. On the trusted machine use PowerShell:
   
       $env:VALYQON_ACCEPTANCE_BASE_URL = 'http://127.0.0.1:8000'
       py -3.12 -B scripts/accept_guest_search_live.py
       if ($LASTEXITCODE -ne 0) { throw 'Guest acceptance incomplete' }
   
   The smoke script requires a reachable homepage, nonempty real persisted guest results, allowed projection fields, no-cache responses and a factual market graph. It prints counts only. It cannot independently establish upstream evidence or payment readiness.
4. Try direct HTTP calls to each locked detail URL while the prelaunch lock is enabled; they must return HTTP 403 with PAID_SOURCE_DETAILS_LOCKED, whether or not the caller has a session. Also manually inspect bot/Telegram and email notification delivery for possible bypass.
5. Test the website in a real browser at desktop/mobile sizes: search, empty state, errors, card navigation locked, registration, language switch, guest AI disabled-state, keyboard controls, help drawer and reduced motion.
6. Require exact-head CI green including Docker, independent source acceptance green, and browser/production readiness before merging or deploying.

## Honest review links

- Operator-only private AWS browser preview uses the previously verified local SSH tunnel at http://127.0.0.1:18765/ (after deployment from the selected reviewed code), NOT a public URL. It does not contain real tender ingestion.
- No verified new public staging/production website URL exists yet. Do not announce a public review link until actual HTTP and browser tests confirm it.
