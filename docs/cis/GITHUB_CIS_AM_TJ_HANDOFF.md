# Передача AM/TJ в GitHub main

Дата: 2026-10-15. Интеграция локальная, без commit/push/merge/deploy. Production readiness НЕ заявляется.

## Реализовано

Перенесены реальные reviewed адаптеры am_armeps.py, tj_eprocurement.py и обязательный transport_errors.py из .tmp-cis-input. Общие файлы не заменялись staging-снимками: catalog получает только регистрации и локальный поиск snapshot AM/TJ; ingestion — hosts, бюджет AM и тип временной ошибки; http — сохранение причины транспортной ошибки. Существующие opportunities.py, snapshots.py и __init__.py не изменялись: их текущий контракт совместим, адаптеры доступны через собственные модули.

AM/TJ зарегистрированы official HTML, enabled=False без нового переключателя окружения. AM: https://eauction.armeps.am/en/public/tender/, две listing-страницы по умолчанию и принудительно в ingestion. Парсер проверяет наблюдавшийся семиколоночный DOM и точный detail URL; detail enrichment не выполняется. В адаптере сохранён staging opt-in max_pages до 5, страницы после второй требуют наблюдаемой ссылки; worker всегда ограничен двумя запросами. TJ: https://eprocurement.gov.tj/ru/searchanno, одна страница, без пагинации и detail fetch. Live keyword search, документы, authenticated API и incremental sync для AM/TJ не заявлены.

Российские источники, EIS 223, B2B-Center, World Bank, TED search, настройки EIS direct/system trust, enrichment/provenance и остальные регистрации main сохранены. Оригинальные assertions tests/test_source_catalog.py сохранены, в точный список ключей добавлены только AM/TJ. SaaS, AI, auth и security файлы не менялись; полная регрессия этих подсистем здесь не выполнялась.

## Security evidence и офлайн-проверки

Новый tests/test_cis_am_tj_main_integration.py самодостаточен, не импортирует staging-тесты и не читает .tmp-cis-input. Синтетические fixtures проверяют actual adapter + bounded client + handler, точные HTTPS hosts и бюджеты 2/1, provenance, disabled enqueue/fetch, строгий payload, отказ redirect/unknown network/TLS/changed DOM/oversize/unsafe link, retryable timeout/503, сохранение внешней policy и изоляцию snapshot terms. Сеть и DNS запрещены в fixture; Windows asyncio разрешён только внутренний socketpair через узкий context marker. БД новый acceptance не использует. Запись проверяется Mock repository, это не доказательство транзакционной атомарности.

Существующая защита транспорта сохраняет TLS verification, public-IP DNS/connect checks, bounded bytes, no redirect и trust_env=False в AM/TJ. Единственное изменение shared HTTP: `from error` вместо `from None` сохраняет cause для отказа повторов при TLS и неизвестных network errors; наружные сообщения адаптеров и job ошибок остаются обезличенными. Изменение cause влияет и на другие bounded connectors и требует внимания при будущих изменениях логирования.

Использован существующий C:/Users/ramze/Documents/Codex/.valyqon-cis-venv/Scripts/python.exe, Python 3.12, без установки пакетов. Для pytest: PYTEST_DISABLE_PLUGIN_AUTOLOAD=1, PYTHONDONTWRITEBYTECODE=1, PYTHON_DOTENV_DISABLED=1; префикс `python.exe -B -m pytest -p no:cacheprovider`.

- `tests/test_cis_am_tj_main_integration.py tests/test_source_catalog.py -q`: **36 passed**, exit 0, 1.50s. Первый запуск нового acceptance дал 25 failed/9 passed из-за неверного EIS URL в fixture и запрета внутреннего Windows socketpair; исправлены только новые fixtures. Промежуточный результат 34 passed; после двух snapshot cases финальный 36 passed.
- `tests/test_source_framework.py tests/test_source_http.py tests/test_source_http_transport.py tests/test_source_http_cleanup.py tests/test_ru_source_integration_contract.py tests/test_international_sources.py -q --tb=short`: **490 passed, 2 skipped, 1 error**, exit 1, 26.70s. Ошибка setup: системный pytest TEMP недоступен, до открытия тестовой БД. Пропуски — raw deflate has no checksum.
- `tests/test_ru_source_integration_contract.py --basetemp=.tmp-cis-main-acceptance-20261015 -q --tb=short`: **8 passed**, exit 0, 1.42s; disposable SQLite создан существующим тестом в новом локальном tmp-каталоге. Существующие БД не открывались. Наборы пересекаются, числа не суммируются; первый exit 1 не скрывается.
- Отдельный read-only replay переданных captures: armenia_1_20261014T140705Z.html — 30, armenia_2_20261014T140705Z.html — 30, tj_20261014T170109027821Z.html — 50 notices; exit 0. Это сохранённый HTML от 14 октября, не live-проверка 15 октября. Captures не скопированы в tracked paths.
- `git diff --check`: exit 0.

## Блокеры и merge risks

Известный **unfenced connector upsert** НЕ исправлен: ConnectorSyncHandler вызывает OpportunityRepository.upsert напрямую для каждого notice, без context.fenced_write. Отказ stale job complete не отменяет уже сделанные записи; возможна перезапись старым worker после истечения lease. Нет whole-sync rollback или атомарности notices + succeeded. Составной ключ подавляет дубли строк, но не обеспечивает exactly-once side effects. Нужен отдельный дизайн транзакций/fencing и fault injection; app/jobs вне разрешённого scope не менялся.

PostgreSQL, отдельные процессы workers, crash/restart, нагрузка, конкурентные stale connector writes и полный production runtime не проверены. API E2E/auth/tenant/AI acceptance из staging reports не переносится автоматически на эту ветку и не объявляется заново доказанным. Scoring allowlist не расширялся: metadata discovery не означает full AI scoring.

Snapshot поиск использует действующий repository: последние 1000 строк, первые 20 terms, substring OR, cap до CompanyProfile; глобальная полнота, исключения и discovery pagination не гарантированы. Новый тест подтверждает передачу terms и отсутствие мутации каталога, а не полноту поиска.

Строгие HTML схемы могут перестать соответствовать upstream; timezone deadline не уточнялась. Активацию AM/TJ следует рассматривать отдельно после устранения блокеров и новой разрешённой live-валидации. Не переносить старые shared snapshots: они удаляют актуальные RU/World Bank/provenance возможности. Staging reports CIS-86–115 — историческое evidence, включая прежний flaky timeout и ограничения lease checks, не результаты текущего main.

В tracked scope только разрешённые адаптеры, shared additions, два тестовых файла и этот документ. .tmp-cis-input, venv, captures, отчёты staging и DB не добавлялись. AWS, Docker, production, secrets и другие worktrees не использовались.
