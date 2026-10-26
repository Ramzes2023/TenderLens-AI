# ARMEPS: проверка 19 октября 2026

Рабочая ветка `fix/cis-am-real-dns-transient-20261018`, исходный HEAD
`69a068b603fe88d197d75c9ee240db8e522f13d4`. Commit/push/merge не выполнялись.
Production, настоящие пользовательские БД, Самара и B2B не менялись.

## История и границы установленной причины

Просмотрены история адаптера от `a58b6ff`/`91d0598`/`60d60a6`, цепочка DNS-исправлений
`e2d059f` → `f355488` → `479b43c` → `e0a5db5` → текущий HEAD,
PR [157](https://github.com/Ramzes2023/TenderLens-AI/pull/157),
объединённый [184](https://github.com/Ramzes2023/TenderLens-AI/pull/184)
(`f94c946`, `7ec4e7e`, merge `6b223fe`) и состояние/лог PR 224.

Текущая ветка старше исправления #184 и всё ещё угадывала `start/2` при нехватке
записей на первой странице. Исправление восстановлено локально: дополнительный
запрос допускается только по точной официальной ссылке из предыдущего ответа.
`fetch(1)` может остановиться раньше `fetch(20)`, поэтому его успех сам по себе
не доказывает успешный Worker. Регрессия воспроизводит один настоящий контракт
данных в offline fixture: первая страница с одной записью и наблюдаемой ссылкой,
вторая — 503; три попытки Worker завершаются ошибкой, отдельный fetch(1) успешен,
частичный результат не принимается. Fixture не выдаётся за live-закупку.

В [падении #224](https://github.com/Ramzes2023/TenderLens-AI/actions/runs/39288784605)
проверялся merge SHA `b0177c9210208346032417378ee7b2231b03f504`:
ARMEPS — три попытки, `permanent_failure`, позднейший `source_probe_rows=1`;
TJ — success. По API прочитан именно файл этого SHA: исправление #184 там уже
есть, а DNS-классификатора из #157 нет. Следовательно, нельзя объявлять
неподтверждённую пагинацию причиной именно этого позднего инцидента. Старый лог
не сохраняет причину отказа Worker: DNS, TLS, HTTP, parser и storage между собой
не различимы. Число 20 само по себе также не доказывает ошибку лимита запросов.

В [проверке HEAD #157](https://github.com/Ramzes2023/TenderLens-AI/actions/runs/39079022651)
ARMEPS исчерпал три попытки с `handler_error`; отдельный probe вернул
`SourceTransportError: Temporary source transport failure.` TJ прошёл.
Это подтверждает временный транспортный сбой, но не конкретный DNS/HTTP статус.

Новая диагностика фиксирует безопасную цепочку типов исключений **того же
Worker**, известный статический код SourceError, HTTP status (если доступен),
точный DNS marker и номер попытки. Не выводит сообщения транспорта, HTML,
заголовки, cookie, адреса DNS или credentials. Не делает ошибку успешной.

## Действующий официальный источник и сеть

- Проверен HTTPS HTML `https://eauction.armeps.am/en/public/tender/` через
  настоящий `BoundedClient`: 200, 22 148 bytes, 30 записей, семь колонок,
  один detail anchor в колонке 6, точная наблюдаемая ссылка на страницу 2.
- Только после обнаружения ссылки запрошена страница 2: 200, 30 записей.
  Неподтверждённые маршруты, API, карточки и JS endpoints не запрашивались.
  При текущих 30 строках и fetch(1), и fetch(20) завершаются после первой
  страницы: различие лимита сейчас не приводит к дополнительному HTTP-запросу.
  Само по себе более позднее успешное fetch(1) совместимо с перемежающимся
  транспортным отказом предыдущего Worker; это объяснение, а не доказанная
  причина исторического #224 без отсутствующей цепочки исключений.
- HTML содержит POST-форму на тот же listing path. Публичный документированный
  JSON API не установлен; неизвестные API не угадывались и в ingestion не добавлены.
- Локальный DNS: A `91.221.229.75`, AAAA-ответа нет (получен SOA).
  В ранней отдельной попытке TCP соединение с 443 установлено, TLS handshake
  завершился timeout; исходная DOM-диагностика также получила ConnectTimeout.
  Последующие защищённые HTTPS/Worker запросы прошли. Постоянная недоступность
  официального сервера или блокировка GitHub по IP этим не доказана.
  Отдельный `curl.exe -I` не прошёл локальный Schannel AcquireCredentialsHandle
  (`SEC_E_NO_CREDENTIALS`); это отказ TLS-стека данной команды, не HTTP-отказ ARMEPS.
- Исходная DOM-диагностика создавала клиент до установки bounded policy, поэтому
  выбирала LiveClient. Теперь клиент создаётся внутри policy, как у Worker.
- Проверки всех DNS-адресов и фактического peer, SSL/SNI, запрет proxy/redirect,
  точный HTTPS hostname, request budget 2 для AM / 1 для TJ сохранены.
  Адаптер ограничивает HTML 1 MiB; общий worker transport дополнительно имеет
  свой существующий предел 25 MiB до парсинга. Shared transport не менялся.
- DNS retry теперь просматривает всю цепочку до конца: найденный DNS marker
  не может скрыть более глубокий SSL error или явный nonretryable policy error.
  PublicIPError остаётся permanent.

## Настоящий Worker → SQLite → поиск

Оба live запуска использовали публичный HTTPS, canonical catalog, настоящие
миграции, durable jobs, lease fencing, OpportunityRepository и snapshot_catalog.
Каталоги включены только в памяти отдельных проверок, source defaults disabled.
БД создавались в новых временных каталогах и закрывались/удалялись проверкой.
Отдельно исправлено незакрытое SQL-соединение acceptance: `with conn` у SQLite
не закрывает дескриптор; на Windows cleanup скрывал уже успешный Worker ошибкой
WinError 32. Используется `contextlib.closing`.

| Проверка | ARMEPS | Таджикистан |
|---|---:|---:|
| Сохранено первым Worker | 20 | 20 |
| Поисков по полному исходному номеру и названию | 40 | 40 |
| Повторный Worker: вставлено / обновлено | 0 / 20 | 0 / 20 |
| Попыток первого / повторного Worker | 1 / 1 | 1 / 1 |
| Повтор enqueue того же окна | тот же job | тот же job |

Примеры реально сохранённых и найденных ARMEPS:

- ID 48191, `ՄԶՀ-ԷԱՃԾՁԲ-2026/06`, `design and furnishing works`.
- ID 48192, `ԻՀԱԿ-ԷԱՃԱՊՁԲ-27/07`, закупка питьевой воды National Center for Infectious Diseases.
- ID 48193, `ՍՄՆՀԴ-ԷԱՃ-ԱՊՁԲ-27/2`, закупка лекарств для ՍՅՈՒՆԻՔԻ ՄԱՐԶԱՅԻՆ ՆՅԱՐԴԱՀՈԳԵԲՈՒԺԱԿԱՆ ԴԻՍՊԱՆՍԵՐ.

Для TJ среди реально сохранённых — 443385, 443387, 443392 (кондиционеры).
Полные исходные названия, номера и публичные ссылки трёх примеров каждого
источника сохранены в JSON, а не восстановлены из offline fixtures:

- `artifacts/armeps-worker-live-20261019.json`
- `artifacts/tajikistan-worker-live-20261019.json`
- `artifacts/armeps-live-dom-20261019.json`
- `artifacts/armeps-official-shape-20261019.jsonl`

Live-поиск доказывает путь через snapshot repository. HTTP auth/tenant route
проверяется отдельно offline integration, не объявляется live tenant acceptance.

## Проверки и оставшиеся действия

Используется изолированный `artifacts/armeps-repair-venv` (локально игнорируется),
Python 3.12.14, HTTPX 0.28.1 / HTTPCore 1.0.9. Для тестов установлены
`PYTHONDONTWRITEBYTECODE=1`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, TEMP/TMP внутри
workspace; pytest запускается с `-B -p no:cacheprovider` и отдельным `--basetemp`.
Live-запуски дополнительно используют `PYTHON_DOTENV_DISABLED=1`. В финальном
расширенном pytest этот флаг снят: существующий jobs unit намеренно проверяет
чтение своего временного `settings.env`. До снятия флага проверено, что `.env`
в корне workspace отсутствует; содержимое настоящих env-файлов не выводилось.

Первый профильный запуск: 34 passed, один отказ из-за отсутствия FastAPI.
Первый расширенный: 600 passed, 2 skipped, 3 failed из-за отсутствующих
PyMuPDF/GigaChat (зависимости API/RAG импортов). Эти отказы не скрывались.
Промежуточные профильные регрессии: 55 passed, 1 deselected (API test ожидал
установки зависимостей). После установки зависимостей расширенный запуск дал
680 passed, 2 skipped, один отказ jobs dotenv unit из-за общего
`PYTHON_DOTENV_DISABLED=1`, а не из-за ingestion. Проверка не отключалась:
полный набор повторно запущен с корректной средой. Финальный результат ниже.

**Финальный расширенный запуск: 681 passed, 2 skipped, exit 0, 69.27 s.**
Два существующих skip — `Raw deflate has no checksum` в test_source_http.py;
новые skip/xfail/ослабления assertions не добавлялись. Есть одно предупреждение
Starlette о будущем переходе testclient с HTTPX на HTTPX2, без отказов тестов.

Проверены полностью:
`test_cis_am_real_dns_retry.py`, `test_cis_am_tj_main_integration.py`,
`test_connector_workers.py`, `test_jobs.py`, `test_source_http.py`,
`test_source_http_transport.py`, `test_source_http_cleanup.py`,
`test_source_catalog.py`, `test_source_framework.py`, `test_international_sources.py`.
Включены API/session/CSRF/tenant integration AM/TJ, durable retry, fencing,
повторы/upsert, original-number/title search, DNS/SSL/unsafe-peer regressions,
пагинация и отсутствие частичного успеха. Вывод —
`artifacts/armeps-full-tests-20261019.txt`.

`git diff --check` и AST parsing пяти изменённых Python-файлов проходят.
Проверка diff по `app/sources/b2b_center.py` и `*samara*` пуста.

Локальные финальные live AM/TJ успешны; ранний ConnectTimeout и прежние красные
GitHub runs не объявляются зелёными задним числом. Для полного зелёного CI нужно
отдельно опубликовать проверенный diff обычным разрешённым процессом, выполнить
все обязательные проверки на окончательном SHA и получить зелёный hosted AM/TJ.
При повторном отказе новая диагностика покажет фактическую цепочку Worker.
Сетевой обход, SSL bypass, skip/continue-on-error или изменение независимых
источников не предлагаются. Старый #224 также имеет отдельный красный
`Russian real-data user scoring acceptance`; он не исправлялся в ARMEPS scope.

Повторные финальные live-запуски после всех изменений также прошли: AM и TJ —
по 20 строк, 40 поисков, повтор 0 insert / 20 update, по одной попытке каждого
Worker. JSON evidence обновлены этими запусками.

## Окончательное рабочее дерево

HEAD: `69a068b603fe88d197d75c9ee240db8e522f13d4`.
Ветка: `fix/cis-am-real-dns-transient-20261018`.
Ни один commit не создан. Изолированные venv и временные каталоги тестов имеют
локальные самоисключающие `.gitignore`; рабочие данные не удалялись.

```text
 M app/sources/am_armeps.py
 M scripts/ci_cis_am_live_dom_diagnostic.py
 M scripts/ci_cis_am_tj_live_acceptance.py
 M tests/test_cis_am_real_dns_retry.py
 M tests/test_cis_am_tj_main_integration.py
?? artifacts/armeps-full-tests-20261019.txt
?? artifacts/armeps-live-dom-20261019.json
?? artifacts/armeps-official-shape-20261019.jsonl
?? artifacts/armeps-targeted-tests-20261019.txt
?? artifacts/armeps-worker-live-20261019.json
?? artifacts/tajikistan-worker-live-20261019.json
?? docs/cis/ARMEPS_REPAIR_20261019.md
```
