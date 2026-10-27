# VALYQON AI — безопасная сверка кода и Docker-образа (27 октября 2026)

**Статус: только CI-аудит, НЕ разрешение на деплой.** Эта ветка ничего не выполняет на работающем VPS.

## Проблема

Read-only аудит владельца зафиксировал работающий контейнер `phase20-valyqon`
с локальным идентификатором `sha256:c3122a0deabcd1568bb55f74061cb2d61eeb6d57d088783986c0508b465dbf27`.
У него нет подтверждённой связи с коммитом GitHub; текущее `main` со страницей
`landing_html` само по себе не является доказательством, что этот код развёрнут.
Внешняя публикация ещё показывает `GET / → 303 /login` и `/assets/premium.css → 404`
по отчёту оператора 27 октября. Рабочая SQLite расположена в отдельном volume.
Запуск нового API может применить миграции к этому volume, поэтому запускать
кандидата на существующей базе нельзя.

## Что доказывает новый GitHub workflow

`.github/workflows/release-image-local-provenance-audit.yml`:

1. На чистом GitHub runner делает checkout конкретного commit SHA.
2. Собирает **отдельный локальный** контейнер через исходный Dockerfile,
   добавляет OCI labels `org.opencontainers.image.revision`,
   `org.opencontainers.image.source` и признак `isolated-ci-audit-only`.
3. Скрипт `scripts/valyqon_ci_image_provenance.py` сверяет точный SHA checkout,
   git tree, Dockerfile sha256, OCI labels, Docker ID и ожидаемый локальный tag.
   Несоответствие приводит к FAIL.
4. Сохраняет в GitHub Actions artifact `valyqon-local-image-identity.json`
   только заранее разрешённые поля; никогда не публикует `docker inspect`
   целиком, Environment/Secrets, registry URL, customer data или SSH credentials.
5. Никуда не отправляет образ, не трогает VPS, не читает `.env`,
   не обращается к SQLite или PostgreSQL.

OCI label устанавливается самим билдом: это **внутренняя проверка
последовательности Git checkout → Docker build**, НЕ цифровая подпись/
самостоятельная доверенная аттестация, НЕ подтверждённый удалённый digest,
НЕ доказательство, что идентичный образ запущен на VPS. Идентификатор
`sha256:…` локального образа не равен автоматически registry RepoDigest.

## Матрица текущих релизных доказательств

| Этап | Доказательство | Итог |
|---|---|---|
| Код → локальная CI-сборка | Exact SHA, OCI revision, local image ID из GitHub Actions | Только после PASS нового workflow |
| Локальная CI-сборка → утверждённый артефакт для релиза | Подписанная attestation, репозиторий артефактов, immutable OCI digest, reviewed release SHA | NOT VERIFIED |
| Утверждённый артефакт → VPS | Совпадение фактически запущенного digest/ID с подписанной публикацией | NOT VERIFIED |
| Рабочая SQLite → зашифрованный off-host backup | Свежий согласованный backup + receipt/object version/retention | NOT VERIFIED |
| Off-host → isolated restore | Подтверждение decrypt, integrity, schema и recovery time | NOT VERIFIED |
| Candidate → восстановленная копия | Не разделять live volumes, отключить все outbound workers/telegram/billing | REQUIRES OWNER APPROVAL |
| Схема и rollback | Репетиция старого image/config с совместимой восстановленной DB | NOT VERIFIED |
| Публичный HTTPS | 200 на `/`, исправный CSS, отдельный login и truthful /health | FAIL на старой публикации |
| SaaS commercial | Legal, billing, provider SMTP, original-source delivery to consenting user | BLOCKED |

### Только отдельное явное согласие владельца

Создание, загрузка и хранение off-host backup; выделение restore volume;
ограничение writers; запуск нового candidate с восстановленной БД; миграции,
изменения routing/HTTPS/Caddy и rollback — **не относятся** к этому PR.
Не передавать приватный SSH key, `.env`, содержимое backup, URL с токеном
или персональные данные через GitHub Issues, Actions и чат.

Окончательный relase gate: применить строго рассмотренный source SHA и
неизменяемый digest, зафиксировать исходное состояние, сделать свежий
off-host backup с независимым restore, проверить candidate на копии,
отрепетировать rollback, получить явное owner approval, только затем
рассматривать cutover. Отдельно потом PostgreSQL и коммерческие функции.

Связанные: Draft PR #318, issue #319. Эта работа не заменяет их и не
автоматизирует ни один production шаг.
