"""Honest, progressive workspace overview: no invented tenders or KPI values.

Built entirely on existing authenticated account/company context and the
already available UI counters. The browser navigation history is *navigation*
history only, never tender activity or persisted customer analytics.
"""

WORKSPACE_WORKBENCH_HTML = """
<section id="vqWorkbench" class="vq-workbench" data-page="overview" aria-labelledby="vqWorkbenchTitle">
  <div class="vq-workbench-heading">
    <div>
      <span class="vq-workbench-eyebrow" data-ui-en="YOUR PROCUREMENT WORKSPACE" data-ui-ru="ВАША РАБОЧАЯ ОБЛАСТЬ">YOUR PROCUREMENT WORKSPACE</span>
      <h2 id="vqWorkbenchTitle" data-ui-en="Your command overview" data-ui-ru="Центр управления закупками">Your command overview</h2>
      <p data-ui-en="Actual account context and in-session actions — not estimates or sample market figures." data-ui-ru="Состояние настоящего аккаунта и действий текущей сессии — без придуманных показателей рынка.">Actual account context and in-session actions — not estimates or sample market figures.</p>
    </div>
    <div class="vq-workbench-state"><span aria-hidden="true">●</span><span id="vqWorkbenchState" role="status" aria-live="polite" data-ui-en="Checking workspace…" data-ui-ru="Проверяем рабочую область…">Checking workspace…</span></div>
  </div>

  <div class="vq-workbench-kpis" aria-label="Verified workspace snapshot">
    <article><span class="vq-workbench-symbol blue" aria-hidden="true">◈</span><small data-ui-en="Organization" data-ui-ru="Организация">Organization</small><strong id="vqWbOrg">—</strong><p data-ui-en="Your selected workspace" data-ui-ru="Выбранное рабочее пространство">Your selected workspace</p></article>
    <article><span class="vq-workbench-symbol purple" aria-hidden="true">▦</span><small data-ui-en="Company profile" data-ui-ru="Профиль компании">Company profile</small><strong id="vqWbCompany">—</strong><p data-ui-en="Active search context" data-ui-ru="Активный профиль поиска">Active search context</p></article>
    <article><span class="vq-workbench-symbol teal" aria-hidden="true">⌕</span><small data-ui-en="Last browser search" data-ui-ru="Последний поиск в браузере">Last browser search</small><strong id="vqWbDiscovered">—</strong><p data-ui-en="Returned rows, only after a search" data-ui-ru="Полученные записи, только после поиска">Returned rows, only after a search</p></article>
    <article><span class="vq-workbench-symbol gold" aria-hidden="true">◇</span><small data-ui-en="Saved opportunities" data-ui-ru="Сохранённые закупки">Saved opportunities</small><strong id="vqWbSaved">—</strong><p data-ui-en="Last loaded company scope" data-ui-ru="Последняя загруженная выборка компании">Last loaded company scope</p></article>
  </div>

  <div class="vq-workbench-content">
    <article class="vq-progress-panel" aria-labelledby="vqProgressTitle">
      <div class="vq-panel-title-row"><div><span class="vq-panel-kicker" data-ui-en="GETTING STARTED" data-ui-ru="НАСТРОЙКА">GETTING STARTED</span><h3 id="vqProgressTitle" data-ui-en="Your setup progress" data-ui-ru="Готовность к работе">Your setup progress</h3></div><strong id="vqProgressCount" aria-live="polite">—</strong></div>
      <div class="vq-progress-track" role="progressbar" aria-label="Verified setup tasks completed" aria-valuemin="0" aria-valuemax="3" aria-valuenow="0"><div id="vqProgressFill"></div></div>
      <div id="vqProgressSteps" class="vq-progress-steps">
        <a href="#team" id="vqStepOrg"><span class="vq-step-status" aria-hidden="true">○</span><span><strong data-ui-en="Shared organization" data-ui-ru="Общая организация">Shared organization</strong><small data-ui-en="Required for discovery workflows" data-ui-ru="Нужна для поиска закупок">Required for discovery workflows</small></span><span aria-hidden="true">↗</span></a>
        <a href="#companies" id="vqStepCompany"><span class="vq-step-status" aria-hidden="true">○</span><span><strong data-ui-en="Active company profile" data-ui-ru="Активный профиль компании">Active company profile</strong><small data-ui-en="Required for matching" data-ui-ru="Нужен для подбора закупок">Required for matching</small></span><span aria-hidden="true">↗</span></a>
        <a href="#discover" id="vqStepSearch"><span class="vq-step-status" aria-hidden="true">○</span><span><strong data-ui-en="Discovery attempted" data-ui-ru="Попытка поиска">Discovery attempted</strong><small data-ui-en="A search attempt is not proof that sources work" data-ui-ru="Попытка не подтверждает работоспособность источников">A search attempt is not proof that sources work</small></span><span aria-hidden="true">↗</span></a>
      </div>
    </article>

    <article class="vq-next-panel" aria-labelledby="vqNextTitle">
      <span class="vq-panel-kicker" data-ui-en="NEXT BEST ACTION" data-ui-ru="СЛЕДУЮЩИЙ ШАГ">NEXT BEST ACTION</span>
      <span class="vq-next-graphic" aria-hidden="true">✦</span>
      <h3 id="vqNextTitle" data-ui-en="Make the next move" data-ui-ru="Продолжите работу">Make the next move</h3>
      <p id="vqNextText" role="status" aria-live="polite" data-ui-en="Checking your verified account and company setup." data-ui-ru="Проверяем состояние аккаунта и настройку компании.">Checking your verified account and company setup.</p>
      <a id="vqNextLink" href="#team" data-ui-en="Open team setup →" data-ui-ru="Открыть настройку команды →">Open team setup →</a>
      <div class="vq-source-check" id="vqSourceCheck" aria-labelledby="vqSourceCheckTitle" hidden>
        <div class="vq-source-check-head"><strong id="vqSourceCheckTitle" data-ui-en="Latest Discovery · source response" data-ui-ru="Последний поиск · ответы источников">Latest Discovery · source response</strong><span data-ui-en="THIS SESSION" data-ui-ru="ЭТА СЕССИЯ">THIS SESSION</span></div>
        <div id="vqSourceCheckRows" class="vq-source-check-bars" role="img" aria-label="Sources requested, responding and unavailable in latest Discovery"></div>
        <p data-ui-en="Requested sources are not proof of working integrations. Based only on the last browser search." data-ui-ru="Запрошенные источники не означают подтверждённую интеграцию. Только результат последнего поиска в браузере.">Requested sources are not proof of working integrations. Based only on the last browser search.</p>
      </div>
      <div class="vq-next-disclaimer" data-ui-en="No scans, alerts or AI tasks run automatically from this panel." data-ui-ru="Эта панель не запускает сканирование, уведомления или ИИ автоматически.">No scans, alerts or AI tasks run automatically from this panel.</div>
    </article>

    <article class="vq-nav-workbench" aria-labelledby="vqFavTitle">
      <div class="vq-panel-title-row"><div><span class="vq-panel-kicker" data-ui-en="YOUR SHORTCUTS" data-ui-ru="ВАШИ ССЫЛКИ">YOUR SHORTCUTS</span><h3 id="vqFavTitle" data-ui-en="Pinned destinations" data-ui-ru="Закреплённые разделы">Pinned destinations</h3></div><span class="vq-small-icon" aria-hidden="true">☆</span></div>
      <div id="vqPinnedPages" class="vq-pinned-pages" aria-label="Pinned workspace pages"></div>
      <div class="vq-workbench-divider"></div>
      <div class="vq-panel-title-row"><h3 data-ui-en="Recently opened pages" data-ui-ru="Недавно открытые разделы">Recently opened pages</h3><span class="vq-small-icon" aria-hidden="true">↗</span></div>
      <div id="vqRecentPages" class="vq-recent-pages" aria-label="Pages visited on this browser"></div>
      <p class="vq-workbench-local" data-ui-en="Only page navigation is saved in this browser. No tender details are collected." data-ui-ru="Сохраняются только названия посещённых разделов в этом браузере. Данные закупок не собираются.">Only page navigation is saved in this browser. No tender details are collected.</p>
    </article>
  </div>
</section>

<div id="vqUtilityBar" class="vq-utility-bar">
  <div class="vq-utility-breadcrumb"><span aria-hidden="true">⌂</span><span data-ui-en="Workspace" data-ui-ru="Рабочая область">Workspace</span><span aria-hidden="true">/</span><strong id="vqCurrentSection">Overview</strong></div>
  <div class="vq-utility-actions">
    <button type="button" id="vqPinCurrent" aria-pressed="false" aria-label="Pin this page">☆ <span id="vqPinLabel">Pin page</span></button>
    <button type="button" id="vqShortcutHelp" aria-label="Keyboard shortcut help"><span aria-hidden="true">⌨</span> <span data-ui-en="Shortcuts" data-ui-ru="Клавиши">Shortcuts</span></button>
  </div>
</div>

<dialog id="vqShortcutDialog" class="vq-shortcut-dialog" aria-labelledby="vqShortcutTitle">
  <div class="vq-dialog-head"><div><span class="vq-panel-kicker" data-ui-en="WORK FASTER" data-ui-ru="РАБОТАЙТЕ БЫСТРЕЕ">WORK FASTER</span><h2 id="vqShortcutTitle" data-ui-en="Keyboard shortcuts" data-ui-ru="Горячие клавиши">Keyboard shortcuts</h2></div><button id="vqShortcutClose" type="button" aria-label="Close keyboard shortcuts">✕</button></div>
  <div class="vq-shortcut-pair"><span data-ui-en="Open page navigation" data-ui-ru="Открыть меню переходов">Open page navigation</span><kbd>Ctrl K</kbd></div>
  <div class="vq-shortcut-pair"><span data-ui-en="Show this shortcut guide" data-ui-ru="Открыть подсказки">Show this shortcut guide</span><kbd>?</kbd></div>
  <div class="vq-shortcut-pair"><span data-ui-en="Close this guide or menu" data-ui-ru="Закрыть подсказки или меню">Close this guide or menu</span><kbd>Esc</kbd></div>
  <p data-ui-en="Shortcuts are disabled while typing in fields. This is page navigation only." data-ui-ru="Горячие клавиши не мешают вводу текста и управляют только интерфейсом.">Shortcuts are disabled while typing in fields. This is page navigation only.</p>
</dialog>
"""


# The utility row is global, while the workbench is Overview-only.
# Splitting at the declared static element keeps the markup in one source.
WORKSPACE_HOME_HTML, _utility_tail = WORKSPACE_WORKBENCH_HTML.split(
    '\n<div id="vqUtilityBar"', 1
)
WORKSPACE_UTILITIES_HTML = '<div id="vqUtilityBar"' + _utility_tail
