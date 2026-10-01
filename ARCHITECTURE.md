# TenderLens AI — intended architecture

Ниже целевая архитектура; реализованы Phase 1–6. Поток полного анализа пока планируется.
Обновление Phase 3: document handler -> services.pdf (загрузка с лимитом) ->
отдельный процесс parsers.pdf_worker -> PyMuPDF -> PdfSummary -> ответ в Telegram.
На диск файл не записывается; в текущем этапе сохраняется только статистика в ответе,
постраничный текст извлекается временно. Для будущего RAG потребуется отдельный контракт хранения.
app.bot.__main__ -> main -> config + Dispatcher -> handlers.
HTTP-сессией владеет run_bot и закрывает её в finally. На Windows Ctrl+C обрабатывает
asyncio.run; на других платформах включены signal handlers aiogram.
Команды отвечают статическими сообщениями; documents использует services.pdf.

## Поток анализа

```text
Telegram (позже HTTP API) / источник тендеров
                  |
                  v
             services
                  |
                  v
         parsers -> текст + страницы
                  |
                  v
      llm -> извлечение фактов -> проверка схемы
                  |
                  v
      scoring + профиль компании -> объяснимая оценка
                  |
                  v
       database -> ответ / уведомление пользователю
```

Отдельный поток RAG: документ -> фрагменты -> embeddings -> индекс;
вопрос -> поиск разрешённых пользователю фрагментов -> LLM -> ответ со ссылками.
SQL хранит метаданные и результаты; векторный индекс не заменяет SQL.

## Границы модулей

| Пакет | Назначение |
|---|---|
| app/bot | Telegram handlers, загрузки, представление ответов |
| app/api | FastAPI routes и HTTP-схемы |
| app/services | Сценарии анализа, извлечения, ответов и мониторинга |
| app/parsers | Преобразование документов в текст с источниками |
| app/llm | Общий контракт и заменяемые API-адаптеры GigaChat/YandexGPT |
| app/scoring | Детерминированные правила без зависимости от Telegram и LLM |
| app/database | Репозитории, SQL-модели, миграции |
| app/rag | Chunking, embeddings, поиск, связи с исходными страницами |
| tests | Будущие unit/integration/evaluation сценарии |

Bot и API вызывают services. Транспортные обработчики не рассчитывают score
и не обращаются к конкретному LLM SDK. Services получают зависимости явно,
чтобы в тестах заменять внешние API и хранилища.
Конкретные интерфейсы и модели данных будут введены при реализации соответствующих этапов.

## Данные и качество

Будущие сущности: пользователь/организация, профиль компании, тендер, документ,
страница/фрагмент, факты, запуск анализа, результат scoring и подписка.
Денежные значения — точные десятичные числа с валютой; сроки — с часовым поясом.
У каждого извлечённого факта сохраняется источник. LLM извлекает и объясняет,
а правила Python рассчитывают оценку. Недостаток данных показывается явно.
Scoring не является обещанием победы или автоматическим решением об участии.

Документы считаются недоверенными данными: содержащиеся в них указания не должны
разрешать вызовы инструментов или менять системные правила.
Поиск и выдача документов ограничиваются владельцем/организацией.
Логи не должны содержать ключи и полный текст конфиденциальных документов.

## Интеграции и исполнение

Первый LLM — GigaChat; YandexGPT можно подключить через тот же контракт.
Для GigaChat выбран официальный SDK 0.2.3; Phase 8.1 использует его Embeddings API, а vector store — Qdrant local mode.
SQL: возможен локальный SQLite, PostgreSQL — по требованиям развёртывания.
Долгий разбор документов не должен блокировать Telegram/API: механизм фоновых
задач выбирается при реализации, без обязательного Redis/Celery на старте.

Мониторинг начинается с одного разрешённого источника и дедупликации.
Файлы хранятся вне исходного кода; ограничения размера и времени обработки
проверяются до передачи в парсер/LLM.
Docker будет добавлен после появления запускаемых сервисов.

## Конфигурация

.env.example содержит пустые секреты. На Phase 2 python-dotenv загружает корневой .env
в окружение без перезаписи существующих переменных. Config читает токен только через
os.environ, проверяет наличие/формат токена и LOG_LEVEL до сетевых запросов.
При запуске выполняется getMe, затем long polling; сессия закрывается и при ошибке getMe.
Telegram не отправляет LLM-запросы; отдельная команда health выполняет запрос только при явном запуске.

Необязательный TELEGRAM_PROXY_URL передаётся в AiohttpSession(proxy=...). Без него
создаётся обычный Bot. Сессия по-прежнему закрывается в finally. URL и учётные данные
прокси исключены из repr настроек и маскируются при форматировании логов.
Автоматического обхода недоступного прокси прямым соединением нет.

## Реализованный LLM-слой (Phase 4)

`app.llm.health -> config -> GigaChatProvider.generate -> SDK OAuth + chat -> LLMResponse`.
Это отдельный поток; из Telegram и PDF к нему нет вызовов.

- base.py: Protocol LLMProvider с async generate(prompt, max_tokens), безопасные типы ошибок.
- models.py: неизменяемый LLMResponse без vendor-типов, с текстом и счётчиками токенов.
- config.py: независимая валидация окружения/.env; ключ исключён из repr.
- gigachat.py: официальный async client.achat.create, контекст закрывает HTTP-клиент;
  общий deadline, TLS включён, max_retries=0. Ошибки преобразуются в фиксированные
  сообщения; upstream body/headers и текст документов не логируются.
- health.py: явный live smoke test; импорт и Telegram startup не вызывают API.

Будущие services получат LLMProvider через аргумент конструктора/функции. Новый
YandexGPTProvider реализует тот же контракт; Telegram не должен импортировать SDK.
Провайдер создаёт SDK-клиент на один generate: простое владение ресурсами, но без
межзапросного кэша OAuth-токена. Для будущей нагрузки потребуется отдельный lifecycle.
SDK может обновлять авторизацию после 401; общий timeout ограничивает этот путь.
Настройка storage=False отключает thread storage запроса, но не является гарантией
политики хранения данных на стороне поставщика. Инструменты модели не включены.

## Общие настройки сети
app.network проверяет OUTBOUND_PROXY_URL. bot.config выбирает непустой
TELEGRAM_PROXY_URL, затем общий прокси, затем прямую сеть ОС.
llm.config при запуске переносит общий HTTP-прокси в окружение HTTPX до создания
ленивых OAuth/API клиентов SDK. Это startup-only настройка процесса, не временная
подмена окружения вокруг async-запроса. Пустое значение сохраняет унаследованную сеть.
NO_PROXY, TLS и CA bundle сохранены. SDK не предоставляет отдельного proxy-параметра;
не используются monkeypatch или изменение приватных полей SDK в приложении.
Для смены прокси нужен перезапуск; адреса задаются конфигурацией, не исходным кодом.

## Phase 5: реализованный поток фактов
main загружает LLM-конфигурацию один раз до polling и передаёт provider/лимит через
Dispatcher dependency injection. Telegram знает только контракт generate;
провайдер GigaChat выбирает composition root main. Ошибка настройки не ломает PDF.
PdfSummary теперь переносит ограниченный text (исключён из repr) из worker в память.
documents → services.tender_analysis → LLMProvider → TenderAnalysis → bot.tender.
Сервис нормализует текст, записывает truncation, формирует JSON-only запрос без tools,
отклоняет дубли ключей, NaN, лишние поля и неправильные типы/диапазоны.
Модель ответа не содержит SDK-типов. Неизвестные скаляры null, списки пусты.
Formatter использует plain text, разбиение учитывает UTF-16 лимит Telegram.
Никакого scoring, выбора участия, сохранения в БД или RAG. Старое описание отдельного
health-потока Phase 4 остаётся историей; теперь читаемые PDF подключены к LLM.


## Phase 6: детерминированный scoring

`documents -> tender_analysis -> TenderAnalysis -> scoring.engine -> ScoringResult -> bot.scoring`.
`CompanyProfile` загружается один раз в composition root из JSON-файла, путь задаётся
`COMPANY_PROFILE_FILE`; секретов профиль не содержит. Telegram и LLM не вычисляют score.

Scoring разделяет:
- fit — взвешенное соответствие только по критериям, для которых есть данные;
- completeness — наличие ключевых извлечённых групп фактов;
- document risks — риски, извлечённые из документа LLM-слоем;
- stop factors — нарушения явных hard-stop правил профиля.

Отсутствующие факты дают `not_scored`, поэтому неизвестность не превращается в отрицательное
совпадение. Веса MVP: category 30, region 15, budget 20, bid security 10, contract
security 10, documents 15. Документ readiness — только keyword-проверка и не доказывает
юридическую действительность документов. Fit не является прогнозом победы и не принимает
решение об участии. Для реальной компании нужен отдельный профиль и проверка правил.

## Phase 7: SQLite persistence and user-scoped deduplication

Composition root создаёт `TenderRepository` из `DATABASE_URL` и передаёт его через
Dispatcher dependency injection. Локальный MVP поддерживает только `sqlite:///` URL.
Схема создаётся idempotent SQL-скриптом и содержит версию схемы.

`tenders` хранит: Telegram owner id, chat id, SHA-256 PDF, безопасное имя файла,
страницы/число символов, JSON строгих Pydantic-моделей анализа/scoring, признак
усечения и UTC timestamps. Уникальность `(owner_user_id, pdf_sha256)` обеспечивает
дедупликацию без пересечения данных разных пользователей.

Поток нового документа:
`download -> SHA-256 -> user-scoped duplicate lookup -> PDF parse -> LLM -> scoring -> save`.
При точном дубликате сохранённые Pydantic-модели валидируются при чтении и повторно
рендерятся в Telegram; LLM и PDF parser не вызываются. База не хранит PDF bytes или
полный извлечённый текст.

`/history` читает последние 10 записей только для `message.from_user.id`. SQLite-операции
вызываются через `asyncio.to_thread`, поэтому короткие локальные SQL-запросы не блокируют
async Telegram loop. Для многопроцессного/серверного масштаба Phase 10/11 может заменить
этот репозиторий PostgreSQL-реализацией с миграционным инструментом.


## Phase 8.1 semantic RAG

После чтения PDF parser сохраняет page-level text только в памяти. `app.rag.chunking` создаёт
ограниченные chunks с overlap и номером страницы. `GigaChatEmbeddingProvider` пакетно вызывает
локальный FastEmbed (`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` по умолчанию), а `QdrantVectorStore` сохраняет
vectors + page/chunk metadata в Qdrant local mode. Фильтры Qdrant всегда включают
`owner_user_id` и `pdf_sha256`, поэтому retrieval изолирован по пользователю и документу.

`/ask <вопрос>` строит semantic embedding вопроса, делает cosine top-k query в Qdrant, ограничивает
общий контекст и вызывает существующий LLMProvider. Prompt запрещает внешние знания/догадки;
ответ показывает страницы retrieved chunks. Embedding network call выполняется через worker thread,
чтобы не блокировать aiogram event loop.

Qdrant client открывается короткоживущими сессиями и явно закрывается, что важно для Windows file
locks в local mode. Коллекция создаётся по размерности первого embedding. Если embedding model
изменит размерность, система требует новое имя `RAG_QDRANT_COLLECTION`, вместо тихого повреждения индекса.

Исходный PDF не хранится; `data/qdrant/` содержит chunk text и vectors, считается чувствительным
локальным хранилищем и исключён из Git. При production deployment local Qdrant можно заменить на
Qdrant server/Cloud, сохранив контракт `RagService` и Telegram workflow.


## Phase 9 monitoring architecture
`EIS RSS -> app.sources.EisRssSource -> TenderNotice -> monitoring.prefilter -> monitor_seen -> Telegram`.
The source adapter is intentionally separate from Telegram. Search filters are encoded in operator-supplied RSS URLs, not hard-coded. Monitoring persistence uses the existing SQLite file but separate tables. Background polling fetches the configured feed set once per cycle, then applies per-user dedup before notifications. Manual `/tenders` uses the same service. RSS metadata is only a coarse pre-filter; authoritative document analysis remains the Phase 5–8 pipeline.


## Phase 10 HTTP boundary
`app.api` is a second transport beside Telegram. `create_app()` receives an `ApiRuntime`, which makes tests independent of live GigaChat/EIS/Qdrant. Production runtime composition loads each component independently and `/health` reports `ready`/`unavailable` without exposing secrets. API handlers call the existing repository, scoring engine, analysis service, RAG service and monitoring service; they do not contain scoring formulas or vendor SDK code.

Security defaults: bind `127.0.0.1`, bounded multipart PDF input, owner-scoped history/RAG, no raw PDF persistence, and optional constant-time `X-API-Key` comparison. Any non-local deployment must set an API key and put the service behind HTTPS/reverse-proxy controls; Phase 10 does not implement user authentication, rate limiting or multi-tenant authorization beyond the existing owner scope.

## Phase 11 deployment topology

```text
Windows / Linux host
        |
  127.0.0.1:8000
        |
+-----------------------+
| TenderLens API image  |
| Python 3.12 / Uvicorn |
| non-root uid 10001    |
+-----------+-----------+
            |
            v
   named Docker volume
       /app/data
      /         \
 SQLite       Qdrant local
   |              |
 monitoring     RAG chunks
                  |
          FastEmbed cache
```

Secrets are runtime environment variables from `.env`; they are not copied into the image. The Russian trusted root CA used by the existing GigaChat/EIS configuration is a public trust certificate and is copied into `/app/certs` so the current TLS setup continues to work inside Linux containers.

This topology is a single-node deployment. Local Qdrant mode and SQLite are intentionally kept behind one API process. A future horizontally scaled deployment should move those stateful components to server-backed services rather than mount the same local files into multiple replicas.
