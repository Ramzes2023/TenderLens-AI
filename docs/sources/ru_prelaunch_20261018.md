# Russian source prelaunch audit — 2026-10-18

Observed from the local Windows 3.12 environment with production transport, HTTPS verification and DNS/public-IP checks intact. All SQL databases were disposable; no production source activation, deployment or customer message was performed. A local pass is not proof of GitHub runner or production network availability.

| Source | Genuine records persisted and found | Proof scope |
| --- | ---: | --- |
| GPB ETP | 3 | Separate details, leased Worker, SQLite, replay, authenticated tenant isolation |
| TEK-Torg | 5 | Separate details, leased Worker, SQLite, replay |
| Fabrikant 44 | 3 | Separate details, leased Worker, SQLite, replay, authenticated tenant isolation |
| Roseltorg | 3 | Separate details, leased Worker, SQLite, replay, authenticated tenant isolation |
| Dagestan public list | 2 | Official GET/token/POST, leased Worker, SQLite, ID/title queries, replay; **details unavailable** |
| B2B-Center | 10 | Leased Worker, SQLite, replay; independent detail not established |
| MikroTon | 10 | Leased Worker, SQLite, replay |
| Leningrad Oblast | 3 | Separate details, leased Worker, SQLite, replay |
| NMCK | 2 | Separate details, leased Worker, SQLite, replay |
| Stantorgi | 2 | Separate details, leased Worker, SQLite, replay |
| South Ural | 10 | Separate details, leased Worker, SQLite, replay |
| Kavkaz.RF | 2 | Separate details, leased Worker, SQLite, replay; independence from EIS not proved |
| EIS RSS 44 / 223 | 10 / 10 | Windows trust, real feed -> SQLite -> keyword; this diagnostic does not prove a leased Worker or individual detail |

## Repairs

- GPB accepts both numeric-only and numeric-plus-slug canonical URLs. The SQL acceptance assertion accepts both forms too.
- Fabrikant uses the live `https://44.fabrikant.ru/44/catalog/procedure/published` registry. The proposed `soap4.fabrikant.ru` route returned HTTP 404 in this environment; search-engine cached content is not live ingestion evidence. Original 19-digit EIS identity is retained; existing original-publication classifier recognizes overlap rather than counting a new independent notice.
- Roseltorg adapter from pending #101 is registered opt-in with bounded same-host list/detail requests. Added authenticated scoring/tenant gate.
- Dagestan #210 was merged into main during this audit. Runtime now supports limit=1 and a consistent empty page (`items=[]`, `totalRows=0`). Contradictory counts and malformed payloads still fail. Live acceptance still demands two genuine rows.
- TEK-Torg and EIS HTML legacy acceptance scripts now claim real durable jobs instead of passing fabricated contexts to the handler.
- Explicit operator queue includes the five recovered sources, individually opt-in. Defaults remain false. Fabrikant/Roseltorg scoring also requires actual catalog enablement.
- Certificate adversarial test uses bounded parameter IDs so Windows does not exceed its environment-variable limit; all hostile payloads are still checked.

## Reproduce

Use Python 3.12 and `requirements-dev.txt`. Run `python -m pytest -q tests -k 'ru_ or tektorg or fabrikant or roseltorg'`.
For the principal live proofs use `python -m scripts.ci_ru_gpb_public_worker`, `scripts.ci_ru_tektorg_real_worker`, `scripts.ci_ru_fabrikant44_real_worker`, `scripts.ci_ru_roseltorg_real_worker`, and `scripts.ci_ru_dagestan_public_list_sql`. The first command form applies to every module. Run the corresponding `*_authenticated` scripts for GPB, Fabrikant and Roseltorg.

## Remaining launch conditions

Exact-head CI must complete; earlier GitHub-hosted GPB/TEK-Torg/Fabrikant/Roseltorg runs failed transport despite these local successes. Do not turn a failed live check green by using fixtures or weakening transport. Confirm the actual deployment network separately. Sources require explicit flags and worker execution; code registration alone does not activate them. Real customer notification delivery has not been exercised. Regional research PRs without original-list/detail acceptance remain research, not working integrations. EIS HTML independent detail proof and Dagestan details remain incomplete.

Offline validation on the initial integration revision: **569 passed**, with one dependency deprecation warning. Additional numeric transport-observation regressions: **4 passed**. The diagnostic does not claim ingestion and cannot replace the strict live gate.
