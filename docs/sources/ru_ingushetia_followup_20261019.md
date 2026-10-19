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
- Cross-EIS/Fabrikant canonical dedup has synthetic regression coverage;
  fetching the same original from both live feeds is not yet demonstrated.
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

Offline contracts at this stage: **64 passed**. Those are separate from the
genuine live Worker acceptance above. No merge was performed.
