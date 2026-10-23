"""Tender Planner: authenticated views of existing saved and team workflow data.

No new routes or permissions. Official bid submission is never performed here.
"""

PLANNER_HTML = """
<section id="plannerWorkspace" class="vq-planner" data-page="tender-planner" hidden aria-labelledby="vqPlannerTitle">
  <div class="vq-planner-hero">
    <div><span class="vq-planner-eyebrow" data-ui-en="VALYQON PROCUREMENT OPERATIONS" data-ui-ru="УПРАВЛЕНИЕ ЗАКУПКАМИ VALYQON">VALYQON PROCUREMENT OPERATIONS</span>
      <h2 id="vqPlannerTitle" data-ui-en="Tender Planner" data-ui-ru="Планировщик тендеров">Tender Planner</h2>
      <p data-ui-en="Manage genuine saved notices, internal participation stages and application deadlines in one place." data-ui-ru="Управляйте сохранёнными закупками, внутренними этапами участия и сроками подачи заявок в одном месте.">Manage genuine saved notices, internal participation stages and application deadlines in one place.</p>
      <small data-ui-en="Internal team stages are not evidence of official submission, award or source status. Always verify deadlines at the original platform." data-ui-ru="Внутренние этапы не доказывают подачу заявки, победу или состояние площадки. Всегда проверяйте сроки на оригинальной площадке.">Internal team stages are not evidence of official submission, award or source status. Always verify deadlines at the original platform.</small>
    </div>
    <div class="vq-planner-actions"><button id="vqPlannerRefresh" type="button" data-ui-en="↻ Refresh saved" data-ui-ru="↻ Обновить сохранённое">↻ Refresh saved</button><button id="vqPlannerCalendarExport" type="button" disabled data-ui-en="↓ Calendar .ics" data-ui-ru="↓ Календарь .ics">↓ Calendar .ics</button></div>
  </div>
  <p id="vqPlannerStatus" class="vq-planner-status" role="status" aria-live="polite" data-ui-en="Open this section to load saved tenders." data-ui-ru="Откройте этот раздел, чтобы загрузить сохранённые закупки.">Open this section to load saved tenders.</p>
  <div class="vq-planner-stats">
    <article><span data-ui-en="Saved in view" data-ui-ru="Сохранено в выборке">Saved in view</span><strong id="vqPlannerTotal">—</strong></article>
    <article><span data-ui-en="Next 7 calendar days" data-ui-ru="Ближайшие 7 календарных дней">Next 7 calendar days</span><strong id="vqPlannerSoon">—</strong></article>
    <article><span data-ui-en="Past deadlines" data-ui-ru="Истекшие сроки">Past deadlines</span><strong id="vqPlannerLate">—</strong></article>
    <article><span data-ui-en="Without exact time" data-ui-ru="Без точного времени">Without exact time</span><strong id="vqPlannerDateOnly">—</strong></article>
  </div>
  <div class="vq-planner-toolbar">
    <div class="vq-planner-tabs" role="group" aria-label="Planner presentation">
      <button id="vqPlannerBoardTab" type="button" aria-pressed="true" data-ui-en="▦ Kanban board" data-ui-ru="▦ Доска этапов">▦ Kanban board</button>
      <button id="vqPlannerMonthTab" type="button" aria-pressed="false" data-ui-en="▣ Deadline calendar" data-ui-ru="▣ Календарь сроков">▣ Deadline calendar</button>
      <button id="vqPlannerBuyersTab" type="button" aria-pressed="false" data-ui-en="◈ Buyer insights" data-ui-ru="◈ Аналитика заказчиков">◈ Buyer insights</button>
    </div>
    <div class="vq-planner-toolbar-right">
      <label for="vqPlannerUrgency" data-ui-en="Deadline" data-ui-ru="Срок подачи">Deadline</label>
      <select id="vqPlannerUrgency" aria-label="Filter by deadline">
        <option value="all" data-ui-en="All deadlines" data-ui-ru="Все сроки">All deadlines</option>
        <option value="week" data-ui-en="Next 7 days" data-ui-ru="Ближайшие 7 дней">Next 7 days</option>
        <option value="late" data-ui-en="Past dates" data-ui-ru="Прошедшие даты">Past dates</option>
        <option value="date-only" data-ui-en="Date only" data-ui-ru="Только дата">Date only</option>
        <option value="unknown" data-ui-en="Unknown" data-ui-ru="Не указано">Unknown</option>
      </select>
      <label for="vqPlannerQuery" data-ui-en="Filter saved" data-ui-ru="Фильтр закупок">Filter saved</label>
      <input id="vqPlannerQuery" type="search" maxlength="120" autocomplete="off" placeholder="Title or tender number" data-ui-en-placeholder="Title or tender number" data-ui-ru-placeholder="Название или номер закупки">
    </div>
  </div>

  <div id="vqPlannerBoard" class="vq-planner-board" aria-label="Real saved opportunity stages"></div>
  <div id="vqPlannerCalendar" class="vq-planner-month" hidden>
    <div class="vq-month-header"><button id="vqMonthPrev" type="button" aria-label="Previous month">‹</button><h3 id="vqMonthTitle">—</h3><button id="vqMonthNext" type="button" aria-label="Next month">›</button></div>
    <div id="vqMonthGrid" class="vq-month-grid" aria-label="Saved procurement deadline dates"></div>
    <p data-ui-en="Date-only notices have no verified submission time. Invalid or timezone-ambiguous timestamps are excluded from the calendar. Download is manual; alerts are not scheduled from this page." data-ui-ru="Для извещений только с датой точное время подачи неизвестно. Недостоверные или неоднозначные даты не показываются. Скачивание вручную; напоминания здесь не создаются.">Date-only notices have no verified submission time. Invalid or timezone-ambiguous timestamps are excluded from the calendar. Download is manual; alerts are not scheduled from this page.</p>
  </div>
  <section id="vqPlannerBuyers" class="vq-planner-buyers" hidden aria-labelledby="vqBuyersHeading">
    <div class="vq-buyer-intro"><div><span class="vq-planner-eyebrow" data-ui-en="VERIFIABLE COMPANY CONTEXT" data-ui-ru="ДАННЫЕ ВАШЕЙ КОМПАНИИ">VERIFIABLE COMPANY CONTEXT</span><h3 id="vqBuyersHeading" data-ui-en="Buyer intelligence · your saved tenders" data-ui-ru="Аналитика заказчиков · ваши сохранённые закупки">Buyer intelligence · your saved tenders</h3><p data-ui-en="Counts reflect only the first 300 saved notices loaded for the active company, grouped by exact buyer name. No market coverage or legal-entity identity resolution is claimed." data-ui-ru="Подсчёт только по первым 300 сохранённым закупкам активной компании, группировка по точному имени заказчика. Это не охват всего рынка и не проверка юридических лиц.">Counts reflect only the first 300 saved notices loaded for the active company, grouped by exact buyer name. No market coverage or legal-entity identity resolution is claimed.</p></div><strong id="vqUniqueBuyers">—</strong></div>
    <div id="vqBuyerChart" class="vq-buyer-chart" aria-label="Observed buyer notice counts"></div>
    <div class="vq-competitor-notice"><span aria-hidden="true">i</span><p data-ui-en="Competitor intelligence requires official award and protocol evidence. VALYQON does not infer competitors or winners from search results or saved tenders." data-ui-ru="Для аналитики конкурентов нужны официальные протоколы и результаты торгов. VALYQON не угадывает конкурентов или победителей по результатам поиска.">Competitor intelligence requires official award and protocol evidence. VALYQON does not infer competitors or winners from search results or saved tenders.</p></div>
  </section>
  <div id="vqPlannerPagination" class="vq-planner-pagination"><span id="vqPlannerShown"></span><button id="vqPlannerMore" type="button" hidden data-ui-en="Load more saved notices" data-ui-ru="Загрузить ещё закупки">Load more saved notices</button></div>
</section>
"""
