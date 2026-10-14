# PHASE24P.3.9H — локальная основа EN/RU, этап A/4

Дата: 2026-10-11. Ветка `phase24-professional-saas-core`, HEAD `93f02eb`.
Статус: основа локализации реализована и проверена автоматическими тестами.
P3.9 PARTIAL; PUBLIC P4 BLOCKED; P5 не включён. Это только автономная
фиктивная выборка, без подключённой организации и поиска реальных закупок.

## Изменения

- `scripts/p39e_preview/page.html`: полностью английский текст до запуска JS;
  заметная тестовая маркировка; кнопки EN/RU с локализованными доступными
  именами и `aria-pressed`; статические подписи размечены стабильными ключами
  `data-i18n`, `data-i18n-aria`, `data-i18n-placeholder`.
- `scripts/p39e_preview/view.js`: один явный словарь из 132 ключей, каждый с
  именованными полями `en` и `ru`. Локализованы семь сценариев, шесть показателей,
  группы релевантности, SVG-подписи, состояния сроков, меню, подсказки, причины,
  поиск, сообщения, инспектор, навигация, заголовок страницы и доступные имена.
  `translate` никогда не заимствует другой язык; отсутствующий ключ/перевод
  вызывает исключение. Отсутствующие динамические доказательства очищают
  результаты и показывают ошибку на выбранном языке. Словарь проверяется
  `validateDictionary`, а тесты дополнительно проходят все необходимые ключи.
- Смена языка немедленно обновляет интерфейс и `html.lang`, сохраняет сценарий,
  поиск, фильтры и сортировку; выбранная группа и её прежние подробности очищаются.
  `localStorage` используется только для языка, через try/catch; при запрете
  хранения показывается локализованное объяснение, выбор работает в памяти страницы.
  Новый профиль начинает с EN; сохранённый RU восстанавливается при перезагрузке.
- `Intl.NumberFormat` и `Intl.DateTimeFormat` меняют только представление.
  Для точных моментов используется исходный `context.timezone`, для календарных
  дат — UTC без изменения самой даты. Группы, окна, даты и показатели не пересчитываются.
- `style.css`: компактный первый по значимости переключатель, активное состояние,
  адаптация длинных переводов и верхней панели на 360px; сохранён тёмный navy-интерфейс.
- Существующий builder не изменён: только `--build-fixture`, реальные проверенные
  worker-результаты, ограничение размера, атомарная запись и SHA256 CSP для CSS/JS.
- `tests/js/p39e_preview.test.cjs`: прежняя проверка всех функций сохранена;
  ожидания начального языка изменены на EN, тестовый DOM учитывает новые узлы,
  добавлена проверка полного словаря. `tests/test_p39e_local_preview.py`:
  сохранены прежние проверки и добавлены две проверки EN fallback/локального контракта.
  Ожидание «Часовой пояс:» обновлено до ключа «Часовой пояс»: двоеточие теперь
  добавляет renderer. Это эквивалентная проверка; CSP, данные и безопасность не ослаблены.
- Новый `tests/js/p39h_i18n.test.cjs` принимает путь к сгенерированному HTML.
  Проверяет именно собранный JS (с учётом нормализации CRLF штатным Python builder),
  оба языка × семь сценариев, статические и динамические узлы, доступные подписи,
  заголовки-подсказки, кольцо/треки/легенды, все drilldown, причины, ошибки/пустые
  состояния, поиск/фильтры/сортировку/reset, переключение с сохранением фильтров,
  первоначальный EN, сохранение RU, отказ хранилища, отсутствие перевода и неизменность
  данных. Анализируется интерфейс, а не язык сырого JSON в техническом раскрытии.
- Новый дополнительный `tests/js/p39h_browser.test.cjs`: настоящая file:// проверка
  в уже установленном Chromium через уже установленный Playwright; загрузок нет.
  При запуске требует `P39H_BROWSER`; внешние запросы блокируются, используются
  новый временный профиль, pipe и запрет DNS-разрешения. Не часть доказанного PASS:
  текущая среда не позволила завершить запуск браузера.

## Исключения из перевода

VALYQON AI, EN/RU на кнопках, CPV, обозначение сценарного набора H, номера фаз
P3.9/P4/P5, исходные пары идентификаторов закупок (например `ted / high`),
официальные коды стран и идентификаторы источников, IANA-имя исходного часового
пояса, числовые идентификаторы вымышленной организации/компании не переводятся.
Слова статусов фаз переводятся. Сырые политики, версии, ISO-моменты, контрольные
суммы, причины и полный JSON остаются только в первоначально свёрнутом техническом
раскрытии. В подробностях группы контрольная сумма отсылает к этому раскрытию.
`noscript` содержит английское предупреждение: оно видно только без JS, когда
переключение языка технически невозможно; в работающем RU-интерфейсе не отображается.
Нет заголовков реальных закупок, сумм, рыночной статистики, вероятности победы,
вымышленных трендов или оценки текущей доступности источников.

## Доказательства приёмки

Финальная сборка: `python scripts/p39e_local_h_preview.py --build-fixture`, exit 0.
Файл `.cache/phase24p3/p39e-preview/index.html`, 70 921 байт,
SHA256 `32d181b9502db761c4b1b385bda0a7af37b59329bde7cf841951420fc0ebdf49`.
Без флага: DISABLED, exit 0; SHA256 существующего файла не изменился.

Финальный настоящий Node (v24 runtime):

```powershell
node tests/js/p39h_i18n.test.cjs .cache/phase24p3/p39e-preview/index.html
node tests/js/p39e_preview.test.cjs .cache/phase24p3/p39e-preview/index.html
```

Оба PASS, exit 0. Normal KPI по-прежнему `[4,2,2,1,1,1]`.
Финальный guarded Python viewer run: **23 passed, exit 0, 6.79s**.
Внешние pytest plugins и cacheprovider выключены, basetemp направлен в новый
`.cache/phase24p3/p39h-tests-a3`. До установки audit guard заранее созданы 24
служебные пары stdlib socket.socketpair для Windows asyncio; во время тестов
socket.socketpair выдаёт только эти готовые пары. Audit guard запрещает socket/DNS
операции и открытие защищённых dotenv-файлов; неиспользованные пары закрываются.
Прежний worker запускается и каждый из семи результатов сверяется с trusted calculate.
Другие business suites в этом этапе не запускались и не менялись.

Честная история промежуточных запусков:
- Первая проверка точного JS выявила CRLF→LF нормализацию штатной сборки; сравнение
  исправлено на эквивалентные строки, CSP по-прежнему проверяет реальные байты.
- Новый DOM harness сначала выбирал второй option вместо первого пустого; исправлена
  модель нативного select. Проверки приложения и числовые ожидания не ослаблялись.
- Первый Python запуск устанавливал guard до служебных socketpair Windows asyncio:
  6 passed / 2 failed / 13 errors. Повторный корректный guarded запуск: 21 passed;
  после двух дополнительных проверок — 23 passed; финальный — 23 passed.
- Попытка реального браузера (Yandex Chromium, file://, headless) завершилась
  ошибкой `Target page, context or browser has been closed` при запуске, exit 1;
  журналы сообщают отказ записи registry и ошибки временного профиля/шифрования.
  Страница не принята браузером, screenshots не получены, реальная клавиатура,
  визуальные 1440/360px и file-origin CSP/storage acceptance остаются **PENDING**.
  Наличие DOM/CSS тестов не считается визуальной браузерной приёмкой.

## Передача следующему этапу

Не начинать с прежней смешанной страницы: текущий контракт — единый словарь и EN
по умолчанию. Все новые пользовательские строки должны иметь явные en/ru ключи;
обновлять этот инвентарь и Node coverage. Сохранить точные fixture/worker значения,
не превращать отсутствующее в ноль, не называть наблюдаемые источники доступными
сейчас и не трактовать высокую релевантность как вероятность победы.

Следующая проверка: открыть уже собранный файл без сервера в доступном локальном
браузере, проверить оба языка на desktop и 360px, Tab/Enter/Space, масштаб текста,
настоящие подсказки, file:// CSP и сохранение языка; выполнить дополнительные
этапы B/C/D только по новой инструкции. Этап A не означает выпуск P4/P5.

Работа ограничена preview assets, разрешёнными viewer tests и документацией;
app/, исходные fixture bytes и существующие business tests не редактировались.
Предыдущие tracked/untracked изменения сохранены; запрещённые временные каталоги
не открывались. Нет stage/commit/push/deploy, сервера, установок или сетевых API.

## Полный инвентарь стабильных ключей (132)
- `pageTitle`
- `brandLine`
- `nav`
- `navOverview`
- `navFit`
- `navDeadlines`
- `navRecords`
- `navEvidence`
- `lab`
- `command`
- `badge`
- `language`
- `chooseEn`
- `chooseRu`
- `scenario`
- `overview`
- `hero`
- `heroCopy`
- `scope`
- `six`
- `fitAxis`
- `fitHeading`
- `historical`
- `fitCopy`
- `table`
- `group`
- `fraction`
- `deadlineAxis`
- `deadlineHeading`
- `frozen`
- `deadlineCopy`
- `explorerAxis`
- `explorerHeading`
- `testData`
- `explorerCopy`
- `search`
- `searchHint`
- `historicalFit`
- `allFits`
- `deadlineEvidence`
- `order`
- `identityUp`
- `identityDown`
- `dateUp`
- `reset`
- `evidenceAxis`
- `evidenceHeading`
- `retry`
- `technical`
- `evidenceCopy`
- `footer`
- `scenario.normal`
- `scenario.empty`
- `scenario.unknown`
- `scenario.legacy`
- `scenario.foreign`
- `scenario.future`
- `scenario.filtered`
- `kpi.Discovered`
- `kpi.Matched`
- `kpi.High Fit`
- `kpi.Active Sources`
- `kpi.Countries`
- `kpi.Closing Soon`
- `fit.high`
- `fit.medium`
- `fit.low`
- `fit.unknown`
- `fit.unavailable`
- `noData`
- `whole`
- `known`
- `tenders`
- `sources`
- `countries`
- `units`
- `entities`
- `commitment`
- `coverage`
- `reason`
- `unspecified`
- `sourceDrill`
- `opened`
- `explorer`
- `of`
- `records`
- `empty`
- `open`
- `pair`
- `noGrouping`
- `noDate`
- `origin`
- `currentFit`
- `ringAria`
- `knownCaption`
- `allStates`
- `pinned`
- `snapshot`
- `timezone`
- `history`
- `testScope`
- `days`
- `selectEvidence`
- `noDates`
- `observed`
- `values`
- `error`
- `cleared`
- `storageDenied`
- `instant`
- `date_only`
- `unavailable`
- `future`
- `past`
- `missing`
- `invalid`
- `unknown`
- `in_window`
- `outside_window`
- `undated`
- `coverage.complete_observed_storage`
- `closing_soon`
- `reason.missing_or_malformed_score`
- `reason.missing_provenance`
- `reason.scope_mismatch`
- `reason.version_conflict`
- `reason.no_supported_instant_deadline_evidence`
- `reason.no_eligible_preview_scores`
- `technicalReference`
- `organization`
- `company`
- `reason.unavailable historical evidence`

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

## 2026-10-12 — D/4: независимый аудит; окончательная приёмка заблокирована

**OFFLINE TEST FIXTURE; P3.9 PARTIAL; PUBLIC P4 BLOCKED; FULL P4/P5 production NOT implemented.**
Контракт не объявлен окончательно принятым: штатный итоговый HTML отсутствует.
Просмотрены передача A/B/C, все три preview-актива, builder и preview-тесты.
Дизайн B/C сохранён; style.css и builder не изменены.

Подтверждённые исправления:
- view.js: при перерисовке списка восстанавливается фокус на той же точной паре идентификаторов; удалён неверный текст про источники/страны из инспектора отдельной записи. При частичном отказе отображения очищаются ссылки на контролы и выключается сброс группы.
- page.html/view.js: состояние подготовки данных получило отдельный EN/RU ключ и обработку `data-i18n-loading`.
- p39h_i18n.test.cjs: проверяются все латинские слова RU-интерфейса, с явными исключениями только для бренда/кодовых обозначений и исходных идентификаторов, стран, источников и timezone. Текстовые фрагменты harness разделены пробелом, чтобы inline-разметка не склеивала V и VALYQON в искусственное слово.
- p39h_interactions.test.cjs: регрессии фокуса, неверного пояснения и частичной ошибки; исправлены прежние `?` вместо `·`, из-за которых поиск модельной группы пропускал проверки. Теперь каждая кнопка обязана соответствовать группе, включая типизированную дату; проверяются её исходные идентификаторы и число записей. Бизнес-ожидания не ослаблены.
- NEW p39h_offline_contract.test.cjs: отдельный аудит исходных активов, ключей перевода/подготовки, textContent, dark/accessibility и отсутствия внешних ресурсов или сетевого кода. Это не проверка итогового HTML.

Измеренные результаты текущего D, без переноса PASS предыдущих этапов:

| Проверка | Результат |
|---|---|
| Штатный `scripts/p39e_local_h_preview.py --build-fixture` | 4 попытки: каждая exit 1, включая две после последнего изменения UI; BUILD FAILED |
| Без флага | exit 0, DISABLED; index.html не создан |
| Четыре обязательных Node-набора на `.cache/phase24p3/p39e-preview/index.html` | каждый exit 1 / ENOENT; повторены после последнего изменения UI |
| Guarded Python: viewer, offline_spike, process_isolation, analytics_api, analytics_service | exit 1; отсутствует pytest, **0 тестов собрано** |
| company.test.cjs | exit 0; аргумент `.cache/phase24p3/p39-dashboard.html` |
| phase24r.test.cjs | exit 0; аргумент `.cache/phase24p3/p4-dashboard.html` |
| discovery / discovery_full_ai / premium / shortlist_ui | 4 набора exit 0; HTML не читают, передан p4-dashboard.html |
| p39h_offline_contract.test.cjs | exit 0, исходные активы |
| compileall builder + viewer Python tests | exit 0; bytecode направлен в отдельный `.cache/phase24p3/p39h-d-compile` |
| git diff --check | exit 0; имеются обычные предупреждения LF/CRLF |

Доступные Python 3.12/3.12.14 не содержат pytest, pydantic и tzdata в полноценном общем runtime. Имеющиеся раздельные кэши зависимостей не удовлетворяют изолированному child worker. Установок, объединения/подмены runtime, изменений worker и обхода штатной сборки не было.

Дополнительная диагностика **только в памяти**, через trusted calculate и существующие кэши, под audit guard: p39h_i18n и p39h_interactions PASS (exit 0), EN/RU × 7 сценариев, immutable JSON и точные normal KPI `[4,2,2,1,1,1]`. Два прежних теста правильно FAIL (exit 1): p39e ожидает первым при сортировке срока ted/high, но без timezone-групп приходит ted/calendar; p39h_visual требует одновременно instant/date_only, однако buckets пусты. Ожидания сохранены. Это не доказательство worker-эквивалентности или корректных deadline tracks. Две диагностические render-строки одинаковы, 79352 байта, SHA256 `85c6e941c5c7c17f8e00be6d46710358a320603cb92a2ac397ff58ce61e8f3e7`; они не записаны в index.html и не заменяют две успешные штатные сборки. CSP-хеши на диагностических байтах прошли до отказа visual suite; парсинг окончательного статического HTML пока невозможен.

Честная история промежуточных отказов D: первая диагностическая передача Node через PowerShell потеряла кавычки (4 SyntaxError); исправлена запуском Node через stdin из Python. Усиленный языковой harness сначала обнаружил искусственно склеенный VVALYQON; исправлена модель текстовых фрагментов, разрешение произвольных английских слов не добавлено.

REAL BROWSER / 360px / MOBILE / KEYBOARD VISUAL ACCEPTANCE **PENDING**. Браузер в D не запускался: нет штатного file:// артефакта; безопасно показать окончательный результат невозможно. Скриншотов и утверждения «client-ready visual accepted» нет. Нужны desktop и 360px скриншоты обоих языков после успешной локальной сборки.

Следующий запуск должен начинаться с этой передачи: существующий полноценный runtime без установок → две штатные сборки с byte-identical SHA256 → четыре Node-набора на настоящем HTML и guarded Python → проверка CSP/сетевых запретов и offline file:// браузер. Замораживать контракт до этих PASS нельзя.

Команда открытия после успешной сборки (сейчас файл отсутствует):
`Invoke-Item $HOME\Documents\Codex\tender-ai-phase19\.cache\phase24p3\p39e-preview\index.html`

Финальный контроль сохранности D: SHA256 всех **366** исходных файлов `app/` и `tests/fixtures/` совпали с началом задания; количество файлов не изменилось. Ветка `phase24-professional-saas-core`, HEAD `93f02eb`. Существующие `.tmp-phase24*` не открывались и не изменялись; git stage/reset/clean/checkout/commit/push/deploy не выполнялись. После усиления обязательного соответствия каждой кнопки модельной группе диагностические i18n/interactions повторно завершились exit 0.

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
