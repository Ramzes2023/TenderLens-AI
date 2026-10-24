# Независимый функциональный аудит PR #264 — 24.10.2026

Кандидат: https://github.com/Ramzes2023/TenderLens-AI/pull/264, точный исходный SHA `a77a43fc3f57668719da26388fdc76e8efd0b35f`. После `git fetch origin refs/pull/264/head` создана ветка `audit/pr264-functional-20261024`. Основной worktree на `feat/ru-chechnya-eis-rss-20261022` не изменялся. Merge и production deployment не выполнялись.

## Что означает результат

PASS относится исключительно к явно указанной проверке. API/SQLite PASS не означает полного browser E2E или доступности upstream. BLOCKED означает отсутствие необходимого внешнего доступа/интеграции; NOT VERIFIED — недостаточность проверок для всей функции. Намеренно отсутствующая пользовательская возможность отмечена FAIL даже при корректной заглушке.

Использовались новые временные SQLite, отдельный Docker Compose project `valyqon-pr264-audit-20261024`, порты 19865/19866 и новый project-scoped volume. PostgreSQL 16 работал в отдельном контейнере `valyqon-pr264-audit-pg-20261024`, порт 25432, данные в tmpfs. Исходный preview 18865, существующие базы, production и личные учётные данные не использовались. Все аккаунты browser QA — новые `@example.test`. Синтетические закупки существовали только в disposable test databases/перехваченных ответах.

## Матрица 18 функций

| № / Функция | Результат | Точная проверка, API и БД | Найденные ограничения |
|---|---|---|---|
| 1. Регистрация, login, восстановление | PASS | Реальный Chromium: `/register` → POST `/api/v1/auth/register` 201 → verification → dashboard → forgot-password 202 → reset-password 200 → login 200 → refresh. Настоящий Docker API и SQLite. Дополнительно `test_auth*`, `test_password_reset*`: неверный/истёкший/повторный токен, политика пароля, аннулирование старых сессий, generic ответ неизвестному аккаунту, CSRF/rate limit. | Browser использует только disposable аккаунт. Доставка наружу не проверялась. |
| 2. Подтверждение email / Mailpit | PASS | Chromium открывает ссылки из настоящих писем через Mailpit `/api/v1/messages` и `/api/v1/message/{id}`. Оба письма — verification и reset — получены локально. `test_email_verification*`: одноразовость, resend, unverified login denial, fail closed без sender. | Это локальная SMTP-доставка, не Gmail/внешний провайдер. |
| 3. Настройки аккаунта / роли | NOT VERIFIED | `test_auth_api`, `test_organization_api`, `test_organizations`, `test_organization_workflows`: owner/admin/member/viewer, removed member, чужой tenant, последний owner. Settings посещён в Chromium. | Роли подтверждены API/БД; все действия настроек аккаунта через браузер не пройдены. |
| 4. Организации / профили компаний | PASS | `test_organization*`, `test_compan*`: создание, изменение, activation, pagination/history, приглашения, права, CSRF, company switch и scoped persistence. Docker Chromium дополнительно создаёт организацию/компанию через UI, активирует профиль и подтверждает сохранение выбора после refresh. | Полный браузерный CRUD, приглашения и все роли в Docker не пройдены. |
| 5. Overview / Operations Center | NOT VERIFIED | Проверены `premium.js`, `shell.js`, dashboard; навигация в настоящем Chromium, refresh, пустое состояние; `test_premium_ui` и JS wrappers. | Все значения карточек и localStorage pinned/recent при нескольких аккаунтах не проверены browser E2E. Иллюстративные публичные графики не являются реальной аналитикой. |
| 6. Discovery / настоящий поиск | BLOCKED | `test_international_discovery`, `test_customer_discovery_contract`, `test_organization_workflows`, JS discovery: запросы, partial failure, повтор, XSS, stale-response isolation. Отдельно реальный HKMA HTTP → Worker → ephemeral SQLite: 9 stored / 9 searched, replay deduped. | QA composition намеренно блокирует source details paid gate (403); реальный notice → авторизованный пользователь в UI не подтверждён. Нельзя обобщать HKMA на ЕИС и все источники. |
| 7. Рекомендации / Saved | FAIL | Saved: `test_shortlist*`, `test_saved_*`: scoped insert/list/delete, idempotent save, active company switch, persistence, no-store, роли. `shell.js` явно содержит `Personalized recommendations are not available yet`. | Saved работает в проверенных путях; персональные рекомендации не реализованы. Это не дефект, исправляемый подменой данных. |
| 8. Tender Planner / Kanban | PASS | GET/PATCH `.../shortlist/{id}/workflow`, `test_shortlist_workflow`: revision, 409, persisted stage, повтор без нового revision, viewer denial. Настоящий Chromium с явно перехваченным OFFLINE_FIXTURE API рисует реальные компоненты Planner. | Browser workflow PATCH на реальном Docker API не выполнен; official submission не реализуется внутренним stage. |
| 9. Календарь / ICS | PASS | Новый `test_planner_browser`: настоящий Chromium скачивает ICS, проверяет два VEVENT, DATE-only DTSTART, преобразование `22:30 +03:00` → `19:30Z`, UID и длину строк ≤75 octets; клик второй записи передаёт точный saved ID + organization/company. Существующие date/timezone contracts сохранены. | Исправлена ссылка календаря, ранее открывавшая только раздел Saved. Google/Outlook sync отсутствует; все сторонние calendar clients не проверены. |
| 10. Назначение / согласование | PASS | Настоящие authenticated API → SQLite: assign, member request, решение другого admin, no self-approval, viewer/outsider denial, cross-origin 403, stale revision 409. Новый одновременный ThreadPool-тест: один победитель, один conflict, revision=1 и ровно одно audit event. Дополнительный Chromium-тест настоящих team controls → ASGI API → SQLite: owner assigns/requests, self-approval disabled, другой admin approves, viewer повторно открывает persisted approval; revision=3, audit events=3. | OFFLINE_FIXTURE закупка. В браузерном component test организация/компания заданы в state; весь dashboard multi-user E2E не пройден. Внешняя подпись/подача заявки не проверяется. |
| 11. Статусы / аудит | PASS | `test_shortlist_workflow`, `test_authenticated_team_source_roundtrip`: запись этапа и повторный GET, optimistic conflict, rollback, scoped audit; confidential note не копируется в audit. | Внутренняя история не является официальным статусом закупки. |
| 12. История извещений ЕИС | NOT VERIFIED | GET `.../source-history`, `test_saved_source_history` и authenticated roundtrip: две сохранённые OFFLINE_FIXTURE observations, допустимые изменённые поля, tenant denial, пустое/неподдерживаемое состояние. | Настоящие последовательные изменения ЕИС и изменения PDF не проверены; `has_document_evidence=false`. |
| 13. Аналитика заказчиков | NOT VERIFIED | `renderBuyers()` читает customer только из tenant-scoped Saved, считает exact names в пределах 300 записей; UI contracts запрещают выдуманные winner/competitor. | Настоящий browser chart с реальным сохранённым набором не проверен. Рыночная аналитика/победители/конкуренты не реализованы. |
| 14. Monitoring / Source Health | PASS | `test_monitoring`, `test_source_health_api_behavior`: данные сохранённой discovery telemetry, empty=`not_checked`, sanitization ошибок, изоляция компании. JS и UI contracts. | PASS для API/DB/JS, не для текущей доступности всех источников или постоянного production worker. |
| 15. AI analysis | BLOCKED | `test_ai_gateway`, `test_ai_failover`, `test_ai_cache`: обработка ошибок, retry/fallback, секреты, cache isolation, failed responses; UI посещён. | Credentials в QA отсутствуют, внешний LLM отключён. Ответ реального провайдера не получен. |
| 16. Telegram / email notifications | BLOCKED | Mailpit auth emails доставлены. Monitoring/notification fixture contracts проходят. `shell.js`: notifications inbox ещё не реализован. | Нет controlled Telegram token/recipient и проверки source→worker→оповещение. Auth email не доказывает tender alert delivery. |
| 17. Billing / подписки / paid access | FAIL | `billing_routes.py` и `billing.js`: authenticated usage counts из БД, owner/admin only; `test_billing_pilot`, `test_public_paid_gate`: 401/403, personal organization rejection, no fabricated invoices. API честно возвращает `billing_status=not_enabled`, `subscription=null`, `upgrade_available=false`. | Merchant ledger, checkout, signed webhook и verified paid entitlements отсутствуют. Gate закрывает детали всем, а не подтверждает оплату. Реальных платежей не было. |
| 18. Навигация / responsive / переводы | NOT VERIFIED | Docker Chromium: overview, recommended, saved, planner, monitoring, source-health, AI, notifications, billing, settings; refresh; viewport 390×844, menu open и Escape close; нет pageerror. Node wrappers: i18n, geography, UI/navigation contracts. | Все маршруты на всех viewport и полнота RU-перевода через браузер не проверены. |

## Исправления

1. `planner.js`: календарная запись теперь отправляет такой же tenant-scoped `valyqon-open-saved`, как Kanban. Общий helper исключает расхождение поведения. Дизайн не изменён.
2. Новые Chromium regressions для auth API/SQLite и календаря/ICS. Auth browser test использует захват писем, отдельно от настоящей Mailpit-приёмки.
3. Новый тест одновременных назначений с проверкой persisted winner и единственности audit event.
4. `.gitattributes`: pinned TED JSON и официальный SDK XML сохраняют точные committed bytes на Windows; checksums не менялись. Это исправляет ложные падения при CRLF checkout.
5. Тест аналитики пишет telemetry в `tmp_path`; oversized certificate pytest ID ограничен коротким названием при сохранении всех 65537 bytes входа. Устранены ошибки чистого checkout и лимита Windows environment.
6. `scripts/qa_pr264_local.py`: воспроизводимая локальная browser/Mailpit приёмка на выделенных портах, без tender seeding, production credentials и внешних рассылок. Генерируемые QA данные исключены из Git.

## Доказательства и числа

- Functional Python/API/DB suite: **631 PASS**, **10 subtests PASS** (`audit-pr264-functional.xml`).
- Итоговая целевая регрессия с Chromium, auth, Planner/ICS, командами и историей: **20 PASS** (`audit-pr264-final.xml`). Числа перекрываются с functional suite, суммировать их нельзя.
- Дополнительный настоящий Chromium team/API/DB сценарий: **1 PASS** (`audit-pr264-team-browser.xml`).
- После добавления проверки UTC в ICS повтор Planner + team Chromium: **2 PASS** (`audit-pr264-browser-final.xml`).
- Node запускается через штатные Python wrappers, передающие требуемые HTML arguments: **19 PASS** (`audit-pr264-javascript.xml`). Прямой `node --test tests/js/*.test.cjs` не является корректным runner для всех этих скриптов.
- Изначальный полный Windows прогон: **3898 PASS / 15 FAIL / 18 ERROR / 7 SKIP / 1 XFAIL**, **518 subtests PASS**. Не объявлен зелёным. Ранний прогон с недоступным системным TEMP имел дополнительно setup errors и не используется как финальное доказательство.
- Повтор проблемных Windows файлов: **272 PASS / 1 FAIL**; единственное оставшееся на тот момент падение было SDK XML CRLF, после чего применена защита точных bytes. Контрольный повтор CPV/eForms/TED: **53 PASS**. Официальные reference inputs восстановлены по CI URLs с исходными SHA-256; checksum assertions не изменялись.
- Read-only HTTP smoke: **16 PASS**, включая assets, anonymous 401/403 и Mailpit 200.
- Docker build: PASS, image `valyqon-pr264-audit:20261024`.
- Реальный Docker Chromium + Mailpit: PASS; `page_errors=[]`, синтетических закупок вставлено **0**. После расширенного повторного сценария SQLite: `auth_accounts=2`, `auth_sessions=2`, `organizations=3`, `company_workspaces=1`, `saved_opportunities=0`, `source_opportunities=0`, migrations=20. QA Compose containers/volume и PostgreSQL tmpfs container удалены после проверки.
- PostgreSQL 16: **6 групп PASS**: миграции/checksums/replay 1–20; threads/spawned processes; quota windows; tenant isolation/roles/inactive accounts; cancellation/restart/retry; durable jobs/fencing. Отдельный `pg_dump -Fc` → новый DB → `pg_restore --exit-on-error`: PASS. Сравнены counts исходной/восстановленной БД: migrations 20/20, accounts 14/14, memberships 13/13, jobs 2/2, synchronous_usage 41/41, quota_admissions 2/2.
- Дополнительно неизменённые data-backed assertions из `test_tender_team_decisions.py` запущены на PostgreSQL 16 вместо SQLite, каждый тест в отдельной новой БД: **3 PASS** — concurrent assignment/единственный audit event, assign/request/approve/revision/audit, scope/two-person reviewer. Второй tmpfs PostgreSQL container после проверки удалён.
- На исходном SHA #264 через GitHub API найдены **6 successful workflow runs**, в том числе [CI](https://github.com/Ramzes2023/TenderLens-AI/actions/runs/40088722869) и [PostgreSQL 16](https://github.com/Ramzes2023/TenderLens-AI/actions/runs/40088722889). Это не статус нового audit commit.

### Полный Linux CI: FAIL, не скрывается

Полная команда в disposable Docker: `python -m pytest tests -q --durations=15 --ignore=tests/test_p39e_local_preview.py --junitxml=artifacts/audit-pr264-linux-final.xml`.

Итог: **3827 PASS / 1 FAIL / 87 SKIP / 1 XFAIL**, **518 subtests PASS**, 24:24. Skip включают Windows-only сценарии и отсутствующие в Linux image optional Node/Playwright; Node и Chromium отдельно фактически запускались на Windows, а Windows-only файлы перепроверены отдельно. Нельзя складывать эти totals с другими наборами.

Падение: `test_analytics_admission.py::test_calculation_barrier_final_scope_and_exception_cleanup[error-503]`, строка 160: `AssertionError: calculation worker not released`, `release.wait(10)` вернул False. Это барьер внутри теста, а не полученный пользователем неправильный approval или утечка tenant data. Отдельный повтор **всего файла в Linux: 13 PASS**. Возможное объяснение — задержка работы потока/event loop под нагрузкой Windows bind mount; это предположение, корневая причина нестабильности не доказана. Timeout и assertions не ослаблялись. Полный набор **не считается зелёным**; стабильный полный green-run остаётся release blocker.

Дополнительный полный повтор из snapshot на файловой системе того же контейнера не завершился: окончание основного `docker run --rm` остановило контейнер вместе с его дополнительным exec. Этот частичный прогон не включён в PASS totals.

GitHub API на commit `2a98d85` вернул ноль PR-triggered workflow runs: workflows основного CI фильтруются по base `main`, тогда как audit PR направлен в feature branch. Новый exact-head remote CI — **NOT VERIFIED**; успех workflows исходного #264 не переносится на audit commits.

### Источники: четыре независимых уровня

| Уровень | Подтверждение |
|---|---|
| OFFLINE_FIXTURE | PASS: scoped API, SQLite persistence, два EIS observations, mocks/Chromium API interception; это не live закупки. |
| REAL_HTTP | PASS только для настоящего публичного HKMA в этой сессии; не для всех источников. |
| WORKER_PERSISTENCE | PASS HKMA: job succeeded, stored=9, searched=9, replay_deduped=true; temporary DB удалена harness. |
| USER_DELIVERY | NOT VERIFIED для закупок/Telegram/email alerts. Mailpit auth/reset отдельно PASS и не заменяет этот уровень. |

## Незакрытые production blockers

Merchant-backed entitlement и подписки; рекомендации; notifications inbox; controlled Telegram/SMTP tender delivery; source→worker→DB→authorized-user acceptance; live EIS revisions и PDF evidence; внешний LLM; полноценный dashboard multi-user browser E2E и все переводы/viewport; стабильный полный Linux green-run и remote CI на audit HEAD. Публичный paid gate по-прежнему блокирует detail workflows. До закрытия этих пунктов merge/deploy не рекомендованы, PR остаётся Draft.

Сырые локальные журналы и JUnit находятся в `artifacts/audit-pr264-*` и не публикуются: они могут содержать тестовые токены и детали тестового окружения. Общие результаты и обезличенное доказательство приведены в этом документе.

## Git и review

Исправления: commit `2a98d85` (`fix(qa): open exact planner deadline and verify isolated auth workflows`). Ветка опубликована. [Draft PR #280](https://github.com/Ramzes2023/TenderLens-AI/pull/280) направлен в `feat/real-guest-search-gated-20261023`, чтобы изменения аудита можно было рассмотреть отдельно от всей истории #264. Отчёт и дополнительная browser regression добавляются следующим коммитом. Git author задан только для команд commit; глобальные настройки пользователя не менялись.
