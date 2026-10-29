# V6 → Telegram: safe read-only bridge gate (staged, no sends)

The 29 Oct 2026 operator audit showed **six** real isolated source jobs running and one enabled `monitor_subscriptions` row in the **separate** production customer database. The old `tenderlens-vps-bot-1` was exited (137, `OOMKilled=false`), and the bot did **not** have V6 RU-catalog flags. Different API/bot image digests are evidence of a deployment difference, **not proof of the cause** of SIGKILL.

## Boundary

`app.monitoring.v6_bridge_readiness` is a strictly **read-only** readiness check. Two *existing* SQLite databases must be supplied on separate read-only mounts by a trusted operator:

- V6 sources: `/app/data/isolated-public-sources.sqlite3`, currently inside Docker volume `valyqon-lenobl-trial_public_source_data` (verify using live Docker inspect, do not infer from a stale Compose file).
- Customer subscriptions and company profiles: `/app/data/tenderlens.db` in the real production API's **own** mounted volume (discover via `docker inspect tenderlens-vps-api-1`, do not guess its volume name).

Example **inside a reviewed, offline container with both volumes mounted read-only**:

```sh
python -m app.monitoring.v6_bridge_readiness \
  --sources-db /v6/isolated-public-sources.sqlite3 \
  --customer-db /customer/tenderlens.db
```

Do not run the script in `tenderlens-vps-api-1` with writable source access or reconfigure existing containers to share writeable volumes. It prints only aggregate counts. There are no network calls, external token access, SQL writes, migrations, profile contents, chat IDs, owner identifiers, company names or tender titles in output.

The preflight blocks if either database is missing/corrupt, schemas are missing, any of the six latest real Worker receipts has not succeeded recently, there are no fresh safely-open first-party Samara-list candidates, or any active Telegram subscription lacks a corresponding active company profile with explicit search/product keywords.

**Important:** A green `CANDIDATE_ONLY` is **NOT** authorization to send. There is no native direct V6-DB-to-Telegram delivery pipeline yet. The legacy bot downloads from sources separately, and `MONITORING_ENABLED=true` alone does not enable all six. The isolated public V6 containers intentionally have `TELEGRAM_BOT_TOKEN` empty and `MONITORING_ENABLED=false`.

## Future real-send gates

Require an independently reviewed source-to-subscriber authorization boundary, explicit opt-in to this new form of notification, a source-owned future original, company-owned keyword filtering, per-chat limits, safe buyer/detail redaction, a transactional per-recipient dedup/retry outbox, actual Bot API acknowledgement, no token logging, and rollback preserving both isolated V6 and production API/SQLite. Do not restart the old bot or enable the public `verified-bot` profile to substitute for these proofs. The existing one subscriber must not receive unsolicited backlog.
