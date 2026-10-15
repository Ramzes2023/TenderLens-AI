# PHASE24P4 — основной SaaS, read-only bridge: STOP

Дата: 2026-10-12. Результат: bridge **не подключён**. Production P4 остаётся
заблокированным до отдельной авторизации и приёмки безопасности.
Изменение этой задачи — только данный новый документ.

## Подтверждённые блокеры

1. **Gate P3.9 не разрешает подключение к основному UI.**
   `docs/PHASE24P39_RUNTIME_GATE.md`, раздел P3.9C, прямо фиксирует
   «P3.9 PARTIAL; P4 BLOCKED» и необходимость отдельного решения об интеграции.
   Доказательства Windows Job Objects относятся к невключённому синтетическому
   прототипу, не к запросу аналитики с аутентификацией, получением соединения,
   чтением БД, вычислением и доставкой HTTP-ответа. Живой disconnect,
   PostgreSQL и полная ресурсная защита запроса не приняты.
   В текущем `app/api/main.py` analytics router уже зарегистрирован, но используется
   `Admission(limit=2)` из `app/analytics/admission.py`: `ThreadPoolExecutor`,
   `asyncio.shield`, проверка deadline до и после выполнения. Отмена ожидания
   не останавливает поток; deadline не прерывает зависшую операцию внутри потока.
   `shutdown()` ждёт освобождения leases. Лимит конкурентности и проверяемые
   размеры не доказывают принудительную остановку или предел памяти/CPU всего
   запроса. Наличие маршрута само по себе не закрывает gate. Браузерный
   AbortController этот серверный блокер не устраняет.

2. **Нет существующего механизма EN/RU в основном Dashboard.**
   `app/api/dashboard.py` задаёт `<html lang="en">`;
   `saas_shell.py`, `command_center_ui.py`, `premium.js`, `shell.js` и прочитанные
   history/discovery/source-health модули используют буквальные английские
   подписи и сообщения. В этой цепочке нет общего словаря EN/RU, выбранного
   языка и события его изменения. Документ `PHASE24P39H_LOCAL_I18N.md`
   относится к локальному offline preview и не доказывает механизм main SaaS.
   Введение отдельного переключателя или определения языка только в premium.js
   не было бы повторным использованием фактического механизма приложения;
   получилось бы смешение языков с существующими подписями и aria-label.
   По условию задачи это блокер, а не основание расширять область изменений.

## Реальный контракт, прочитанный без обращения к API

- GET `/api/v1/organizations/{organization_id}/companies/{company_id}/analytics/v1/history/aggregate`.
  Обязательный query-параметр: `timezone_name`. По умолчанию `deadline_days=7`,
  `page_size=20`, `order=identity`; `start`/`end` необязательны, интервал `[start,end)`.
  Неизвестные и повторные параметры отклоняются. Rows/replay существуют отдельно;
  replay требует подписанный token. Никакой запрос в рамках задачи не выполнялся.
- `_authorize()` вызывает `current_account(request, touch=False)`, проверяет
  membership роли owner/admin/member/viewer и компанию именно в организации.
  Авторизация и digest профиля проверяются повторно перед ответом. Запрос
  явно адресует company_id; он не выбирает активную компанию браузера автоматически.
- Успешный JSON — `AnalyticsResponse` без обёртки `data`:
  `population`, `population_token`, `kpis`, `drilldowns`, `distributions`,
  `deadline_buckets`, `search_activity`, `metadata_counts`, `source_observations`,
  `rows`, `total`, `next_cursor`, `order`. `total` — число выбранных rows,
  не замена KPI и не lifetime total.
- `population` содержит version `company-analytics-v1`, origin `H`,
  organization_id/company_id, population_id, временной интервал, timezone,
  coverage, source_search_coverage, unknowns и другие поля контракта.
  `lifetime_total=null`; D/R/P capability остаются unavailable.
- Шесть точных ключей `kpis`: `Discovered`, `Matched`, `High Fit`,
  `Active Sources`, `Countries`, `Closing Soon`. Каждый `Measure` содержит
  `value: int|null`, `numerator`, `denominator`, `identities`, `coverage`,
  `reason: string|null`, `time_field`, `unit`.
- `service.py` устанавливает `value=null`, если есть reason. Частично неудачные
  поиски, отсутствие eligible fit, наблюдений источников, доказательств страны
  или instant deadline могут означать unavailable. `numerator` не заменяет null.
  Ноль не равен неизвестному; некоторые KPI пустой валидной популяции равны нулю,
  тогда как Active Sources без наблюдений остаётся null.
  Active Sources означает distinct successfully reached sources в истории,
  не текущую доступность, настройку мониторинга или состояние healthy.
  Countries использует поддержанные доказательства страны; geodata не создаётся.
- Ошибки маршрута: 401 — нет аутентификации; 403 — доступ запрещён;
  404 — компания не найдена в разрешённой организации; 409 — изменение
  исторической популяции/профиля, требуется новое чтение; 422 — неверные
  параметры/token; 503 — storage, capacity, budgets или invalid evidence.
  Ни одна из ошибок не является пустой успешной популяцией. Успешный ответ
  имеет `Cache-Control: no-store`.

## Существующая frontend-конвенция и оставшаяся работа

History/Source Health используют `fetch` с `credentials: 'same-origin'`,
`cache: 'no-store'`, проверяют HTTP status, затем JSON, и повторно проверяют
serial и identity `${state.organizationId}:${state.activeCompanyId}:${state.uiEpoch}`.
Discovery также отменяет запрос через AbortController. Shell инвалидирует
activeCompanyId и увеличивает uiEpoch при переходах workspace. Навигация
`#monitoring` реально существует и относится к monitoringCenter; новый link
не добавлен и работоспособность страницы не заявляется как результат теста.

После отдельного закрытия обоих блокеров bridge должен валидировать scope
ответа против активной организации/компании, сбрасывать значения до перехода,
проверять stale response после fetch и JSON, различать loading/error/403/404,
null/unavailable и zero, отображлять недоверенные строки через textContent.
Нужен отдельный targeted Node-тест источника и поведения DOM, включая смену
компании, stale response, ошибки и недоверенные строки. Сейчас bridge и новый
тест намеренно не созданы: условие STOP разрешает максимум новый документ.

## Проверки и границы

Прочитаны указанные пользователем модули и необходимые прямые зависимости
контракта/gate. AGENTS.md в корне, каталогах этих модулей, tests/js, docs и
доступных .agents/.codex не найден. `rg` недоступен; использованы PowerShell reads.
`Get-Command node` не обнаружил Node в текущем sandbox/PATH. `node --check`
и targeted suite не запускались; PASS не заявляется. Для проверки нового кода
тестов нет, поскольку executable-файлы не изменялись.

Существующие working-tree изменения сохранены. Monitoring, discovery, history,
source health, premium.js/css и backend не изменялись. Не выполнялись сервер,
сеть, реальные API/БД, чтение секретов или .tmp-phase24*, builder, Docker,
установка пакетов, миграции, deployment или Git stage/commit/push/checkout/reset/clean.
