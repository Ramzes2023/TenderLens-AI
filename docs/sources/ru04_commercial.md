# RU-04: российские коммерческие источники

База: `d6ee20fbed1c51e932136e4c9097b13eb0ecfcd1`.

## Результат и доказательства

| Цель | Статус | Доказательство и границы |
| --- | --- | --- |
| B2B-Center | PARTIAL | Реализован bounded HTML-адаптер агрегированной публичной выдачи `/search/`. Сохранённый образец содержит 10 `ListItem` с `Organization`, `Demand`, функцией `Buy`, идентификаторами `/search/number/.../`, названиями и оригинальными ссылками. Это смешанная агрегированная выдача, а не подтверждённый полный каталог собственных коммерческих процедур B2B-Center. |
| Roseltorg | BLOCKED | В предоставленной папке отсутствует `roseltorg.html`. Нет доказательств структуры, стабильных идентификаторов и detail URL. Причина отсутствия образца неизвестна: нельзя утверждать CAPTCHA, shell или конкретный HTTP-статус. Адаптер, endpoint и конфигурация активации не создавались. |

Исходная папка: `C:\Users\ramze\AppData\Local\Temp\VALYQON_RU04_SAMPLES_e6c24eee5bfc454994c94cc73b349f9b`.
Сохранённый HTML скопирован без изменений в `tests/fixtures/ru04/b2b_center.html` (329456 байт).
SHA-256: `4a3840ff6e2157a8ee6a132677aca04b1edbf4fe9542dc1c1666a939f92b428d`.
HTML используется исключительно как недоверенные данные; скрипты и обработчики событий не выполняются.
Файл `public_probe.py` прочитан как данные, не запускался. Новых сетевых запросов не было.

Контрольная карточка `l15289907-3-9-1`: «Доработка сайта заказчика», организатор
«ГОСУДАРСТВЕННЫЙ МУЗЕЙ ИСТОРИИ РЕЛИГИИ», исходный номер `200909828126100317`,
ссылка ЕАТ `https://agregatoreat.ru/purchases/announcement/eb5ffd56-ca42-4fec-86e8-cd6d55b021db/info`,
100000 RUB, публикация `2026-10-13T17:50:04+03:00`, срок `2026-10-13T19:50:00+03:00`.
Другие карточки содержат ссылки РТС-тендер; исходные ссылки сохраняются, но не загружаются.

## Контракт и активация

`B2B_CENTER_ENABLED=false` по умолчанию. Только явное включение оператором добавляет
`b2b_center` в существующий `SourceRegistry` / `SourceCatalog`; metadata `official=False`.
Регистрация не создаёт customer subscriptions, задания или автоматическую активацию клиентов.
Roseltorg не зарегистрирован. Независимость источников обеспечена отсутствием общей активации.

Используются существующие `TenderSource`, `TenderNotice`, `MultiSourceFetcher`,
`BoundedClient`, `ConnectorSyncService`, `OpportunityRepository`, `SnapshotSource`
и scoring engine. Нет второго реестра, очереди, модели хранения или изменения схемы.
Подкласс notice следует уже существующему provenance-контракту EIS 223:
дополнительные поля сохраняются в JSON; базовая реконструкция остаётся `TenderNotice`.
Исходная ссылка, host и origin также сохраняются в `summary`, поэтому доступны после
snapshot/scoring реконструкции. `source=b2b_center` означает канал получения,
а `origin=aggregated` означает стороннюю площадку; неизвестный origin не угадывается.

Идентичность: `(b2b_center, идентификатор из валидированного detail path)`.
Detail URL строго HTTPS, host `www.b2b-center.ru`, путь `/search/number/<id>/`,
без credentials, query или fragment. Оригинальная ссылка сохраняется отдельно,
в том числе исходный HTTP, без искусственного повышения до HTTPS.
Поле customer содержит опубликованную организацию/организатора, а не самостоятельно
доказанного конечного покупателя. Регион не угадывается. Даты берутся из прямых
структурированных свойств Demand с timezone. Названия вложенных позиций не заменяют
название закупки. Цена берётся из карточного `PriceSpecification` только для RUB;
нулевая, неизвестная валюта и несколько разных цен оставляют цену неизвестной.
Не производится вывод цены из строк описания или суммирование лотов.

Транспорт: один listing GET, только разрешённый host, без redirect, proxy environment,
пагинации, detail GET, авторизации или исполнения JavaScript. Ограничение HTML 2 MiB,
глубины 128, результата 1–100; timeout валидируется и ограничивается существующим
bounded client. Worker policy и request counter сохраняются. PublicIPBackend защищает
фактическое соединение. Ошибки и пустая/неподдерживаемая выдача отражаются существующим
failure/status механизмом; HTTP 200 сам по себе не означает usable records.
Одинаковые дубликаты сворачиваются, конфликтующие идентификаторы отклоняются;
порядок сортируется по external_id. Источники ЕИС 44/223 не меняют парсинг или регистрацию.

Worker ingestion требует system scope и явной регистрации. Snapshot discovery читает
локальный repository без HTTP fallback. Scoring использует прежние правила и требует
включённый B2B-Center в catalog; tenant/customer проверки остаются существующими.
Общие parsing helpers не выделялись: новая структура отличается от CPPP и AusTender,
а новая общая абстракция не оправдана обнаруженным повторением.

## Проверки на Windows host

pytest в Codex sandbox не запускался. Интерпретатор `python` не найден в PATH;
runtime корректность и прохождение тестов пока не подтверждены.

В активированном окружении проекта выполнить:

```powershell
python -m pytest tests/test_ru04_sources.py tests/test_source_framework.py tests/test_source_catalog.py tests/test_connector_workers.py tests/test_source_http.py tests/test_source_http_transport.py tests/test_source_http_cleanup.py
python -m pytest tests/test_eis_223_rss.py tests/test_eis_223_persistence_contract.py tests/test_eis_223_scoring_contract.py tests/test_eis_business_metadata.py tests/test_ru03_integration.py tests/test_scoring_workers.py
```

Новые проверки покрывают сохранённую выдачу, точную карточку, identity/provenance,
неизвестные поля, некорректный HTML, duplicate conflict, detail validation,
host isolation, общий request budget, redirect refusal, default-off,
explicit registration, реальные worker/repository/snapshot контракты с временной SQLite,
отказ customer scope для ingestion и неизменность ЕИС registration.
Tenant/customer scoring isolation требует также существующего `test_scoring_workers.py`.
Capacity test регистрирует 100 искусственных источников, проверяет concurrency ≤8,
dedup, deterministic merge и изоляцию одной ошибки. Это не 100 live integrations.

## Следующий пакет 5–10 источников

1. Для Roseltorg и ещё 5–9 выбранных оператором площадок получить публичные образцы
   вне Codex, законным доступом без credentials, обхода CAPTCHA или access control.
   Кандидаты: РТС-тендер, ЕАТ, ТЭК-Торг, ЭТП ГПБ, Фабрикант, Сбербанк-АСТ,
   РАД, OTC, АСТ ГОЗ. Это кандидаты для исследования, не обещание доступности.
2. Сохранить URL запроса, время, status/content type, SHA-256 и HTML/feed/API payload;
   отдельно проверить listing/detail records. Для shell/blocked/login или отсутствия
   стабильной identity присвоить BLOCKED, не изобретать endpoints.
3. Проверить происхождение: собственная площадка или aggregator, исходный номер,
   canonical detail link, customer/organizer и семантику времени/валюты.
4. Сделать каждый поддержанный адаптер по существующему protocol с отдельным default-off
   флагом, условной регистрацией, ограниченными hosts/requests/bytes и без customer activation.
5. Добавить evidence-derived regression fixtures и мутации для malformed/unknown/link attacks,
   request budget, dedup, repository round-trip, snapshot/scoring и tenant isolation.
6. Только при подтверждённом повторении выделить небольшой parser/URL helper; сохранить
   единую очередь, registry, scoring и модель хранения. Повторить synthetic capacity test.
7. На host выполнить offline suite; отдельно оператору проверить разрешённый live smoke
   после review. До этого статус остаётся PARTIAL. Изменения оставить uncommitted.

RU04_IMPLEMENTATION=PARTIAL
PRODUCTION_TOUCHED=NO
COMMIT_CREATED=NO
