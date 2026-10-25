# VALYQON public pilot launch gate — 25 October 2026

This is a **limited public website pilot**, not proof that every Russian platform supplies tenders and not an authorization to accept paid subscriptions. The source results shown to anonymous visitors must come from actual connector rows persisted in the same staging/production database as the API. The deployment and real Telegram acceptance cannot be performed by GitHub unit tests.

## Launch boundaries

- `compose.public.yaml` permits only Caddy to bind a public TCP port. The API and bot remain private to the Docker network.
- `VALYQON_PUBLIC_ANALYTICS_MODE=demo` labels illustrative analytics appropriately. **Do not claim real market KPIs from demo values.** Real saved guest search still requires a genuine official publisher → leased Worker → persistent database proof.
- `VALYQON_RESTRICT_PAID_SOURCE_DETAILS=true` keeps subscription-only data closed. Payment, merchant-signed entitlement and cancellation are not production-accepted. No paid checkout until it is.
- In the public *pilot* Docker profile, `GPB_ETP_PUBLIC_ENABLED`, `ROSELTORG_PUBLIC_ENABLED`, `TEKTORG_PUBLIC_ENABLED`, `B2B_CENTER_ENABLED`, `EIS_44_HTML_ENABLED`, `EIS_223_ENABLED`, and `VALYQON_RU_BACKGROUND_CATALOG_ENABLED` are **forced off in both API and bot**. They cannot be accidentally enabled by an old host `.env`.
- The public-pilot bot runs with `MONITORING_ENABLED=false` until an authorized, real Telegram Bot API message ACK is observed from the same deployment/notification loop. Offline/local fake ACK tests are insufficient.
- This profile is deliberately limited. To enable a newly verified source, use a separate reviewed deployment configuration and a source-owned live acceptance before removing its protective override.

## Operator checks BEFORE exposing the site

From the exact reviewed commit on the authorized deployment machine:

```powershell
python -B -m scripts.ci_public_pilot_release_policy
if ($LASTEXITCODE -ne 0) { throw "Public pilot source safety policy failed" }

# Configure .env with secrets privately; .env.public with domain and ACME email.
docker compose --env-file .env.public -f compose.public.yaml config
if ($LASTEXITCODE -ne 0) { throw "Public compose invalid" }
```

Then, in an isolated staging copy of the exact reviewed commit, confirm HTTPS certificate and redirect; restore an encrypted backup; verify /health and /status.json; verify registration/login, isolation between two distinct organizations, guest search on **persisted genuine notices**, the refusal of locked paid-detail requests (HTTP 403), and UI on mobile.

Read `docs/GUEST_SEARCH_PUBLIC_RELEASE.md`, and run its existing `scripts/accept_guest_search_live.py` **against the actual staging API**. It must find nonempty real saved search data; empty fixtures or an illustrative page do not count. The preflight command above is configuration-only and does **not** pass this live gate.

Before enabling customer notifications, explicitly approve a test Telegram chat, send one genuine publisher-derived message via the running monitor and verify the real Bot API `ok/message_id/chat_id` acknowledgement, then verify retries/dedup and no cross-tenant leakage. This step needs access to the deployment, approved chat and operational secrets; GitHub-hosted offline jobs cannot substitute.

## Russian source release matrix (not raw counts)

| Publisher/integration | Current criterion |
| --- | --- |
| Samara municipal list | Strict first-party list → Worker → SQLite/authorized query and local alert CI previously passed; list-only cards, no authenticated deep-link claim; opt-in requires operator production acceptance |
| Dagestan small purchases | Genuine public list → Worker → SQLite/authorized query and local-only alert acceptance; detail may require login; operator opt-in |
| Leningrad Oblast | Real visible original detail → Worker → SQLite/authorized query previously passed; operator opt-in |
| MikroTon | Current API + authentic detail → Worker → SQLite/authorized query previously passed; operator opt-in |
| Ingushetia EIS/Fabrikant | PR #226 merged with independently checked same-EIS-origin mirror and operator-local Windows/CI evidence; publisher outages are intermittent; production 24/7 Worker and real Telegram ACK not confirmed |
| Chechnya EIS | PR #236 blocked; merged PR #263 is **research** and not an enabled end-to-end connector |
| GPB | PR #252 blocked by official upstream access/real Worker jobs; RSS/HTML GET diagnostics alone are not tender proof |
| Roseltorg | PR #251 blocked by official listing transport/real Worker jobs |
| TEK-Torg | PR #257 blocked by real Worker job; separate official API diagnostics returned HTTP 403 |
| B2B-Center | Do not activate from stale offline/fixture evidence; require current original data and runtime proof |

The platforms above can duplicate individual public 44-FZ EIS notices. Deduplicate by official original identity across publishers; a regional mirror is **not** a new independent procurement.

### Decision

**Static pilot configuration can pass while real source ingestion, production Telegram delivery, merchant billing, DNS/HTTPS and ongoing operations remain unverified.** A full paid, alerting public launch is **NO-GO** until the separate externally observable gates pass. Do not issue a public launch announcement or claim a verified subscriber alert before those checks.
