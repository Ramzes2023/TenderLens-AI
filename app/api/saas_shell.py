"""Extend the existing authenticated dashboard without duplicating its services."""

from .command_center_ui import COMMAND_CENTER_HTML
from .discovery_ui import DISCOVERY_HTML
from .history_ui import HISTORY_HTML
from .saved_ui import SAVED_HTML
from .notifications_ui import DELIVERY_JOURNAL_HTML
from .planner_ui import PLANNER_HTML
from .workspace_home_panels import WORKSPACE_HOME_HTML, WORKSPACE_UTILITIES_HTML
from .source_health_ui import SOURCE_HEALTH_HTML
from .support_ui import SUPPORT_HTML


PAGES = [
    "Overview",
    "Discover",
    "Search History",
    "Recommended",
    "Saved",
    "Tender Planner",
    "Geography",
    "Monitoring",
    "Source Health",
    "AI Analysis",
    "Documents",
    "Companies",
    "Notifications",
    "Team",
    "Billing",
    "Support",
    "Settings",
]


def shell_html(html: str) -> str:
    groups = {
        "Workspace": [
            "Overview",
            "Discover",
            "Search History",
            "Recommended",
            "Saved",
            "Tender Planner",
        ],
        "Intelligence": [
            "Geography",
            "Monitoring",
            "Source Health",
            "AI Analysis",
            "Documents",
            "Notifications",
        ],
        "Organization": [
            "Companies",
            "Team",
            "Billing",
        ],
        "System": [
            "Support",
            "Settings",
        ],
    }

    icon_paths = [
        "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
        "M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14 M15 15l6 6",
        "M4 5h16v14H4z M8 9h8 M8 13h5",
        "M6 3h12v18l-6-4-6 4z",
    ]

    nav = ""

    for group, labels in groups.items():
        nav += (
            '<div class="nav-group">'
            f'<span class="nav-group-label">{group}</span>'
        )

        for index, label in enumerate(labels):
            key = label.lower().replace(" ", "-")
            path = icon_paths[index % len(icon_paths)]

            nav += (
                f'<a href="#{key}" data-nav="{key}">'
                '<svg viewBox="0 0 24 24" aria-hidden="true">'
                f'<path d="{path}"/>'
                "</svg>"
                f"<span>{label}</span>"
                "</a>"
            )

        nav += "</div>"

    shell = f'''
<a class="skip-link" href="#pageHeading">
  Skip to content
</a>

<button
  id="navToggle"
  class="nav-toggle"
  aria-controls="appNav"
  aria-expanded="false"
>
  Menu
</button>

<aside id="appNav" class="app-nav">
  <a class="brand" href="/">
    VALYQON<span> AI</span>
  </a>

  <p class="fine">
    Find. Analyze. Score. Win.
  </p>
  <button id="vqSidebarCompact" class="vq-sidebar-compact" type="button"
    aria-label="Collapse sidebar" title="Collapse sidebar" aria-pressed="false">
    <span aria-hidden="true">⇤</span><span class="vq-compact-caption">Compact menu</span>
  </button>

  <nav aria-label="Main navigation">
    {nav}
  </nav>

  <div class="sidebar-context">
    <small>ACTIVE COMPANY</small>
    <strong id="sideCompany">
      Choose a company
    </strong>
    <a href="#support">
      Help &amp; support
    </a>
  </div>
</aside>
'''

    top = '''
<header class="product-topbar">
  <div class="product-heading">
    <span class="eyebrow">
      PROCUREMENT WORKSPACE
    </span>

    <h1 id="pageHeading" tabindex="-1">
      Overview
    </h1>

    <p class="product-subtitle">
      Global Procurement Intelligence powered by AI
    </p>
  </div>

  <button
    id="openCommands"
    class="command-trigger"
    type="button"
    aria-label="Open workspace navigation"
  >
    Go to workspace...
    <kbd>Ctrl K</kbd>
  </button>

  <div class="toolbar">
    <label class="shell-language" for="shellLocale">
      <span id="shellLocaleLabel">Language</span>
      <select id="shellLocale" aria-describedby="shellLocaleScope">
        <option value="en">English</option>
        <option value="ru">Русский</option>
      </select>
    </label>
    <a
      class="notification-link"
      href="#notifications"
    >
      Notifications
    </a>

    <details class="account-menu">
      <summary>Account</summary>

      <div>
        <span id="email">
          Loading account...
        </span>

        <a href="#settings">
          Workspace settings
        </a>

        <a href="/docs">
          API documentation
        </a>

        <button
          type="button"
          onclick="refreshAll()"
        >
          Refresh workspace
        </button>

        <button
          type="button"
          onclick="logout()"
        >
          Sign out
        </button>
      </div>
    </details>
  </div>
</header>
<nav class="vq-workspace-shortcuts" aria-label="Quick workspace destinations">
  <span class="vq-shortcut-caption">QUICK ACCESS</span>
  <a href="#discover"><span aria-hidden="true">⌕</span><span data-ui-en="Find tenders" data-ui-ru="Найти закупки">Find tenders</span></a>
  <a href="#tender-planner"><span aria-hidden="true">▣</span><span data-ui-en="Planner" data-ui-ru="Планировщик">Planner</span></a>
  <a href="#saved"><span aria-hidden="true">◇</span><span data-ui-en="Saved" data-ui-ru="Сохранённые">Saved</span></a>
  <a href="#monitoring"><span aria-hidden="true">◉</span><span data-ui-en="Monitoring" data-ui-ru="Мониторинг">Monitoring</span></a>
  <a href="#source-health"><span aria-hidden="true">▥</span><span data-ui-en="Sources" data-ui-ru="Источники">Sources</span></a>
  <a href="#team"><span aria-hidden="true">♧</span><span data-ui-en="Team" data-ui-ru="Команда">Team</span></a>
</nav>
{WORKSPACE_UTILITIES_HTML}
<p id="shellLocaleScope" class="shell-locale-scope" hidden>Navigation and account controls only. Monitoring Center, Source Health, other page content and workspace forms remain in English.</p>
'''

    top = top.replace("{WORKSPACE_UTILITIES_HTML}", WORKSPACE_UTILITIES_HTML)

    start = html.index('<div class="top">')
    end = html.index(
        '<section class="grid">',
        start,
    )

    html = html[:start] + top + "\n" + html[end:]

    context = '''
<section
  class="workspace-context"
  aria-label="Active workspace"
>
  <div id="orgControl"></div>

  <div>
    <span class="fine">
      Active company
    </span>

    <strong id="activeCompanyLabel">
      Loading workspace...
    </strong>

    <a href="#companies">
      Switch / manage company
    </a>
  </div>
</section>

<section
  class="overview-welcome"
  data-page="overview"
>
  <div>
    <span class="eyebrow">
      YOUR OPPORTUNITY LANDSCAPE
    </span>

    <h2>Welcome back.</h2>

    <p>
      Make your next procurement decision
      a considered one.
    </p>
  </div>

  <div class="toolbar">
    <a class="cta" href="#discover">
      Start discovery &rarr;
    </a>

    <a class="secondary" href="#companies">
      Manage company profile
    </a>
  </div>
</section>

<section class="vq-action-center" data-page="overview" aria-labelledby="vqActionHeading">
 <div class="vq-action-heading"><div><span class="vq-card-eyebrow">YOUR WORKSPACE</span><h2 id="vqActionHeading" data-ui-en="Pick up where you left off" data-ui-ru="Продолжите работу с закупками">Pick up where you left off</h2>
 <p data-ui-en="Direct access to the existing product workflows. Figures only appear after your workspace loads." data-ui-ru="Быстрый доступ к действующим функциям. Показатели появляются после загрузки рабочего пространства.">Direct access to the existing product workflows. Figures only appear after your workspace loads.</p></div>
 <button type="button" class="vq-action-command" id="vqActionCommand" aria-label="Open quick workspace navigation" data-ui-en="Quick navigation · Ctrl K" data-ui-ru="Быстрый переход · Ctrl K">Quick navigation · Ctrl K</button></div>
 <div class="vq-action-grid">
  <a class="vq-action-card" href="#discover"><span class="vq-action-glyph" aria-hidden="true">⌕</span><strong data-ui-en="Find opportunities" data-ui-ru="Поиск подходящих закупок">Find opportunities</strong><p data-ui-en="Explore procurement notices with your company context." data-ui-ru="Ищите закупки с учётом профиля компании.">Explore procurement notices with your company context.</p><small data-ui-en="Open discovery →" data-ui-ru="Открыть поиск →">Open discovery →</small></a>
  <a class="vq-action-card" href="#saved"><span class="vq-action-glyph" aria-hidden="true">◇</span><strong data-ui-en="Review saved work" data-ui-ru="Проверить сохранённое">Review saved work</strong><p data-ui-en="Continue your existing saved procurement review." data-ui-ru="Продолжайте работу с сохранёнными закупками.">Continue your existing saved procurement review.</p><small data-ui-en="Open saved →" data-ui-ru="Открыть сохранённое →">Open saved →</small></a>
  <a class="vq-action-card" href="#monitoring"><span class="vq-action-glyph" aria-hidden="true">◉</span><strong data-ui-en="Check monitoring" data-ui-ru="Проверить мониторинг">Check monitoring</strong><p data-ui-en="Review scan availability and your configured status." data-ui-ru="Проверьте сканирование и доступность источников.">Review scan availability and your configured status.</p><small data-ui-en="Open monitoring →" data-ui-ru="Открыть мониторинг →">Open monitoring →</small></a>
  <a class="vq-action-card" href="#team"><span class="vq-action-glyph" aria-hidden="true">♧</span><strong data-ui-en="Coordinate with your team" data-ui-ru="Работать с командой">Coordinate with your team</strong><p data-ui-en="Open verified organizations, roles and invitations." data-ui-ru="Управляйте организацией, ролями и приглашениями.">Open verified organizations, roles and invitations.</p><small data-ui-en="Open team →" data-ui-ru="Открыть команду →">Open team →</small></a>
 </div>
</section>
{WORKSPACE_HOME_HTML}
<section id="firstRunPreview" class="p" data-page="overview" hidden>
  <span class="eyebrow">YOUR FIRST MATCHING OPPORTUNITIES</span>
  <h2>Real tenders matched to your company</h2>
  <p>Actual procurement notices from enabled sources, never fabricated demo data.</p>
  <p id="firstRunStatus" role="status" aria-live="polite"></p>
  <div id="firstRunResults" aria-label="Company-matched live procurement results"></div>
  <a class="cta" href="#discover">Open all results in Discover</a>
</section>
<!-- COMMAND_CENTER -->
<details class="session-report" data-page="overview">
<summary>Latest browser search - operational row counters</summary>
<section
  class="session-metrics"
  aria-label="Latest browser search row counters, not unique analytics"
>
  <article>
    <small>
      Returned rows
    </small>

    <strong
      id="discoveredCount"
      class="metric"
    >
      Not run
    </strong>

    <span>
      Latest browser search
    </span>
  </article>

  <article>
    <small>
      Rows with preliminary fit
    </small>

    <strong
      id="scoredCount"
      class="metric"
    >
      Not run
    </strong>

    <span>
      Available preliminary fit
    </span>
  </article>

  <article>
    <small>
      Sources checked
    </small>

    <strong
      id="sourcesChecked"
      class="metric"
    >
      -
    </strong>

    <span>
      Attempted, not guaranteed available
    </span>
  </article>

  <article>
    <small>
      Last discovery
    </small>

    <strong
      id="lastDiscovery"
      class="metric metric-time"
    >
      Not run
    </strong>

    <span>
      This workspace session only
    </span>
  </article>
</section>
</details>

<section
  class="discovery-prompt p"
  data-page="overview"
>
  <div>
    <h2>
      Your next review starts here.
    </h2>

    <p>
      An initial company-matched search may run once when the company is activated.
      No results are automatically saved or submitted as bids.
    </p>
  </div>

  <a href="#discover">
    Find opportunities &rarr;
  </a>
</section>

<div
  id="appNotice"
  role="status"
  aria-live="polite"
></div>

<section
  id="onboarding"
  class="p"
  hidden
>
  <span class="eyebrow">
    SET UP YOUR WORKSPACE
  </span>

  <h2>
    A company profile brings opportunities into focus.
  </h2>

  <p>
    Create a company → Add products and search keywords → Discover opportunities.
    Global discovery requires a shared organization; create or select one in Team first.
  </p>

  <button
    id="onboardingStart"
    onclick="location.hash='companies';showCompanyForm()"
  >
    Create company
  </button>
</section>

<section
  id="discoveryWorkspace"
  class="p"
  data-page="discover"
  hidden
>
  <h2>
    Discover opportunities
  </h2>

  <p>
    Discovery workspace is being prepared.
  </p>
</section>

<section
  id="futurePage"
  class="p future-state"
  hidden
>
  <span class="neutral-pill">
    Planned workspace
  </span>

  <h2 id="futureTitle"></h2>

  <p id="futureText">
    This feature is not available yet.
  </p>
  <a id="futureNext" hidden></a>
</section>
'''

    placeholder = '''
<section
  id="discoveryWorkspace"
  class="p"
  data-page="discover"
  hidden
>
  <h2>
    Discover opportunities
  </h2>

  <p>
    Discovery workspace is being prepared.
  </p>
</section>
'''

    context = '''
<section id="documentIntelligence" class="p document-intelligence" data-page="ai-analysis" hidden>
  <span class="eyebrow" data-ui-en="DOCUMENT INTELLIGENCE" data-ui-ru="АНАЛИЗ ДОКУМЕНТОВ">DOCUMENT INTELLIGENCE</span>
  <h2 data-ui-en="Turn PDF evidence into a reviewed decision" data-ui-ru="От PDF к проверенному решению">Turn PDF evidence into a reviewed decision</h2>
  <p data-ui-en="Use the active company and existing workflows. Every profile change needs your approval." data-ui-ru="Используйте активную компанию и существующие сценарии. Изменения профиля требуют вашего подтверждения.">Use the active company and existing workflows. Every profile change needs your approval.</p>
  <div class="document-workflows">
    <article>
      <span class="neutral-pill" data-ui-en="01 · PDF → Profile" data-ui-ru="01 · PDF → Профиль">01 · PDF → Profile</span>
      <h3 data-ui-en="Company catalog" data-ui-ru="Каталог компании">Company catalog</h3>
      <p data-ui-en="Review proposed products, keywords, markets and certificates, then explicitly apply. Identity, currency, budget, exclusions and hard stops are preserved. No automatic scans." data-ui-ru="Проверьте предложения по продуктам, ключевым словам, рынкам и сертификатам, затем примените явно. Идентификация, валюта, бюджет, исключения и ограничения сохраняются. Автоматических сканирований нет.">Review proposed products, keywords, markets and certificates, then explicitly apply. Identity, currency, budget, exclusions and hard stops are preserved. No automatic scans.</p>
      <button id="openCompanyPdf" type="button" disabled data-ui-en="Open company PDF assistant" data-ui-ru="Открыть PDF-помощник компании">Open company PDF assistant</button>
      <p id="companyPdfHubGate" class="fine" role="status"></p>
    </article>
    <article>
      <span class="neutral-pill" data-ui-en="02 · PDF → Analysis" data-ui-ru="02 · PDF → Анализ">02 · PDF → Analysis</span>
      <h3 data-ui-en="Tender document" data-ui-ru="Тендерный документ">Tender document</h3>
      <p data-ui-en="Open an opportunity in Discover or Saved, then use its Full AI analysis PDF upload. Extract facts, score against the active company and retain analysis history." data-ui-ru="Откройте карточку в Поиске или Сохранённом и загрузите PDF через полный ИИ-анализ. Извлеките факты, оцените соответствие активной компании и сохраните историю анализа.">Open an opportunity in Discover or Saved, then use its Full AI analysis PDF upload. Extract facts, score against the active company and retain analysis history.</p>
      <a class="cta" href="#discover" data-ui-en="Open Discover" data-ui-ru="Открыть поиск">Open Discover</a>
      <a class="secondary" href="#saved" data-ui-en="Open Saved" data-ui-ru="Открыть сохранённое">Open Saved</a>
      <a href="#documents" data-ui-en="View analyzed documents" data-ui-ru="Просмотреть анализ документов">View analyzed documents</a>
    </article>
    <article>
      <span class="neutral-pill">03 · PDF → RAG</span>
      <h3 data-ui-en="Ask with citations" data-ui-ru="Вопросы со ссылками">Ask with citations</h3>
      <p data-ui-en="Upload a PDF for the active company, check ingestion status, then ask with page citations. Processing requires configured services and a running worker. Answers require an AI provider." data-ui-ru="Загрузите PDF для активной компании, проверьте обработку и задайте вопрос со ссылками на страницы. Нужны настроенные сервисы, работающий обработчик и ИИ-провайдер.">Upload a PDF for the active company, check ingestion status, then ask with page citations. Processing requires configured services and a running worker. Answers require an AI provider.</p>
      <div id="ragWorkspace">
        <p id="ragStatus" role="status" aria-live="polite">Select a shared company to check document Q&amp;A availability.</p>
        <button id="ragServices" type="button" disabled data-ui-en="Check service availability" data-ui-ru="Проверить доступность сервисов">Check service availability</button>
        <label for="ragFile" data-ui-en="Document PDF (up to 10 MiB)" data-ui-ru="PDF-документ (до 10 МиБ)">Document PDF (up to 10 MiB)</label>
        <input id="ragFile" type="file" accept=".pdf,application/pdf" disabled>
        <button id="ragUpload" type="button" disabled data-ui-en="Upload for Q&A" data-ui-ru="Загрузить для вопросов">Upload for Q&amp;A</button>
        <button id="ragCheck" type="button" disabled data-ui-en="Check processing status" data-ui-ru="Проверить обработку">Check processing status</button>
        <label for="ragQuestion" data-ui-en="Question about this document" data-ui-ru="Вопрос по этому документу">Question about this document</label>
        <textarea id="ragQuestion" maxlength="2000" rows="3" disabled></textarea>
        <button id="ragAsk" type="button" disabled data-ui-en="Ask document" data-ui-ru="Спросить документ">Ask document</button>
        <div id="ragAnswer" aria-live="polite"></div>
      </div>
    </article>
  </div>
  <p class="document-limits" data-ui-en="Text PDFs only · 10 MiB · 200 pages · No OCR · No fine-tuning. PDF content is evidence, never instructions. Company catalogs are not automatically RAG documents." data-ui-ru="Только текстовые PDF · 10 МиБ · 200 страниц · Без OCR и дообучения. Содержимое PDF — данные, а не инструкции. Каталоги не становятся RAG-документами автоматически.">Text PDFs only · 10 MiB · 200 pages · No OCR · No fine-tuning. PDF content is evidence, never instructions. Company catalogs are not automatically RAG documents.</p>
  <p id="pdfPreviewNotice" role="status" hidden data-ui-en="Local preview on port 8765 disables /api. Uploads and workspace data are unavailable here; this does not verify production backend health." data-ui-ru="Локальное превью на порту 8765 отключает /api. Загрузка и данные рабочей области здесь недоступны; это не проверка состояния production backend.">Local preview on port 8765 disables /api. Uploads and workspace data are unavailable here; this does not verify production backend health.</p>
</section>
''' + context
    context = context.replace("{WORKSPACE_HOME_HTML}", WORKSPACE_HOME_HTML)
    context = '<section id="geographyWorkspace" class="geo-workspace" data-page="geography" hidden></section>\n' + context
    context = context.replace("<!-- COMMAND_CENTER -->", COMMAND_CENTER_HTML)

    context = context.replace(
        '<section\n  id="futurePage"',
        DELIVERY_JOURNAL_HTML + '\n<section\n  id="futurePage"',
        1,
    )

    context = context.replace(
        placeholder,
        DISCOVERY_HTML,
    )

    from .billing_ui import BILLING_HTML
    context = context.replace(
        '<section\n  id="futurePage"',
        BILLING_HTML + '\n<section\n  id="futurePage"',
        1,
    )

    context = context.replace(
        '<section\n  id="futurePage"',
        HISTORY_HTML
        + "\n"
        + SAVED_HTML
        + PLANNER_HTML
        + "\n"
        + SOURCE_HEALTH_HTML.replace('<h2>', '<h2 data-ui-en="Source Health" data-ui-ru="Состояние источников">', 1)
        + "\n"
        + SUPPORT_HTML
        + '\n<section\n  id="futurePage"',
        1,
    )

    html = html.replace(
        "</head>",
        '<link rel="stylesheet" href="/assets/geography.css?v=20261013">'
        '<link rel="stylesheet" href="/assets/saas.css">'
        '<link rel="stylesheet" href="/assets/premium.css?v=phase24-visual-20261012&main_i18n=2">''<link rel="stylesheet" href="/assets/support.css?v=thread-dark-20261017">'
        '<link rel="stylesheet" href="/assets/rag.css?v=pilot1">'
        '<link rel="stylesheet" href="/assets/workspace_luxe.css?v=20261023c">''<link rel="stylesheet" href="/assets/workspace_home.css?v=20261023a"><link rel="stylesheet" href="/assets/planner.css?v=20261023a"><link rel="stylesheet" href="/assets/delivery_journal.css?v=20261024a"><link rel="stylesheet" href="/assets/tender_team.css?v=20261023a">'
        '<link rel="stylesheet" href="/assets/responsive.css?v=phase24q">'
        "</head>",
    )

    html = html.replace(
        "<body>",
        '<body class="saas">'
        "<noscript>"
        "This workspace needs JavaScript enabled. "
        "Your data has not been changed."
        "</noscript>"
        + shell,
    )

    html = html.replace(
        '<section class="grid">',
        context
        + '<section class="grid" id="existingWorkspace">',
        1,
    )

    html = html.replace(
        "AI Procurement Intelligence Platform",
        "Global Procurement Intelligence powered by AI",
    )

    html = html.replace(
        "Existing personal company and tender cards remain unchanged in this checkpoint.",
        "Select a workspace before managing its companies or opportunities.",
    )

    html = html.replace(
        "</main>",
        '''</main>

<button
  id="globalSupportLauncher"
  class="global-support-launcher"
  type="button"
  aria-label="Open VALYQON Support"
  title="VALYQON Support"
>
  ?
  <span>Support</span>
</button>

<div
  id="globalSupportPanel"
  class="global-support-panel"
  hidden
>
  <div class="global-support-panel-head">
    <div>
      <strong>VALYQON Support</strong>
      <span>
        Product guidance &amp; support requests
      </span>
    </div>

    <button
      id="globalSupportClose"
      type="button"
      aria-label="Close support"
    >
      &times;
    </button>
  </div>

  <div class="global-support-panel-body">
    <p>
      Need help with discovery, company matching,
      monitoring or your account?
    </p>

    <a
      class="global-support-primary"
      href="#support"
    >
      Open Support Center
    </a>

    <a
      id="globalReportProblem"
      href="#support"
      class="global-support-secondary"
    >
      Report a problem
    </a>
  </div>
</div>

<dialog
  id="commandPalette"
  aria-labelledby="commandTitle"
>
  <h2 id="commandTitle">
    Go to workspace
  </h2>

  <p>
    Navigation only - this does not search tenders or buyers.
  </p>

  <label for="commandQuery">
    Find a page
  </label>

  <input
    id="commandQuery"
    type="search"
    autocomplete="off"
  >

  <div id="commandResults"></div>

  <button
    id="closeCommands"
    type="button"
  >
    Close
  </button>
</dialog>''',
    )

    html = html.replace(
        "</body>",
        '<script src="/assets/shell.js?v=ui-fix-20261013"></script>'
        '<script src="/assets/premium.js?v=ui-fix-20261013"></script>'
        '<script src="/assets/support.js?v=phase24r"></script>'
        '<script src="/assets/discovery.js?v=phase24-customer-onepass&intl=20261014"></script>'
        '<script src="/assets/first_run.js?v=launch-20261017"></script>'
        '<script src="/assets/history.js?v=ui-fix-20261013"></script>'
        '<script src="/assets/saved.js?v=phase24r"></script>'
        '<script src="/assets/billing.js?v=pilot-20261017"></script>'
        '<script src="/assets/source_health.js?v=ui-fix-20261013&intl=20261014"></script>'
        '<script src="/assets/rag.js?v=pilot1"></script>'
        '<script src="/assets/locale.js?v=ui-fix-20261013"></script>'
        '<script src="/assets/workspace_locale.js?v=20261013"></script>'
        '<script src="/assets/workspace_ux.js?v=20261013"></script>'
        '<script src="/assets/geography_fallback.js?v=1"></script>'
        '<script src="/assets/geography.js?v=3"></script>'
        '<script src="/assets/workspace_luxe.js?v=20261023b"></script>''<script src="/assets/workspace_home.js?v=20261023a"></script><script src="/assets/planner.js?v=20261023a"></script><script src="/assets/delivery_journal.js?v=20261024a"></script><script src="/assets/delivery_preferences.js?v=20261024a"></script><script src="/assets/tender_team.js?v=20261023a"></script><script src="/assets/source_history.js?v=20261023a"></script>'
        "</body>",
    )

    return html
