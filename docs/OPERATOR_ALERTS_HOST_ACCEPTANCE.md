# Phase 24 Operator alert scheduler — host acceptance checklist

These templates are **inactive** and do **not** deploy to AWS/production. They are provided so an operator can configure unattended incident checks once a supported host/runtime is available.

## Verified implemented checks

- Recent failed jobs during the past 15 minutes.
- Expired running-job leases, suggesting that a job stopped heartbeating.
- **Eligible queued jobs waiting more than 15 minutes**, excluding jobs scheduled for the future. A queue can stall even if no job has been claimed.
- Freshness warnings for an **explicit allowlist** of source IDs. Zero tenders may be legitimate; a freshness warning does not prove the portal is down.
- Elevated/rising HTTP 5xx from an explicitly supplied **local Caddy JSON access log**. If absent, the 5xx check reports not configured instead of falsely reporting a healthy service.

Decisions use aggregate read-only SELECTs; customer payloads, prompts, names, emails, job IDs and source URLs are not included in Telegram messages.

## How this will operate (not yet deployed)

Two templates under `ops/systemd` describe a one-shot service and a five-minute calendar timer. The example service is pinned to a dedicated unprivileged `valyqon-monitor` system identity and a host installation at `/opt/valyqon/current`; it does **not** assume the existing AWS container actually has this layout.

Before an operator can use the templates:

1. Verify the actual deployment topology, available Python runtime and database URI injection; adapt the example `WorkingDirectory` and `ExecStart` accordingly. Provision a **read-only PostgreSQL role** with SELECT permissions only on the required tables, or a protected local database read-only connection as supported by the runtime.
2. Provision one private operator Telegram bot and private chat. Store the token and chat ID in a root-managed, non-repository `/etc/valyqon/operator-alerts.env`, chmod 0600; never post them in CI, chat, application logs or GitHub. Limit operator account access. Populate `VALYQON_OPERATOR_ALERTS_ENABLED=1`, `VALYQON_OPERATOR_TELEGRAM_BOT_TOKEN`, `VALYQON_OPERATOR_TELEGRAM_CHAT_ID`, `VALYQON_OPERATOR_ALERT_STATE_FILE=/var/lib/valyqon-operator/alerts.json`, `VALYQON_OPERATOR_EXPECTED_SOURCES` and optional `VALYQON_OPERATOR_CADDY_LOG`. Also supply the database settings expected by `load_database_settings`.
3. If 5xx alarms are needed, enable JSON access logs on the reverse proxy and grant only the monitor identity read access. **Do not enable public metrics endpoints.** Validate file permissions and log retention.
4. Execute the read-only CLI **without** `--send` against staging first, inspect exit status and the bounded alert codes. Test failure injection with only synthetic queued and failed jobs and a local HTTP 5xx log sample.
5. Verify a private Telegram test message is received using a non-production test bot/config, then check rate limiting and failure/timeout handling. Do not enable the timer until checks succeed.
6. Install the reviewed service/timer manually on the actual host and enable it **only with explicit deployment approval**. Verify the scheduler runs every five minutes, sends for stalled eligible queues, and stops duplicating alerts within one hour.
7. Install an **independent external heartbeat/dead-man monitor** or host-level alert for failed checks. If the entire server is powered down, a systemd timer and the application Telegram bot cannot alert anyone. Validate notification delivery by failure injection at least once after deployment.

Example install and activation commands are intentionally not executed by this PR. Production automation, secrets and user data stay out of Git.

## Safety and operational limitations

The local de-duplication state is designed for a **single scheduled instance**. The provided systemd service uses `flock -n` so overlapping invocations on one host do not send simultaneous messages; a multi-host deployment requires a durable shared notification lock.

The operator's database credentials must not have write privileges. The Caddy log reader examines only the last 2 MiB of logs; in high-throughput deployments use an external log aggregator and appropriate incident time windows.

Queue age cannot prove that a worker process is down: capacity limits, intentionally held admissions and infrastructure outages can also create backlog. Tune alert thresholds after measuring real traffic. 5xx rate is a proxy-log indication only, and cannot account for errors suppressed before logs are emitted.

This is a **template and checked-in regression change**, not a claim of live 24/7 paging. A dedicated independent paging path and real operator credential configuration remain mandatory.
