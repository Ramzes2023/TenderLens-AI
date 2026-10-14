# P4A/4 — проверяемые локальные проекции

2026-10-12. Только OFFLINE LOCAL DEMO, семь закреплённых синтетических сценариев.
P3.9 PARTIAL; authenticated/public production P4 BLOCKED; production Smart Widgets P5 не реализованы.

План выполненной реализации: аудит H allowlist и service → чистые проверяемые
проекции в view.js → инспекция в существующем техническом раскрытии → отдельный
generated-HTML тест p39j_evidence.test.cjs. Builder, app и fixture не изменялись.
Редизайн и новые зависимости отсутствуют; прежний DOM H сохранён.

## Инвентарь доказательств

| Проекция | Доказательство и единица | Ограничение |
| --- | --- | --- |
| Историческая активность | selected_events: ID, timestamp, snapshot hash; число уникальных выбранных событий по UTC-дню / все выбранные события | Не число новых закупок, не тренд; пропущенные дни не достраиваются. В empty может существовать событие с пустым U. |
| Источники | Первая часть точной пары в U; уникальные записи каждого источника / выбранное U | Не source events, не KPI успешных источников, не uptime |
| Страны | unavailable, numerator null, groups null | Countries KPI содержит distinct codes, но allowlist не содержит country→identity mapping. Нельзя считать распределение или число неизвестных стран. |
| CPV / отрасли | unavailable, numerator null, groups null | Классификации отдельных записей отсутствуют в allowlist; policies не являются классификациями |
| Сроки | Готовые worker buckets и states; точные пары / U | Тип instant/date_only сохранён. Day — готовый локальный bucket worker, не исходный timestamp. Date-only не превращается в instant. Состояния вне окна и unknown отдельны. |
| Релевантность | Готовые high/medium/low группы / known; unknown / U | Историческая предварительная релевантность, не вероятность победы; числовых raw scores нет |
| Покрытие | Known и unknown historical fit / U | Не полнота рынка. Страны, CPV и финансовые знаменатели не выводятся |

Каждая группа содержит exact identities, numerator, denominator, unit; каждый
panel — status, basis, missing semantics. Общая provenance: population_id, scope,
as_of, timezone, coverage, sample_window. Проекции копируют входные массивы;
между сценариями нет кэша. Проверяются безопасные целые, membership, дубликаты,
partition states, реальные календарные дни, типы и manifest событий. Неподдерживаемые
страны/отрасли явно объяснены на EN/RU рядом с существующими наблюдениями.
Неизвестное не заменяется нулём. Финансы, supplier wins и source health не создаются.

## Проверки и передача launcher

Новый обязательный тест:
`node tests/js/p39j_evidence.test.cjs .cache/phase24p3/p39e-preview/index.html`.
Принимает настоящий generated HTML; отвергает старый JS bundle, проверяет CSP,
семь случаев, normal U и KPI [4,2,2,1,1,1], точные source/event/deadline/fit
группы, неизменность, unavailable и вредоносные числа/manifest/membership.
Также вызывает существующий EN/RU DOM suite. Старые suites не изменялись.

В sandbox Node/Python команды отсутствуют в PATH. Через уже доступный Node REPL
проверены текущий source JS, словарь, проекции всех семи случаев на данных из
существующего HTML, неизменность входа и отклонение NaN/Infinity/negative/unsafe
denominator: диагностический PASS. Это НЕ PASS нового generated-HTML suite и
НЕ независимое доказательство worker parity. git diff --check для view.js: exit 0.
Существующий HTML не пересобирался и не переписывался; fake artifact отсутствует.

Launcher должен выполнить разрешённый builder --build-fixture в своём известном
рабочем host venv, новый и все H suites, Python viewer tests, protected hash checks.
Реальный браузер и 360px не инспектировались, визуальная приёмка P4A не заявлена.
Network/install/deploy/git stage/commit/push не выполнялись.


## 2026-10-12 — P4B/4: тёмные локальные диаграммы

OFFLINE LOCAL DEMO на семи закреплённых синтетических сценариях. P3.9 PARTIAL;
production authenticated/public P4 BLOCKED; full production Smart Widgets P5 не реализованы.

План реализации: проверить P4A allowlist → добавить панели без новых доказательств →
связать точные группы с инспектором → добавить отдельные тесты и передать host gates.
Реализовано в существующих page.html/style.css/view.js. Navy-панели, мягкое свечение,
cyan/teal полосы наблюдаемых источников, amber-разделение календарных дат, компактные
календарные ячейки и прежнее кольцо known fit с отдельным unknown; шесть KPI сохранены.
Источник использует numerator / U, шкалу 300 SVG units и native button: выбор обновляет
точную группу explorer/inspector, aria-pressed и сброс. Даты используют только worker
buckets; instant/date_only никогда не объединяются. Состояния вне окна/unknown отдельны.
Тренд закупок недоступен: event IDs и timestamp не дают доказанной связи с tender
identities, поэтому события не переименованы в новые закупки. География и CPV явно
«Недостаточно доказательств» / “Insufficient evidence”, без карт, долей, нулей и
интерактивных имитаций. Наблюдаемые источники не означают live health. Технические
доказательства остаются в свёрнутом раскрытии. Все новые тексты/ARIA EN/RU; безопасный
textContent, конечная SVG-геометрия, внешних ресурсов нет. CSS содержит narrow/mobile
правила и reduced-motion; реальное отсутствие overflow ещё требует браузерной проверки.

Новый обязательный suite:
node tests/js/p39j_charts.test.cjs .cache/phase24p3/p39e-preview/index.html
Проверяет настоящий текущий bundle и CSP обоих assets, семь сценариев × EN/RU,
нефункциональные unavailable панели, exact source/deadline groups, scale geometry,
zero/null/unknown, обе типизированные дорожки normal, выбор/ARIA/focus-модель, redraw,
responsive hooks, безопасные длинные строки; вызывает прежние H i18n/interactions/visual.
В p39e_preview.test.cjs только зарегистрирован новый chart-sources DOM node.
P4A evidence suite и H suites не ослаблены. Builder/app/fixtures не редактировались.

Фактические проверки sandbox:
- Node/Python отсутствуют в PATH; доступен установленный Node REPL.
- Синтаксис view.js и p39j_charts.test.cjs: PASS через vm.Script.
- Source DOM diagnostics на текущем page.html/view.js и данных из прежнего штатного
  HTML: PASS для новых проверок всех 14 комбинаций и для прежних H i18n/interactions.
  Межконтекстные массивы диагностически сравнивались по точному JSON; файл suite
  сохраняет strict deepEqual. Это НЕ generated-HTML acceptance и НЕ worker parity.
- H offline source contract: PASS через Node REPL; словарь EN/RU валиден.
- Новый обязательный generated-HTML suite на существующем index.html: FAIL на
  “Test the final builder output, never a stale bundle”. Нужна штатная host-пересборка.
- git diff --check для изменённых assets и preservation test: exit 0.
- Первые диагностические попытки выявили пропущенную скобку теста (исправлена), затем
  отсутствующий vm в harness, повторное объявление Element и cross-realm comparison;
  исправлена только диагностическая среда, продуктовые ожидания не ослаблены.

Ни builder, ни generated HTML не запускались/перезаписывались обходным способом.
Host launcher должен выполнить текущий --build-fixture в известном рабочем Python venv,
новый p39j_charts и p39j_evidence, все сохранённые H/viewer suites, реальные Python tests,
protected hash gates и offline desktop/360px QA EN/RU. Браузер не инспектировался,
скриншотов нет; визуальная и настоящая клавиатурная приёмка P4B НЕ заявлены.
Сеть/install/deploy/stage/commit/push отсутствуют. Исходные посторонние изменения
рабочей копии сохранены; утверждение о clean git tree не делается.

## 2026-10-12 — P5A/4: локальные умные виджеты, host acceptance pending

OFFLINE LOCAL DEMO: только семь PINNED synthetic scenarios. P3.9 PARTIAL;
authenticated/public production P4 BLOCKED; full production Smart Widgets P5 НЕ реализованы.

План: аудит allowlist → компактные полезные виджеты → реальные связи с explorer и
inspector → отдельный DOM suite → передача независимых host gates.
Реализованы приоритетные exact identity records: все записи U, сортировка по готовой
historical band (high/medium/low/unknown), затем identity. Это не ранжирование числовых
scores и не прогноз победы. Выбор сохраняет фильтры, открывает отдельную панель записи
и возвращает фокус к её кнопке, либо к панели, если запись скрыта фильтром.
Панель показывает исходные historical/current band, reason, worker states/day buckets,
as_of/timezone и source identity code. Числовые scores, country, CPV, суммы и названия
явно unavailable. Закрытие очищает выбор и возвращает фокус к записи, если она видима.

Coverage: known и unknown historical fit / exact U, включая честное 0/0 для empty.
Обе группы фильтруют explorer и inspector точными identity sets. Country/CPV completeness
не рассчитывается. Recent historical search activity: сохранённые selected_events,
по убыванию timestamp, tie по event ID; отображение в исходном context timezone.
Это события поиска, не новые закупки, не tender trend, не последовательность действий
клиента. Нет достроенных дней или связи event→tender. При отсутствии событий —
локализованное insufficient evidence. Source observations: exact identity source / U;
native buttons выбирают точные группы, без online/uptime/health индикаторов.

Filter chips реально очищают search/fit/deadline или выбранную группу. Search chip
содержит локализованное имя фильтра; запрос остаётся в input без копирования произвольного
латинского текста в RU chrome. Reset очищает всё. Scenario/retry/error удаляют старые
виджеты/детали/chips. Language сохраняет search/fit/deadline/order; старый выбор
очищается по существующему H контракту. KPI не пересчитываются. Guidance не содержит
фиктивных ссылок. Dark navy, cyan/teal, responsive single-column widgets; внешних assets нет.
Builder/app/fixtures не изменялись.

Новый обязательный тест:
node tests/js/p39j_widgets.test.cjs .cache/phase24p3/p39e-preview/index.html
Принимает штатный GENERATED HTML, отвергает stale JS/CSS, проверяет CSP, все 7 × EN/RU,
stable sorted IDs, coverage denominators/exact membership, event IDs/order, источники,
country/CPV unavailable, click/chip/reset, native button/ARIA и focus model, scenario/error
isolation, язык/фильтры, immutable fixture/KPI [4,2,2,1,1,1]; вызывает сохранённые H suites.
Preservation p39e harness только регистрирует новые DOM nodes. Словарь: 175 ключей
(158 ранее + 17 P5A), каждый с EN/RU.

Фактические проверки:
- Node/Python CLI отсутствуют в PATH. Использован существующий Node REPL; install/network нет.
- vm.Script: текущий view.js и новый suite синтаксически валидны.
- Диагностика текущих assets в памяти на данных прежнего штатного HTML: P5A DOM 7 × 2,
  H i18n и H interactions PASS. Cross-realm arrays диагностически сравнивались через
  точный JSON; сохранённый suite использует strict deepEqual. HTML не записывался.
  Это НЕ generated-HTML acceptance, НЕ worker parity и НЕ browser acceptance.
- Новый suite на существующем generated HTML: FAIL — “Test the final builder output,
  never a stale bundle”. Старый artifact не подменён; builder в sandbox не запускался.
- Первая H i18n диагностика выявила English query token в RU chip; исправлено отображение
  search chip без ослабления H assertions; повторная диагностика PASS.
- Python pytest, независимые protected hashes, реальные Enter/Space, desktop/360px
  и screenshots здесь НЕ выполнены. CSS/DOM contracts не заменяют визуальную приёмку.

Launcher: штатный текущий --build-fixture в известном рабочем host venv; p39j_widgets,
p39j_charts, p39j_evidence, сохранённые H/viewer suites, Python viewer, protected hash gates,
offline browser QA EN/RU desktop/360px. Без флага builder остаётся DISABLED.
Production P4/P5 не объявлены завершёнными. Deploy/stage/commit/push отсутствуют.

Финальный git diff --check: exit 0 (предупреждения LF/CRLF, ошибок whitespace нет).
