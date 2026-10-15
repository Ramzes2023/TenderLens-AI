# P39E local H fixture preview — 2026-10-11

Implemented standalone, opt-in static HTML viewer. P39E LOCAL DEMO implemented;
P3.9 remains PARTIAL, full P4 public rollout BLOCKED, P5 not enabled.
No authenticated analytics integration or production acceptance is implied.

## Run and open on Windows

From repository root:

```powershell
python scripts/p39e_local_h_preview.py
python scripts/p39e_local_h_preview.py --build-fixture
Invoke-Item .cache/phase24p3/p39e-preview/index.html
```

First command prints DISABLED, imports no analytics worker and creates nothing;
it also leaves an existing preview unchanged. Second runs seven real bounded
Windows FixtureSpike children and prints PREVIEW_HTML only after atomic success.
Open the resulting file directly: no HTTP server, hosting, network assets or
listening application socket. Python asyncio initializes its stdlib internal
wakeup socketpair before the parent audit guard; it is not a preview service.
After that initialization parent guard refuses socket/DNS operations and dotenv
opens, before importing/calculating H. Child retains P39D guards and Job limits.
This audit hook is not an OS security sandbox. P39D unsuspended startup and
whole-request resource limitations remain unchanged.

Verified output path:
`C:\Users\ramze\Documents\Codex\tender-ai-phase19\.cache\phase24p3\p39e-preview\index.html`.

## Contract and visible behavior

Only fixed normal, empty, unknown, legacy, foreign, future and filtered scenarios.
Pinned FIXTURE_SHA256 and existing fixture_payload / FixtureSpike validate input
and output. No scoring implementation or fixture hash was changed. Child output
is exactly compared to the existing trusted calculate reference and bounded by
24 KiB per result. Full HTML is bounded by 256 KiB. Result allowlist contains no
tender titles/text/URLs, tokens, cookies, secrets or actual customer history.

Six cards: Discovered, Matched, High Fit, Active Sources, Countries, Closing Soon.
Fit chart uses historical fit-band numerator / known-score denominator; unknown
identities use the entire selected population denominator and a separate label.
Typed deadline chart uses existing closing-window buckets, preserving instant
versus date_only and frozen server timezone/as_of. Each bar is measured against
the selected population U, not a fabricated market total. Closing Soon KPI is
instant-only; date-only is separate. Deadline states, including unknown/missing,
are also shown in the accessible table. No browser date arithmetic.

Clickable cards/bars disclose exact identities from the selected result. Scenario
selection clears all prior details, charts, table and provenance; retry renders
the committed static case again (does not run a new search). Contract failure
clears all data. Filtered is explicitly a precomputed backend ted/zero filter,
not arbitrary client analytics. Arbitrary search is disabled. No industry or
winning-probability/current-profile-fit chart is offered.

All DOM values use textContent; JSON escapes script terminators, ampersands,
U+2028/U+2029. Hash-pinned inline CSS/JS CSP denies other assets/connections.
Geometry rejects nonfinite, negative, fractional and unsafe integer counts and
clamps valid widths to 0..100. Navy responsive layout includes 360px rules,
keyboard focus, table/caption, status live region and textual chart alternatives.
No live dashboard, routes, production settings, DB, scoring or source edits.

## Verification and limitations

Baseline guarded runner: 103 passed, exit 0, 15.81s (offline_spike + service).
Final new Python suite: 20 passed, exit 0, 3.76s. Tests cover seven real child
parities, exact normal/empty/unknown/filtered semantics, typed deadlines, default
off, safe JSON/provenance, checksum/output limit/mismatch failures, parent audit
denials and atomic success/failure cleanup. Existing assertions are unchanged.
New Node suite passed: geometry, all cases/cards, real rendering handlers in a
dependency-free DOM harness, drilldown, stale clearing, retry and error recovery.
Six existing JS suites each exit 0: company, discovery, discovery_full_ai,
phase24r, premium, shortlist_ui. Node DOM harness is not browser acceptance.

Relevant regression command:
`python .cache/phase24p3/run_tests.py p39e-regression tests/test_p39e_local_preview.py tests/test_analytics_offline_spike.py tests/test_analytics_process_isolation.py tests/test_analytics_admission.py tests/test_analytics_runtime_gate.py tests/test_analytics_api.py tests/test_analytics_compatibility.py tests/test_analytics_service.py tests/test_company_history_paging.py tests/test_analytics_fit.py tests/test_analytics_dates.py`.
Observed 386 passed, 0 skipped/deselected, exit 0, 121.03s, one existing
Starlette/httpx warning. This includes the initial 14 preview tests; after final
parent guard/test additions the preview suite independently passed 20 tests.
These counts overlap and must not be summed. Final compileall for entrypoint
and new tests passed; git diff --check exit 0 (existing CRLF warnings only).
Final rendered CSS/JS hashes matched CSP declarations; new Node suite repeated
against the final generated file passed, exit 0.

Initial parent guard blocked asyncio's internal wakeup pair during experimental
builds; those failed closed and removed the old success file. Guard installation
was moved after event-loop initialization, before H imports; explicit final build
then succeeded. No assertion or worker guard was weakened.

Two successful full builds were byte-identical: HTML 42056 bytes, SHA256
239e78e951652561b79550a61e26e24d13fb94e913febacecac2fd2365b8add6.
Default-off command also verified the existing output hash stayed unchanged.
No real browser launched: visual/CSP/file-origin acceptance remains PENDING;
an offline-enforced browser launch was not established in this session.
Next practical step: open the generated HTML locally and inspect normal/unknown/
filtered at desktop and 360px, including keyboard drilldown. This does not require
or authorize a production rollout.

Prior tracked/untracked work and .tmp-phase24* preserved; those folders were not
opened or cleaned. Existing docs were appended, not rewritten. No staging,
commit, push, deployment, migration, package installation, Docker, live network,
customer DB or credential access. PRODUCTION_TOUCHED=False.


## P24P.3.9F — local fixture visual polish (2026-10-11)

Scoped edits only: scripts/p39e_preview/page.html, style.css, view.js, matching
viewer tests and these local progress documents. Production dashboard, premium
assets, core analytics, fixture commitment and worker logic were not edited.
Local fixture preview improved; P3.9 PARTIAL / full production P4 still BLOCKED /
no P5. Original P39E evidence above is preserved.

Russian user labels, restrained navy header with light evidence panels, balanced
card heights, neutral priority accents for High Fit and closing deadlines, chart
legend, exact denominators, explicit historical preliminary relevance (not win
probability), observed successful sources (not live health), typed calendar/date
versus instant deadlines, and clearer evidence table. Exact identities remain
in drilldowns/table; raw metric evidence/reasons are retained in expandable
technical provenance. Unknown/null remains distinct from zero. No client scoring,
new figures, network resources or production routes. Native buttons retain click,
focus and Enter/Space behavior; keyboard activation itself still needs a browser.
Fit values now also reject unsafe numeric contract values before rendering.

Baseline guarded Python: 123 passed, exit 0, 20.34s (P39E + offline spike + service).
Baseline viewer JS on original generated HTML: exit 0. Initial all-JS command
omitted mandatory HTML arguments for company/phase24r/viewer and returned exit 1
for those invocations; corrected calls all passed, not product failures.
Final local Python: 21 passed, exit 0, 7.28s, including Russian presentation and
rendered CSP hash checks. Final JS viewer and all six existing suites: each exit 0
(company, discovery, discovery_full_ai, phase24r, premium, shortlist_ui).
Company/phase24r use existing .cache/phase24p3/p39d-dashboard.html; viewer uses
actual rebuilt .cache/phase24p3/p39e-preview/index.html. Tests verify seven cases,
normal [4,2,2,1,1,1], unknown/zero, filtered and typed deadlines, drilldown/stale
clearing/retry/error recovery, numeric failures, accessible labels and responsive
layout rules. DOM harness is not real browser acceptance. compileall exit 0;
git diff --check exit 0 with existing CRLF warnings only.

Two final explicit --build-fixture builds identical: 46453 bytes, SHA256
805345b466eab63b50802cd77b727316cd343ca26e6e0f0af71b4a3f55878d29.
Default-off remains DISABLED and preserves the output hash. CSP script/style
hashes match rendered content; no external resources/connections are added.

Browser acceptance: user-supplied prior desktop descriptions establish only the
original P39E desktop render. No Edge/Chrome executable found at standard Program
Files Edge/Chrome or per-user Chrome paths. No browser launched, installed,
networked or attached; no additional screenshots captured. Updated desktop,
360px visual, real keyboard, file-origin CSP and accessibility acceptance remain
PENDING. Next single practical step: open the rebuilt file and provide a 360px
screenshot (ideally after opening a card with Enter/Space).

```powershell
Invoke-Item $HOME\Documents\Codex	ender-ai-phase19\.cache\phase24p3\p39e-preview\index.html
```

All prior tracked/untracked work and .tmp-phase24* preserved. No stage/commit/
push/deploy, server, installs, customer database or secret reads.

Final bounded regression: 198 passed, exit 0, 180.35s, one existing
Starlette/httpx deprecation warning. Command:
`python .cache/phase24p3/run_tests.py p39f-final tests/test_p39e_local_preview.py tests/test_analytics_offline_spike.py tests/test_analytics_process_isolation.py tests/test_analytics_api.py tests/test_analytics_service.py`.
This run started with the original 20 local tests; the final 21-test local suite
ran separately after the presentation/CSP test addition. Counts overlap and are
not additive. No failing test assertions were changed or weakened.
## P24P.3.9G — тёмный procurement command center (2026-10-11)

Локальный viewer перестроен: почти чёрный navy canvas #07101f, фиксированная
боковая навигация на desktop, компактная прокручиваемая навигация на mobile,
верхняя панель сценария и OFFLINE TEST FIXTURE — НЕ ДАННЫЕ КЛИЕНТА,
шесть компактных KPI с акцентами High Fit / Closing Soon, SVG-кольцо известных
исторических оценок, отдельная unknown-группа, типизированные треки сроков,
explorer записей и evidence inspector. Большой основной raw-evidence table убран.
Текстовая таблица fit остаётся доступной в disclosure; технические hashes,
политики и population commitment — в технической панели.

Работают anchor-навигация с активным состоянием, поиск пары ID, фильтр historical
fit, фильтр точных deadline state memberships, четыре порядка сортировки,
сброс, нажатия KPI / fit legend / deadline bucket / state / record, повторное
отображение и переключение всех семи сценариев с полной очисткой старого выбора.
Native button/select/input/anchor сохраняют клавиатурную семантику; aria-live
сообщает состояние и размер subset. KPI при explorer-фильтрации неизменны.
Источники и страны не превращаются в notice identities. Текущий fit показан
отдельно от historical. Неизвестное/null не превращается в ноль.

Кольцо normal: high 2/3, medium 0/3, low 1/3; unknown отдельно 1/4 U.
Geometry ограничена finite safe counts и 0..100. Membership и denominators
проверяются до отображения. Сроки — только переданные worker даты окна,
с оригинальными строками дат, фиксированным as_of и Europe/Rome; instant и
calendar date_only раздельны, missing/future доступны отдельно. Нет browser
Date arithmetic, имитации 30-дневного ряда или пересчёта бизнес-показателей.
CSV/clipboard не добавлены: для минимальных инструментов достаточно безопасных
локальных controls, без дополнительного download/clipboard permission surface.
Названия закупок, суммы, CPV, рыночная доступность и win probability недоступны.

Baseline: guarded runner p39g-baseline, local Python 21 passed (9.15s), exit 0;
оригинальный viewer JS на прежнем index — exit 0. Первоначальный прямой pytest
дал 18 passed / 3 setup errors из-за доступа к системному temp, а plain node
не был в PATH; повторено существующим workspace runner и локальным node.exe.
Промежуточный новый JS выявил floating-point equality и неверную автоселекцию
псевдо-DOM harness; harness исправлен под реальную семантику select, geometry
проверяется с точностью 1e-12. Python выявил UTF-8 BOM в template после
PowerShell Set-Content: BOM удалён из исходников, assertion не ослаблен.
Также прежнее требование «Легенда:» заменено новым disclosure заголовком.

Финальная двойная guarded --build-fixture сборка byte-identical: 54894 bytes,
SHA256 bca0a213987a1122def9f6d75fccbbee2d008cd1160b6aecb54b6755032e0d07.
Семь сценариев, normal KPI [4,2,2,1,1,1]. Worker/fixture/scoring не изменены.
CSP hashes пересчитываются штатным builder; network/resources не добавлены.
Финальный viewer JS PASS, exit 0: geometry, все cases, search/filters/sorts,
reset/drilldown, country/source isolation, stale clearing/error recovery,
nav active state, text-only XSS rendering, dark/mobile contracts.
Шесть существующих JS suites company/discovery/discovery_full_ai/phase24r/
premium/shortlist_ui — каждый exit 0. company и phase24r получают существующий
.cache/phase24p3/p39d-dashboard.html. compileall exit 0; git diff --check exit 0,
только существующие CRLF warnings. Python regression результат добавлен ниже.

Browser status: standard local Chrome/Edge executable paths отсутствуют.
Браузер не запускался; desktop/360px screenshots, реальная клавиатура и file://
CSP visual acceptance PENDING. Псевдо-DOM и CSS contracts — не screenshot acceptance.

Generated index:
C:\Users\ramze\Documents\Codex\tender-ai-phase19\.cache\phase24p3\p39e-preview\index.html
Открыть без сервера:
`Invoke-Item 'C:\Users\ramze\Documents\Codex\tender-ai-phase19\.cache\phase24p3\p39e-preview\index.html'`

Изменения только preview assets/tests и append документации. Другие tracked /
untracked изменения и .tmp-phase24* сохранены; без stage/commit/push/deploy.
P3.9 PARTIAL; публичный production P4 BLOCKED; P5 НЕ ВКЛЮЧЁН.
Промежуточная полная узкая регрессия p39g-final: 197 passed, 2 failed,
exit 1, 191.41s. Оба failure локального viewer: BOM в template и старое
утверждение о заголовке «Легенда:». Они исправлены до финальной сборки;
core regression failures не было. Отдельный окончательный guarded local run
p39g-local-verified: 21 passed, exit 0, 5.93s. Default без флага остаётся
DISABLED, exit 0, итоговый SHA256 не меняется.
Финальная guarded регрессия p39g-verified завершена: 199 passed, exit 0,
188.69s, одно существующее Starlette/httpx deprecation warning. Проверены
tests/test_p39e_local_preview.py, tests/test_analytics_offline_spike.py,
tests/test_analytics_process_isolation.py, tests/test_analytics_api.py,
tests/test_analytics_service.py. Counts с отдельным local run перекрываются,
не суммируются. Финальный JS дополнительно проверяет DOM-переключение всех
семи сценариев, сброс search/sort и соответствие explorer каждой U; exit 0.

### P24P.3.9H / A — полная локальная основа EN/RU, 2026-10-11

Единый словарь 132 явных en/ru ключей, английская страница до JS, заметный EN/RU
переключатель, локализация всего статического/динамического интерфейса и ARIA,
Intl-представление без пересчёта данных, сохранение языка с обработкой отказа
localStorage. Фильтры/сценарий сохраняются, старый drilldown очищается.
Normal KPI [4,2,2,1,1,1], все семь trusted scenarios без изменения worker/fixtures.
Финальный Node i18n и прежний viewer suite PASS / exit 0; guarded Python viewer:
23 passed / exit 0 / 6.79s. Сборка только --build-fixture: 70 921 bytes,
SHA256 32d181b9502db761c4b1b385bda0a7af37b59329bde7cf841951420fc0ebdf49.
Без флага DISABLED, файл не меняется. Реальный headless browser test предпринят,
но браузер завершился при запуске в ограниченной среде (exit 1); screenshots и
браузерная/клавиатурная приёмка PENDING. Все промежуточные ошибки и корректный
guarded test setup описаны в docs/PHASE24P39H_LOCAL_I18N.md.
Только offline preview; production не менялся. P3.9 PARTIAL; PUBLIC P4 BLOCKED;
P5 не включён. Следующие этапы и настоящая desktop/360px приёмка ещё впереди.

## Этап B/4 — 2026-10-12: визуальные инструменты реализованы, приёмка заблокирована

P3.9 PARTIAL; PUBLIC P4 BLOCKED; P5 не включён. Только автономная вымышленная выборка.

Изменения:
- scripts/p39e_preview/page.html: общий адаптивный контейнер explorer/inspector.
- scripts/p39e_preview/style.css: тёмная композиция navy, тонкие разделители, глубина панелей,
  шесть акцентированных KPI с пояснениями, двухколоночное рабочее место на desktop,
  отдельные стили instant/date_only, узлы SVG, hover/focus, mobile/tablet breakpoints,
  отключение переходов при prefers-reduced-motion. Светлый режим не добавлен.
- scripts/p39e_preview/view.js: десять новых ключей общего EN/RU словаря; контекст каждого KPI;
  внешний контур known / U отдельно от внутреннего распределения known;
  декоративные узлы подтверждённых дат без выдуманной временной шкалы;
  переведённое объяснение расстояний и клавиатурные подсказки в title.
  Математика model/arcs, идентификаторы, фильтры, сценарии и сохранение языка не изменены.
- tests/js/p39h_visual.test.cjs: новый тест пути к штатному HTML, CSP-хешей реальных байтов,
  dark/responsive/motion, EN/RU, знаменателей, идентификаторов и обязательного наличия
  обеих групп сроков в normal; включает i18n suite.
- tests/js/p39h_i18n.test.cjs: обход SVG на конечные неотрицательные координаты,
  безопасный фиксированный path, переведённые новые подписи/title и native buttons.
- tests/test_p39e_local_preview.py: дополнительный контракт композиции и графических инструментов.
- Builder и существующий tests/js/p39e_preview.test.cjs не изменялись; app/ и fixtures не редактировались.

Фактические запуски и ограничения:
1. Найденный Python 3.12: штатный --build-fixture exit 1 (сначала отсутствует pydantic).
   Повтор с существующими каталогами кэша через PYTHONPATH: exit 1, child_exit.
   Изолированный worker получает один каталог зависимости и не видит раздельные зависимости кэша.
   Установок, сети и изменений worker не было.
2. Для диагностики render(calculate(...)) выполнялся исключительно в памяти.
   Это НЕ успешная worker-сборка и НЕ восстановленный index.html.
   В этом runtime отсутствует база часовых поясов; normal deadline buckets пусты.
3. Настоящий Node v24.21.0: i18n suite прошёл на диагностическом HTML в памяти.
   Первоначальная visual-проверка прошла, но после добавления обязательного покрытия обоих
   типов сроков финальный visual suite правильно падает из-за пустых buckets.
   Старый p39e suite падает на ожидании deadline sort ted/high: без дат первым идёт ted/calendar.
   Ожидание сохранено, тест не ослаблялся.
4. Шесть функций Python artifact/security/layout tests выполнены напрямую из AST тестового
   файла на диагностическом calculate-результате: PASS (HTML/security, CSP/labels/layout,
   EN fallback, i18n contract, stage B contract, отсутствие server/app mutation).
   Это НЕ полный pytest suite: pytest отсутствует в доступном runtime.
5. Два диагностических render побайтово одинаковы: 77059 байт,
   SHA256 37d5959b42cd7820cf013ae50af88992463d58ce4fa2d2744c6c5f6ab4683e68.
   Две последовательные штатные сборки НЕ подтверждены.
6. Без флага main([]): DISABLED, exit 0.
7. Браузер не запускался, screenshots и визуальная приёмка 360/tablet/desktop отсутствуют.
   Адаптивность проверена только контрактами CSS/DOM.
8. Штатный builder удаляет предыдущий успешный index.html до попытки сборки.
   После неуспешных запусков финальный .cache/phase24p3/p39e-preview/index.html отсутствует.
   Нельзя подменять его диагностическим HTML; нужен успешный --build-fixture в полном runtime.

Для следующего этапа нужен уже установленный полноценный runtime с pydantic и его зависимостями
в общем доверенном каталоге и базой IANA timezone, плюс pytest. Затем штатная сборка дважды,
три Node suites по фактическому index.html, полный Python viewer suite и реальная offline
браузерная приёмка. Этап B не объявлен принятым.

## 2026-10-12 — Stage C/4: local interaction instruments
P3.9 PARTIAL; PUBLIC P4 BLOCKED; P5 DISABLED.

Implemented only preview assets:
- view.js: row inspection preserves search, filters, order and current group instead of reducing the list to one row. Record selection uses aria-pressed and a distinct visual state. Group buttons expose aria-controls and synchronized aria-pressed. Clear selected group restores the population while retaining user filters. Reset clears group/record selection. Scenario and language rendering clear stale selection; scenario resets all inputs. Visible counts now explicitly label the frozen indicator population.
- page.html: genuine EN/RU Clear selected group and Back to records controls. The former is disabled when no group exists; the latter scrolls to explorer and returns keyboard focus to its first result.
- style.css: selected evidence states, disabled-state appearance, narrow toolbar bounds; existing dark hierarchy, 360px rules and reduced-motion retained.
- tests/js/p39h_interactions.test.cjs: accepts generated HTML, verifies EN/RU × seven scenarios, exact group identities/counts, row/search preservation, group clearing, focus return, anchors, errors, restoration, fixture immutability and native button semantics.
- tests/js/p39e_preview.test.cjs: DOM harness registers the three new nodes; existing assertions unchanged. No worker, builder, app or fixture bytes edited.

Actual verification:
1. Standard --build-fixture attempted twice: BUILD FAILED, no successful index.html. First runtime lacks installed dependencies; cached dependencies via PYTHONPATH still do not satisfy isolated child worker. No dependency installation or worker bypass.
2. Four final Node suites PASS on diagnostic HTML rendered in memory from trusted calculate for all seven cases using existing cached dependencies: interactions, i18n, visual, existing viewer. Base64 transport preserved UTF-8 and CSP bytes. Diagnostic HTML was never saved as index.html and is NOT worker/build acceptance. Normal KPI [4,2,2,1,1,1]; both typed deadline tracks verified by unchanged visual suite.
3. Seven existing Python contract functions executed directly from AST under offline audit guard: semantics, safe HTML, no app mutation/server, CSP/layout, EN fallback, i18n contract, Stage B layout PASS. This is NOT the full pytest suite or worker equivalence.
4. Full viewer pytest attempted: No module named pytest, exit 1. Default launcher remains DISABLED, exit 0.
5. Browser/screenshot acceptance NOT performed. Real Enter/Space activation and 360px rendered layout remain unverified; native buttons/focus/CSS contracts are covered only by DOM tests.
6. Intermediate test failures: shell interpolation introduced invalid JS; corrected before final PASS. Diagnostic stdout text transport changed UTF-8/newlines; corrected via base64 without weakening assertions.

CSV deliberately omitted: no validated file:// download/browser runtime. No P5 widgets, live source monitor, invented analytics or network calls. Remaining acceptance requires a complete existing trusted Python runtime (dependencies together for isolated worker, pytest, timezone database), standard --build-fixture, all suites on its real HTML and offline browser review. Stage C is implemented but NOT accepted as a final built/browser artifact.

## 2026-10-12 — D/4: исправления QA, приёмка не завершена

Исправлены потеря клавиатурного фокуса при выборе записи, неверное пояснение источников/стран в её инспекторе, очистка контролов при частичной ошибке и локализация состояния подготовки. Усилены EN/RU и точные проверки модельных групп; добавлен отдельный offline source contract. Дизайн, worker, app и fixture-данные не менялись.

Шесть legacy JS suites и source contract: exit 0. compileall и diff --check: exit 0. Четыре штатные попытки сборки: exit 1; default DISABLED: exit 0. Четыре обязательных Node suites на финальном index.html: exit 1 / ENOENT. Guarded Python для пяти обязательных файлов: exit 1, pytest отсутствует, 0 собрано. Диагностические i18n/interactions в памяти: exit 0; viewer/visual: exit 1 из-за отсутствующей timezone-группировки. Подробные результаты и ограничения — в `docs/PHASE24P39H_LOCAL_I18N.md`, раздел D/4.

Итоговый index.html отсутствует; CSP/детерминизм штатной сборки и реальная визуальная/клавиатурная приёмка desktop/360px не подтверждены. Нужны desktop и 360px скриншоты EN/RU после успешной штатной сборки. OFFLINE TEST FIXTURE; P3.9 PARTIAL; PUBLIC P4 BLOCKED; FULL P4/P5 production NOT implemented.

## 2026-10-12 — P4A/4: локальные проверяемые проекции
Реализованы analyticsEvidence в view.js и tests/js/p39j_evidence.test.cjs (путь к штатному generated HTML обязателен). Event activity по UTC, источники по выбранному U, typed worker deadlines, known/unknown fit, покрытие и provenance. Country/CPV identity mappings отсутствуют: явно unavailable, без поддельных нулей. Существующий DOM H и builder сохранены.
Диагностика текущего source в доступном Node REPL на семи случаях существующего HTML: PASS для проекций, неизменности, словаря и небезопасных чисел. Команды Node/Python отсутствуют в PATH; обязательный новый generated-HTML suite, rebuild, Python, protected hash gates и browser/360px остаются launcher pending. Никакой успешный artifact не генерировался обходным способом.
Подробности: docs/PHASE24P4_P5_LOCAL_ANALYTICS.md. OFFLINE LOCAL DEMO; P3.9 PARTIAL; production P4 BLOCKED; production P5 не реализован.

## 2026-10-12 — P4B/4: локальные dark charts, приёмка host pending
Реализованы EN/RU панели источников с exact U drilldown и SVG scale, календарные ячейки
с отдельными instant/date_only, явные unavailable состояния тренда/географии/CPV.
Сохранены шесть KPI, fit donut, фильтры, сценарии и инспектор. Только preview assets;
builder/app/fixtures не менялись. Добавлен tests/js/p39j_charts.test.cjs (generated HTML
обязателен); preservation harness p39e зарегистрировал новый DOM node.
Source DOM диагностика 7 × 2 и H i18n/interactions PASS; offline source contract и
JS syntax PASS. Новый generated suite FAIL на stale bundle; штатная host-пересборка,
полные Node/Python/hash gates и реальная desktop/360px EN/RU визуальная приёмка pending.
Node/Python CLI отсутствуют в PATH; использован имеющийся Node REPL. Артефакт не подменялся,
браузер не инспектировался. Полная передача: docs/PHASE24P4_P5_LOCAL_ANALYTICS.md.
OFFLINE LOCAL DEMO; P3.9 PARTIAL; production P4 BLOCKED; full production P5 не реализован.

## 2026-10-12 — P5A/4: локальный прототип виджетов
Только OFFLINE pinned synthetic demo; P3.9 PARTIAL; production P4 BLOCKED;
full production P5 НЕ реализован. Exact U records sorted by historical band/identity,
coverage known/unknown / U, stored dated search events, source observations, рабочие
filter chips/reset и identity detail panel с focus return. Country/CPV/scores/финансы
явно unavailable, KPI [4,2,2,1,1,1] неизменны. +17 EN/RU ключей, всего 175.
Новый tests/js/p39j_widgets.test.cjs требует generated HTML и проверяет реальные DOM
handlers 7 × 2, identities/counts, язык/фильтры, isolation и keyboard structure/focus.
Source DOM diagnostics P5A/H i18n/interactions PASS; syntax PASS через Node REPL.
Generated suite на прежнем HTML FAIL: stale bundle. CLI Node/Python нет в PATH.
Builder не запускался; artifact не подменён. Host rebuild/Node/Python/hash gates и
реальная offline browser desktop/360px/Enter/Space приёмка pending.
Подробности и честные ограничения: docs/PHASE24P4_P5_LOCAL_ANALYTICS.md, P5A/4.
