# Ingushetia follow-up, isolated clone, 2026-10-19

Base: PR #222, `feat/ru-ingushetia-eis-live-gated-20261019`,
`b5414553d2630b4145b9336a0dde7c5ae8a9bf13`. No production changes.

## Confirmed defects and fixes

- `regions=06` is not a working EIS regional selector: a genuine local
  response contained Lipetsk/Moscow buyers. The adapter correctly rejected
  those rows. Replaced this guessed selector with the public EIS text search
  for `Ингушетия`, retaining mandatory publisher-owned customer/region proof.
  This conservative search does not guarantee exhaustive regional coverage.
- Fabrikant's public GET form exposes `placer_search_str` for organizer
  name/INN. The correct current list is
  <https://44.fabrikant.ru/44/catalog/procedure/published?placer_search_str=0608058533&order=publication_datetime&dir=desc>.
  `q` is not the organizer field. Actual HTML contains regional current rows.
- Title cells contain preference badges. Parse the title anchor separately
  so `СМП/СОНО` and `1875` cannot contaminate original-card title validation.
- The acceptance monitor previously overrode fetching with an in-memory list.
  It now uses the actual Worker SQL repository, production snapshot catalog,
  production monitoring service and monitor loop. Receipt assertions respect
  SQL ordering after idempotent replay updates `last_seen`.
- Required Ingushetia acceptance and diagnostics now also run for PRs targeting
  the requested feature branch, rather than only PRs targeting `main`.

## Actual current notices, independently fetched official marketplace cards

Organizer on each card: КОМИТЕТ ГОСУДАРСТВЕННОГО ЗАКАЗА РЕСПУБЛИКИ
ИНГУШЕТИЯ, INN `0608058533`, in the organizer section. Each detail H1 and
title matches the separately fetched current official listing. This is an
accredited mirror of EIS originals, not a second independent publisher.

| EIS original number | Procurement | Listing publication | Official card |
|---|---|---|---|
| 0114500000826002390 | Поставка ГСМ (Бензин АИ-95) | 19.10.2026 17:01:05, site display | https://44.fabrikant.ru/44/procedure/ea21/0114500000826002390 |
| 0114500000826002391 | Капитальный ремонт медицинского мобилизационного центра «Резерв» | 19.10.2026 15:18:40, site display | https://44.fabrikant.ru/44/procedure/ezk21/0114500000826002391 |
| 0114500000826002364 | Поставка лекарственных средств | 16.10.2026 17:01:50, site display | https://44.fabrikant.ru/44/procedure/ea21/0114500000826002364 |

Live execution: `python -B -m scripts.ci_ru_ingushetia_fabrikant_worker`:
three genuine originals, real leased Worker `succeeded`, three rows in
disposable SQLite, number/title search, positive keyword/region profile,
excluded-keyword rejection, unrelated-query rejection, idempotent replay,
three simulated notification acknowledgements. The monitor reads that same
SQL database. Evidence: `artifacts/ingushetia-live-worker-20261019.txt`.
Temporary SQL files are closed and removed; no production database is used.

Strict combined live acceptance also passed via Fabrikant, explicitly reporting
`REAL_USER_TELEGRAM_RECEIPT=NOT_TESTED`.

## Remaining limits and external blockers

- EIS text RSS really returned five regional buyer-confirmed notices, including
  `0114100000126000011`, `0114100000126000012`, `0114500000826002384`,
  `0114500000826002383`, `0114500000826002382`. Its separate acceptance failed
  fetching the first original EIS card with `ConnectorTransportError`.
  Do not present the Fabrikant pass as direct EIS card reachability.
- Previous hosted CI on PR #222, run `39261240944`, failed with EIS
  `ConnectError` and Fabrikant `ReadTimeout`. Earlier runs had `ConnectTimeout`.
  These are environment-specific transport failures, not parser/TLS evidence.
- GitHub runner inventory: `VALYQON-RU-01` offline, not busy. Existing domestic
  diagnostic run `39259094528` remains queued. No runner, process, Docker,
  other clone or other branch was modified. Local reachability is not proof
  of reachability from a Russian deployment network.
- No GitHub environments were listed. No authorized test bot configuration
  or test chat was supplied. Actual Telegram API delivery is **NOT TESTED**;
  the isolated sink is only generation/acknowledgement/dedup evidence.
- Live crossfeed proof subsequently passed: `2390` and `2391` were independently
  acquired from current Fabrikant cards and actual EIS number-filtered RSS.
  Two real Worker jobs succeeded, stored four source rows in disposable SQL,
  and collapsed them to two original identities. After two mirror notification
  acknowledgements, the actual EIS rows produced zero repeat alerts. Evidence:
  `artifacts/ingushetia-crossfeed-20261019.txt`; repeat with
  `python -B -m scripts.ci_ru_ingushetia_crossfeed`. This verifies EIS RSS
  acquisition, not availability of direct EIS HTML cards or Telegram delivery.
- Both sources remain opt-in/default OFF. Keep the follow-up PR draft and
  unmerged until real authorized Telegram delivery and all required CI pass.
  No failed checks were disabled, no fixtures used as live evidence.

## Repeat locally in this clone

Create an isolated venv and install `requirements-dev.txt`, then run:

```powershell
python -m pytest -q tests/test_ru_ingushetia_eis44.py tests/test_ru_ingushetia_fabrikant44.py tests/test_ru_source_integration_contract.py tests/test_ru_original_notice_identity.py tests/test_ru_tenders_confirmed_send.py
python -B -m scripts.ci_ru_ingushetia_fabrikant_worker
python -B -m scripts.ci_ru_ingushetia_live_worker
```

Offline contracts: **64 passed**, plus **152 passed** in Worker/jobs/monitoring
regressions. These are separate from genuine live acceptance above. Follow-up
draft PR: <https://github.com/Ramzes2023/TenderLens-AI/pull/226>. No merge.

## Second follow-up: live CI and RU host inspection (2026-10-19)

- PR #226 run 39298360268 failed upstream transport: EIS ConnectError,
  Fabrikant ReadError. Contract jobs passed. Failed job rerun requested;
  no checks disabled or success substituted.
- Fixed Windows cp1252 UnicodeEncodeError when printing a successful live
  result: evidence JSON now escapes Unicode without changing its data.
- Corrected stale regions=06 and Fabrikant q= URLs in the fixed RU diagnostic.
- Current repeat: 71 focused tests and 141 jobs/Worker/monitoring tests passed.
  Initial sandbox run hit pytest shared-temp access denial; rerun used a
  clone-local --basetemp. No application failure was hidden.
- Fresh genuine live acceptance PASS via Fabrikant: three originals, Worker
  succeeded, SQL/title/number search, user region/keyword/exclusion filtering,
  three isolated notification acknowledgements. Crossfeed PASS: two actual
  EIS RSS originals plus two Fabrikant originals, four SQL rows, two unique
  results, zero repeat EIS alerts. See followup artifacts. Direct EIS HTML
  cards and Telegram delivery are still not proven.
- VALYQON-Runner WSL was stopped; started only this dedicated distribution
  for read-only inspection. Its registration confirms RU-01 / agent 21.
  No listener/Worker or runner systemd service was running; /mnt/c is not
  mounted. Other distributions and Codex folders were not modified.
- Direct no-proxy country observation from this WSL: country RU,
  egress 94.232.94.3. Real filtered Fabrikant catalog HTTP 200 / 124422 bytes;
  original 0114500000826002390 HTTP 200 / 140810 bytes. These are transport
  observations, not full Worker acceptance from Linux.
- Direct RU EIS RSS failed curl 60 (root absent from Linux trust store).
  Attempt to supply project CA through /dev/stdin failed curl 77; no TLS
  bypass was attempted. Need a readable CA bundle containing the verified
  project root on the RU host and another direct EIS RSS/card test.
- Persistent listener start was rejected by automatic approval review:
  enabling it can claim future unreviewed jobs. It remains offline; no
  indirect workaround was attempted. Operator approval / reviewed queue and
  safe runner execution policy are required before enabling the listener.
- Repository Actions secret names, variable names, environments, and current
  process Telegram-related configuration inventories were empty. Required:
  dedicated test TELEGRAM_BOT_TOKEN, explicit authorized test chat ID, and
  confirmation that this bot may send test procurement alerts to that chat.
  Do not use a production subscription as an implied test authorization.
- PR remains draft/unmerged. Hosted live transport, runner listener recovery,
  direct EIS access from RU, and actual Telegram receipt remain open gates.


## 20 October 2026: fresh operator-local EIS full-chain acceptance

The operator supplied PowerShell stdout from the existing isolated Ingushetia
checkout after a `git pull --ff-only` to PR #226 commit `17ae0f5`.
The command executed `python -B -m scripts.ci_ru_ingushetia_live_worker`
on that Windows host. This is *operator-provided local execution evidence*,
not a GitHub-hosted run, signed attestation or production confirmation.

The pasted output reported:
- `RU_INGUSHETIA_LIVE_UPSTREAM=official_eis_rss`
- `RU_INGUSHETIA_LIVE_ACCEPTANCE=PASS` and `LIVE_TEST_EXIT_CODE=0`
- `FAILURE_ROUTE_SUMMARY=[]`
- Worker `succeeded`, 10 EIS regional notices stored and searchable in
  disposable SQLite, two actual first-party EIS HTML originals independently
  checked, replay duplicates 0, isolated monitor sink dispatches 2.
- Original EIS 44-FZ IDs `0314100001626000010` and
  `0314100001626000012`, Rosreestr for Ingushetia.
- `REAL_USER_TELEGRAM_RECEIPT=NOT_TESTED`;
  `PRODUCTION_CHANGED=NO`.

These newly confirmed IDs demonstrate a genuine accessible local acquisition.
The output does not demonstrate broad Ingushetia buyer coverage, a user-specific
keyword profile, persistent scheduled production operation or Telegram Bot API
acceptance. They must not be conflated with the separate three committee
originals from Fabrikant.

The exact-head hosted mandatory gate remained red because direct GitHub-hosted
HTTPS from Windows and Linux failed EIS/Fabrikant before an HTTP response
(see native curl diagnostic run 39402379505). Green local acceptance is
strong evidence that the code works from at least one source-reachable
network, but does **not** justify disabling the independent hosted gate or
merging production.

On PR #226, `scripts/ci_ru_ingushetia_live_worker.py` was subsequently
simplified to one real leased Worker RSS acquisition: the two independent
EIS card GETs are now against the actual persisted Worker rows, not rows
from a separate earlier RSS fetch. An offline regression verifies this.
There is no claim yet that the revised exact-head code has passed local
or GitHub-hosted live acceptance.

## 20 October 2026: second operator-local PASS after EIS single-fetch repair

The operator pasted a fresh PowerShell transcript showing a clean
`git pull --ff-only` advancing the isolated Windows checkout from
`17ae0f5` to `a12b2b9` and an actual execution of
`scripts.ci_ru_ingushetia_live_worker` on the new commit.

Reported output (operator-provided stdout, **not** CI attestation):
- `FAILURE_ROUTE_SUMMARY=[]`
- `RU_INGUSHETIA_LIVE_UPSTREAM=official_eis_rss`
- `RU_INGUSHETIA_LIVE_ACCEPTANCE=PASS`
- `LIVE_TEST_EXIT_CODE=0`
- Leased Worker state `succeeded`; 10 genuine publisher-region-
  corroborated EIS notices persisted in disposable SQL and searchable
  by notice number and title; two independently retrieved EIS original
  HTML cards verified from the same persisted Worker notices.
- Current independently verified EIS original numbers
  `0114500000826002380` and `0114500000826002381` from the
  Ministry of Health of the Republic of Ingushetia.
- Two *isolated fake-sink* monitor dispatches; replay duplicates zero;
  `REAL_USER_TELEGRAM_RECEIPT=NOT_TESTED`; production unchanged.

This corroborates that the revised **single real Worker RSS acquisition**
method still passes an actual local network test, with genuinely different
first-two EIS original IDs than the prior local run. It does **not**
demonstrate new publication between two polling cycles, complete coverage
of regional buyers, persistent cloud operation or a real Telegram send.

The same PR head's 207 strict GitHub contract tests passed. Hosted live
acceptance stayed blocked on inaccessible Russian first-party routes;
independent native curl failed from hosted Linux *and* Windows. No
workaround, fixture, or bypass may mark the hosted gate green. Both
regional source flags remain opt-in/default OFF and PR #226 stays draft
and unmerged pending approved operational acceptance.

## 22 October 2026: subscriber fan-out reliability under intermittent access

GitHub Actions job `ingushetia-real-publisher-original-worker-search` at
head `d9cc153` returned `BLOCKED` for both direct EIS and accredited
Fabrikant routes after three real durable retries. Contract tests and
operator-queue tests passed. Historical hosted first-party Fabrikant PASS
on 20 October does not imply that the source is consistently reachable.

The bot's existing per-subscriber Russian-catalog loop independently
issued full remote HTTP fetches for *each* subscription. For the two
fixed Ingushetia regional routes, these requests do not use
subscriber-specific upstream search terms, so repeating them for
every subscriber wastes the limited source-reachable egress window.

Commit `334f0e5` changes only the configuration where **all**
enabled Russian catalog source keys are a nonempty subset of
`{ru_ingushetia_eis44, ru_ingushetia_fabrikant44}`:
one source-catalog fetch per monitoring cycle is distributed across
subscribers **after** their individual, locally resolved company
keyword/region/exclusion profiles are applied. The existing
`unseen_matches`, real Bot API message/chat acknowledgement and
`claim_new` remain individually scoped per subscriber. If all sources
fail, no alert is claimed; partial source success can still generate
alerts from the healthy source. This does not cache or invent a
fresh tender and does not make an unreachable upstream work.

If a profile-specific `eis` or any other RU source is enabled, the
old per-owner fetch behavior is preserved; this change must not silently
broaden a user's RSS query or expose their monitoring profile to
other users. In particular, the existing default EIS profile-feed
registration may remain enabled, so this optimization activates only
in an operator-managed Ingushetia-only catalog configuration.

Offline tests cover two subscribers with mutually exclusive keywords,
a full source outage, and a mixed EIS source configuration. These
are synthetic test conditions, not live Bot API delivery evidence.
This change is PR-only, default source flags remain OFF and there
is no production change, merge, remote runner enablement or
unauthorized Telegram send.


## 22 October 2026: manual-only Telegram Bot API acceptance prepared

New `.github/workflows/ru-ingushetia-test-telegram-optin.yml`
is an **optional** one-shot transport test for a separately provisioned test
bot, not a source acceptance or production user alert. The workflow is not
triggered by a push, PR or schedule. It is deliberately blocked unless an
operator explicitly selects `authorize_test_send` and types the exact
numeric dedicated test chat ID. The workflow requires:

- GitHub Actions secret `VALYQON_INGUSHETIA_TEST_BOT_TOKEN`: token for a
  newly created **non-production** test bot; never enter it in issue text,
  source files, commits or chat.
- GitHub Actions repository variable `VALYQON_INGUSHETIA_TEST_BOT_ID`:
  numeric ID that must equal the token prefix and the Telegram `getMe` ID.
- GitHub Actions secret `VALYQON_INGUSHETIA_TEST_CHAT_ID`: numeric dedicated
  authorized test-chat ID. Operator must confirm the same ID manually.

The explicit test sends at most one quiet message clearly labelled
`ТЕСТ доставки`, checks `getMe`, `getChat` and Telegram's returned
message ID/chat ID, and never retries after a potentially ambiguous send.
Actual receipt visible to the test-chat participant is **not automatically
proven** by Bot API acknowledgement, nor does the synthetic message prove
actual real-tender notification end-to-end. Repository/production bot tokens
and customer subscriptions are not consulted.

A GitHub `workflow_dispatch` workflow must normally exist on the default
branch for the ordinary GitHub Actions manual **Run workflow** interface;
keeping PR #226 unmerged can therefore leave this UI unavailable. Do not
merge solely to test Telegram. A local isolated test using
`python -B -m scripts.ru_ingushetia_telegram_test --send --confirm-test-chat <numeric-test-id>`
with the same dedicated `TEST_TELEGRAM_*` environment variables is an
alternative, but it requires separate operator authorization. Until then
status remains `REAL_USER_TELEGRAM_RECEIPT=NOT_TESTED`.

**The new workflow is configuration-only and does NOT dispatch a send.**


## 22 October 2026: opt-in notification reads from fresh Worker SQL

Implemented a strictly **default-disabled** monitoring route for Ingushetia.
The regular bot originally read live catalog adapters again on each monitor
cycle, even when `connector.sync.v1` Worker had already stored the same
official notices in SQL. A source failure between Worker ingestion and
subscriber notification could make those proven rows invisible to users.

The new operator switch
`VALYQON_RU_INGUSHETIA_WORKER_SQL_ALERTS_ENABLED=true` requires
`VALYQON_RU_BACKGROUND_CATALOG_ENABLED=true`,
`MONITORING_ENABLED=true` and at least one explicitly enabled regional
adapter (`RU_INGUSHETIA_EIS44_ENABLED` or
`RU_INGUSHETIA_FABRIKANT44_ENABLED`). It replaces **only** those selected
regional registrations with read-only `FreshIngushetiaWorkerSource` entries
in the runtime catalog. Tenant-specific EIS and all unrelated RU sources
retain their existing network behavior. An enabled bot process reads the
same configured SQL database used by the separately running operator-approved
connector Worker and hourly queue.

The regional snapshot adapter requires a `source_opportunities.last_seen`
UTC timestamp no older than **4500 seconds (75 minutes)**. It rejects absent, expired or
implausibly future-dated Worker SQL and returns only rows observed within
that same freshness window. It **never** falls back to an HTTP request,
does not fabricate tenders and does not mark any alert delivered when its
source is stale. Non-regional historical saved-search reads stay unchanged.
The user's keyword/region/exclusion profile, original 44-FZ cross-platform
identity and Telegram message/chat acknowledgement are still enforced by
the normal TenderMonitorService and monitor_loop.

Important operational limitations: this is **not an automatic scheduler**.
The operator still must periodically enqueue both approved sources using
`python -m app.sources.enqueue --ru-approved` with their individual flags,
and run the approved `python -m app.jobs.worker --connectors` process
against the SAME DATABASE_URL as the bot. If the worker is stopped, the
snapshot goes stale after 75 minutes and notification attempts remain
unclaimed. Successful ingestion with **zero** verified notices also
produces no fresh row, and therefore fails closed instead of falsely
claiming a healthy empty upstream response. No public customer bot,
production infrastructure, real Telegram chat or persistent worker was
enabled by this PR.

Offline tests are in `tests/test_ru_ingushetia_worker_sql_alerts.py`.
They are synthetic SQL and freshness tests, not live delivery evidence.
Full-chain operator-supplied local and hosted Fabrikant source acceptance
remain separately documented above. The separate manual-only authorized
test Telegram Bot API receipt is **still NOT TESTED**.


## 22 October 2026: hourly queue / notification freshness alignment

The operator enqueue API deliberately deduplicates jobs by **UTC hour**.
The initial Worker SQL alert source TTL of 30 minutes could therefore
produce a silent gap for part of every otherwise successful hour.
Adjusted only the strictly opt-in Ingushetia Worker SQL notification
snapshot to a maximum of **75 minutes** (one hourly interval plus 15 minutes
of scheduling/processing drift); this does **not** relax publisher-origin
verification or bypass failed upstream Worker acquisition. Data older than
75 minutes still fails closed, and historical source rows cannot be silently
marked delivered. The new offline regression verifies a real stored notice
remains readable after 68 minutes but fails closed after 76 minutes.
No recurring scheduler, Bot API delivery or production source activation was
performed by this change. Operational continuity still requires a properly
approved source-reachable, recurring enqueue/Worker process.


## 22 October 2026: approved UTC-hourly regional enqueue (not deployed)

Added `scripts/ru_ingushetia_hourly_enqueue.py` as a strictly opt-in
queue-only process for the two individually operator-enabled sources
`ru_ingushetia_eis44` and `ru_ingushetia_fabrikant44`. No other Russian
sources can enter this regional loop. Normal invocation without explicit
authorization fails without opening any database:

- CLI must contain `--authorize-queue-only` plus either `--once` or
  `--hourly`.
- Environment must explicitly set
  `VALYQON_INGUSHETIA_QUEUE_APPROVED=YES_INGUSHETIA_QUEUE_ONLY`.
- At least one of the two source flags must be enabled individually.
- The runtime calls existing `ConnectorSyncService.enqueue` using a UTC
  clock and the existing durable `connector.sync.v1` job implementation.
  It writes actual queue records, and therefore **must not run against
  production until deployment is separately authorized**.
- `--hourly` checks the UTC hour every 30 seconds, enqueues once each
  hour and uses actual database-backed source + connector version +
  UTC-hour idempotency so process restart in that hour cannot duplicate
  jobs. Importing the module creates no job, subprocess or HTTP request.

This queue-only process is not a Worker, source scheduler service
deployment, monitoring bot or Telegram send. Continuous operation
requires an explicitly approved separate connector Worker
(`python -m app.jobs.worker --connectors`) using the identical
`DATABASE_URL` and configured source flags. The opt-in monitor mode
`VALYQON_RU_INGUSHETIA_WORKER_SQL_ALERTS_ENABLED=true`, enabled
monitor, account subscriptions and a working authorized Telegram
bot are separate requirements.

An offline contract verifies that two target source flags enqueue two
real durable SQL jobs, a process restart reuses the same UTC-hour IDs,
and the next hour creates fresh IDs. It also verifies that an unrelated
RU flag cannot enqueue through this narrow scheduler and that missing
authorization makes no DB call. No listener, hosted runner, scheduler
process, production database or Bot API was started by this PR.

The earlier Worker SQL notification TTL was also aligned to this
hourly idempotency: 75 minutes, allowing 15 minutes of processing and
scheduling drift beyond a normal 60-minute cycle. If not updated by
then, regional notifications fail closed rather than presenting historical
saved searches as current observations.


## 23 October 2026: hosted upstream outage and conservative partial SQL status

On PR #226 head `36396d0` (22 October push), GitHub-hosted mandatory
live acceptance [run 39843561110](https://github.com/Ramzes2023/TenderLens-AI/actions/runs/39843561110)
failed both live routes after **three real queue retry attempts**.
The safe diagnostic classified both EIS and accredited Fabrikant as
`UPSTREAM_NETWORK_RETRIES_EXHAUSTED` with `connection_failure_unspecified`.
The 285 strictly offline contract tests, approved queue contract, and
observational diagnostics passed. There is no new evidence of certificate
verification failure, and no parser patch can honestly turn these
connection failures into newly fetched tenders. A previous genuine hosted
Fabrikant full-chain PASS (20 October, run 39407402210) remains valid as
historical evidence, **not** an uptime guarantee.

Operator-only runtime status now reports
`fresh_sql_source_count`, `not_fresh_sql_source_count` and
`partially_fresh_sql_observed`, alongside per-source states. When only
one of two explicitly enabled regional Worker SQL sources has recent
verified source-keyed persistence, the other remains marked unavailable:
the overall result stays `NOT_OPERATIONALLY_READY`, exit code remains 2,
and `current_upstream_reachability_proven` /
`telegram_bot_api_receipt_proven` stay false. This is strictly
read-only; no queue, scheduler, bot, user notification or production
change occurs. It avoids hiding a partial source recovery, while never
turning an old SQL row into a live publisher acceptance.

The unresolved operational requirements remain: source-reachable
persistent and approved deployment, current hourly queue/Worker
execution against shared SQL, and explicit isolated test Bot API
acknowledgement plus recipient confirmation. Do not enable the shared
offline runner, modify TLS trust or merge a red mandatory CI gate.
