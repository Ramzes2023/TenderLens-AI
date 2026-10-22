# Чеченская Республика — региональный ЕИС 44-ФЗ (VALYQON)

Status: **draft; production disabled; no verified live delivery** until all checks described below pass. No national search result is counted as a Chechnya tender merely because the title mentions the region.

## Original source and scope

- Original publication: [ЕИС](https://zakupki.gov.ru/). Official regional authority: [Комитет Правительства Чеченской Республики по госзаказу](https://gostorgi-chr.ru/). The committee homepage is not claimed to expose a live tender API.
- Supports **44-ФЗ** RSS results only. This does not claim to cover 223-ФЗ, commercial platforms, regional small purchases outside ЕИС, or all federal buyers delivering to Chechnya.
- Each accepted entry must carry a valid EIS 44-ФЗ original registry number and an official original URL, with Chechnya/Grozny evidence in the EIS customer/region fields.
- One original 44-ФЗ procedure is deduplicated across `eis` and `ru_chechnya_eis`.

## Configure, only after successful acceptance

1. Open EIS **advanced procurement search** using the browser on a trusted host. Select 44-ФЗ and the customer location **Чеченская Республика**. Click its official RSS link; copy the exact full RSS URL, preserving the search parameters. **Do not invent `customerPlace` or region IDs**. An optional explicit text search for Чеченская Республика is narrower than the regional filter.
2. Set `RU_CHECHNYA_EIS_RSS_URLS` to that URL and `RU_CHECHNYA_EIS_ENABLED=true`. It is required to supply both settings; empty URLs while enabled cause an error. If using PowerShell, set environment variables for the current process with `$env:RU_CHECHNYA_EIS_ENABLED="true"` and `$env:RU_CHECHNYA_EIS_RSS_URLS="<copy official link>"`.
3. Keep `EIS_DIRECT_ENABLED=true` with a **verified** trusted CA source. On Windows use `EIS_SYSTEM_TRUST_ENABLED=true` when official server-auth trust has been separately checked. On Linux/WSL use a vetted `EIS_CA_BUNDLE_FILE` if necessary. **Never use verify=false, skip TLS checks, or download and trust a server-supplied chain.**
4. In an isolated environment run `python -B -m pytest -q tests/test_ru_chechnya_eis_rss.py` then `python -B -m scripts.ci_ru_chechnya_eis_real_worker`. A successful unit suite is **not** equivalent to live source validation.
5. **Before merge, use the trusted Windows runner/host (supported):** from the exact Chechnya feature branch, execute `powershell -NoProfile -ExecutionPolicy Bypass -File .\\scripts\\ru_chechnya_windows_live.ps1 -RegionalRssUrl '<full RSS URL copied from the official UI>'`. The launcher forces direct HTTPS, trusted Windows server-auth certificates, local offline tests and the isolated strict EIS → leased Worker → disposable SQLite → original-number and keyword searches → LOCAL alert capture and replay dedup. It restores inherited process environment variables and does not mutate production. `PASS_LOCAL_ONLY` does **not** mean Telegram Bot API delivery. No custom certificate installation or TLS bypass is performed by this script.
6. **Pre-merge live GitHub gate:** GitHub normally requires a `workflow_dispatch` workflow file on the repository **default branch**. To avoid merging an unverified source just to expose its manual Run button, the workflow now has a narrow `push` trigger for the repository-owned `feat/ru-chechnya-eis-rss-20261022` branch. The push first runs offline contracts on GitHub-hosted Ubuntu; only then a separate job attempts the official EIS `chechnya-real-live-worker` on `[self-hosted, Linux]`, using `VALYQON_RU_CHECHNYA_EIS_RSS_URL` if supplied as a repository variable, otherwise a clearly marked **unverified text-search candidate**. This job never runs on `pull_request` code, never changes production settings and has both test Telegram credentials intentionally blank. The trusted Russian operator must still confirm location/TLS, real EIS originals, temporary SQLite, original-number and keyword queries, and separately authorize a Telegram Bot API test on Windows. The push gate is **diagnostic** until each of those is confirmed.

## Опциональная проверка без ручного копирования RSS

До подтверждения точного регионального фильтра ЕИС оператор может выполнить на Windows, находясь в ветке PR #236:

```powershell
.\\scripts\\ru_chechnya_windows_live.ps1 -TryOfficialSearchCandidate
```

Это **только кандидат** стандартного RSS-запроса ЕИС по тексту «Чеченская Республика» и 44-ФЗ, а **не** подтверждённый региональный RSS-фильтр из интерфейса сайта. Запрос не делает результаты «чеченскими» автоматически: каждый принятый номер должен иметь официальную карточку 44-ФЗ и независимое доказательство заказчика/региона в извещении. При отсутствии таких данных проверка завершится ошибкой.

Если строгая Worker-приёмка завершится неуспешно, Windows-скрипт автоматически запускает отдельную read-only проверку `python -B -m scripts.ru_chechnya_eis_transport_probe`, которая не отключает TLS и выводит **только** безопасную причину (`DNS_RESOLUTION_FAILED`, `TLS_CERTIFICATE_OR_HANDSHAKE`, `TIMEOUT`, `HTTP_403`, `INVALID_RSS_OR_LAW`, `VALID_FEED_NO_CHECHNYA_EVIDENCE` и т. п.). Ни URL, ни описание закупки не печатаются. Диагностика **не** является доказательством Worker или доставки в Telegram.

При успешной приёмке одна и та же закупка, даже при изменении RSS GUID, должна сохранять ключ `ru_chechnya_eis/<реестровый номер 44-ФЗ>`; соответствующий ключ в блоке публичного provenance обновляется вместе с идентификатором.

## Отдельное подтверждение Telegram Bot API

По умолчанию живой скрипт **не отправляет** внешних сообщений. Чтобы добровольно проверить внешний Bot API **после** успешной загрузки настоящей закупки, оператор предварительно задаёт в текущем PowerShell-процессе токен отдельного тестового бота и идентификатор разрешённого тестового чата, не сохраняя их в GitHub или в логи:

```powershell
$env:RU_CHECHNYA_E2E_TEST_BOT_TOKEN = '<test-bot-token>'
$env:RU_CHECHNYA_E2E_TEST_CHAT_ID = '<authorized-test-chat-id>'
.\\scripts\\ru_chechnya_windows_live.ps1 -TryOfficialSearchCandidate -SendAuthorizedTelegramTest
```

Можно вместо `-TryOfficialSearchCandidate` использовать проверенный `-RegionalRssUrl '<точная-ссылка-ЕИС>'`. Без `-SendAuthorizedTelegramTest` скрипт временно скрывает тестовые реквизиты от процесса приёмки, даже если они были заданы ранее, и возвращает исходные значения после завершения. При включённом флаге отправляется **один** проверенный публичный оригинал 44-ФЗ, только в явно указанный чат; наличие валидного `message_id` и совпадение `chat.id` проверяются по реальному ответу Telegram. API acknowledgement означает принято сервером Telegram, но не доказывает прочтение пользователем. Уведомления рабочим пользователям и production не включаются.

Токен, полный URL запроса и ID тестового чата не выводятся в диагностические логи. Никогда не публикуйте тестовые токены в PR, workflow inputs или issue.

## Публичный контрольный номер для проверки качества регионального поиска

Для ручной проверки фильтра найден **сторонний** публичный пример от 16.10.2026: [№ 0194200000526005373 — «Поставка продуктов питания»](https://zakupki.kontur.ru/0194200000526005373). В карточке указаны организация-разместитель **Комитет Правительства Чеченской Республики по государственному заказу**, **44-ФЗ** и срок подачи заявок до **26.10.2026**. Этот номер **не** используется как фикстура в strict-live приёмке и **не подтверждает** прямой доступ к оригиналу ЕИС. Официальная карточка, наличие записи в текущем RSS, строгий TLS, Worker, SQL и отправка в Telegram проверяются независимо. Отсутствие номера в маленьком окне RSS не означает, что источник в целом нерабочий.

## Диагностика: полный оригинал или только региональная метка

Сетевая read-only проверка `scripts.ru_chechnya_eis_transport_probe` использует **одинаковый с адаптером** предикат отбора оригиналов 44-ФЗ. Успешный сетевой ответ с полем «Регион: Чеченская Республика», но без допустимого 19-значного `regNumber` в официальной HTTPS-карточке ЕИС возвращает `VALID_FEED_NO_ACCEPTED_ORIGINALS` и ненулевой код выхода. Поле `regional_evidence_count` отдельно показывает метки региона, а `accepted_original_count` — количество пригодных оригиналов без повторов. Только `VERIFIED_FEED_WITH_ACCEPTED_ORIGINALS` разрешает признать сетевую *диагностику* успешной; оно **не** подтверждает Worker, SQLite, поиск или Telegram.

Windows-скрипт отличает `PASS_LOCAL_ONLY` от `PASS_LOCAL_AND_TEST_BOT_ACK`. В обоих случаях `PRODUCTION_USER_DELIVERY=NOT_VERIFIED`: подтверждение тестового Bot API не является фактом уведомления настоящего пользователя и не активирует production.

## Второй контрольный номер — актуальная закупка октября 2026

Независимый публичный каталог [Контур.Закупки](https://zakupki.kontur.ru/0194200000526005433) показывает **№ 0194200000526005433**, опубликованный **19.10.2026**, объект «Поставка продуктов питания», размещающая организация — Комитет Правительства Чеченской Республики по государственному заказу, закон **44-ФЗ**, срок заявок **27.10.2026 09:00**. Сверьте этот номер в **официальном** ЕИС на российском рабочем компьютере. Это **вторичная контрольная подсказка**, не признак успешного RSS, попадания в выдачу текущего RSS-окна или доставки пользователю. Живой тест использует только полученные с официального RSS данные и не подставляет этот номер искусственно.

## Merge gate — all of the following

- PR tests and all required repository checks green on the current head commit.
- Real official EIS RSS and original notice links with strict HTTPS and 44-ФЗ verification; **nonzero real notices** from the Chechen Republic.
- Real leased `connector.sync.v1` Worker has persisted notices to disposable SQLite with no skipped entries, user exact-number and title-keyword searches recover the same notice, unrelated queries return nothing.
- Repeat delivery is idempotent. A real regional tender reaches the **local Telegram message boundary** in the strict script; the script **does not send Telegram externally**.
- Separate operator evidence of **real Telegram API acknowledgement to an authorized test chat**, plus deployment monitoring, is required before claiming *actual delivery to users*. Never report local capture as external delivery.
- Approve and merge only after those proofs. Turn on production configuration only in a separate explicitly reviewed operator activation.

## Failure handling

No live feed, empty/ambiguous regional data, redirect, invalid CA, challenge, HTTP error, wrong law, or invalid original ID => **BLOCKED**, no merge and no production activation. The acceptance script prints `RU_CHECHNYA_EIS_STRICT_LIVE=BLOCKED_...` with a nonzero exit code. The offline PR workflow is never a substitute for live verification.

## Related files

- `app/sources/ru_chechnya_eis_rss.py`: strict regional adapter
- `app/sources/catalog.py`, `app/monitoring/config.py`: source registration and operator opt-in
- `app/sources/ingestion.py`: official host and bounded Worker requests
- `app/sources/ru_notice_identity.py`, `app/sources/ru_dedup.py`: original EIS duplicate handling
- `scripts/ci_ru_chechnya_eis_real_worker.py`: strict real data → Worker → SQL → search → local alert acceptance
- `scripts/ru_chechnya_windows_live.ps1`: opt-in Windows trusted-root execution of pre-merge live acceptance
- `scripts/ru_chechnya_eis_transport_probe.py`: official RSS safe network error categories and regional evidence count
