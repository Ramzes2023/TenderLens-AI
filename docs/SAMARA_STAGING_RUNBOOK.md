# Samara staging and release gate

Official public registry: https://webtorgi.samregion.ru/smallpurchases/GzwSP/NoticesGrid.
Only list metadata is verified. Numeric detail cards and documents are not proved.
Date-only deadlines remain date-only; do not advertise an inferred closing time.

## Local acceptance (no recipients or production writes)

Use Python 3.12 and `pip install -r requirements-dev.txt PyYAML` in an isolated venv.

```sh
python -B -m scripts.research_ru_samara_third_page
python -B -m scripts.ci_ru_samara_three_page_worker_sql
python -B -m scripts.ci_ru_samara_authenticated
python -B -m scripts.ci_ru_samara_telegram_query_delivery
```

The 30-row gate requires price, publication, deadline, buyer and title on every
original, searches all 30 IDs from disposable SQL, and rejects duplicate inserts.
The delivery gate uses live procurements and a LOCAL transport: failure leaves
the notice unseen, then a successful local retry claims it. This is not evidence
of Telegram API delivery. These scripts are development tools outside the image.

## Separate Docker staging project

`compose.samara.staging.yaml` is standalone. Do not combine it with production
Compose files. Its own volume stores `samara-stage.db`; do not import customer
subscriptions or use a production bot token. Docker must be installed separately.

Create a gitignored `.env.samara-staging` from only the settings needed for the
test. Keep `MONITORING_ENABLED=false` initially. For Telegram use a dedicated
test bot and only the user-authorized test account. Enter credentials securely;
do not print the file or expanded `docker compose config` output in logs.

Set `SAMARA_STAGING_ENV_FILE` to that file in the shell, then:

```sh
docker compose -f compose.samara.staging.yaml config --quiet
docker compose -f compose.samara.staging.yaml up --build -d api worker
docker compose -f compose.samara.staging.yaml exec worker python -m app.sources.enqueue --source ru_samara_public_list
docker compose -f compose.samara.staging.yaml exec worker python -m app.sources.enqueue --status JOB_UUID
```

The existing worker owns queue leases and fenced writes; enqueue is a one-shot
operator action with hourly idempotency, not a scheduler. Require `succeeded`,
30 accepted/inserted rows on the first sync and no duplicate rows on replay.
Inspect the API at `http://127.0.0.1:18080` using an isolated test organization.
Repeat keyword, negative-query and organization-isolation checks there.

After a test account is explicitly authorized, enable monitoring in the dedicated
staging file and start only the test bot:

```sh
docker compose -f compose.samara.staging.yaml --profile telegram-test up -d bot
```

Use `/tenders` from the authorized account for current matches. `/monitor_on`
baselines existing matches, so lack of immediate alerts after subscribing is
expected. Verify the actual Telegram message and its original purchase number;
never treat local capture or a bot process start as a delivered message. Test
delivery failure/retry locally, without disrupting a production token or chat.
The monitor queries the live catalog; the queued connector separately persists
snapshots. Do not claim the notification path reads Worker SQL snapshots.

Stop staging with `docker compose -f compose.samara.staging.yaml --profile
telegram-test stop`. Preserve its volume; never use `down -v` on customer data.

## Release

Require all agreed exact-HEAD CI gates, then merge without bypassing checks.
Keep research PRs #191 and #99 separate unless actual detail-level data proves
their contracts. PR #221 repairs the separate B2B worker request budget; a red
B2B gate is not proof that Samara failed and must not be disabled to merge it.
Before changing a production server obtain explicit user confirmation of the
server, revision, database, enabled source, worker and test notification account.
Production launch and real Telegram delivery remain unverified until separately
observed. This runbook does not authorize a production deployment.
