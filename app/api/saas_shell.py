"""Extend the existing authenticated dashboard without duplicating its services."""

from .discovery_ui import DISCOVERY_HTML
from .history_ui import HISTORY_HTML
from .saved_ui import SAVED_HTML
from .support_ui import SUPPORT_HTML


PAGES = [
    "Overview",
    "Discover",
    "Search History",
    "Recommended",
    "Saved",
    "Monitoring",
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
        ],
        "Intelligence": [
            "Monitoring",
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
'''

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

<section
  class="overview-metrics"
  data-page="overview"
  aria-label="Latest browser discovery"
>
  <article>
    <small>
      Opportunities found
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
      Metadata scored
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

<section
  class="discovery-prompt p"
  data-page="overview"
>
  <div>
    <h2>
      Your next review starts here.
    </h2>

    <p>
      No automatic saving or hidden background searches.
      Run discovery when you are ready.
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
    Coming in the next phase.
    This feature is not available yet.
  </p>
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

    context = context.replace(
        placeholder,
        DISCOVERY_HTML,
    )

    context = context.replace(
        '<section\n  id="futurePage"',
        HISTORY_HTML
        + "\n"
        + SAVED_HTML
        + "\n"
        + SUPPORT_HTML
        + '\n<section\n  id="futurePage"',
        1,
    )

    html = html.replace(
        "</head>",
        '<link rel="stylesheet" href="/assets/saas.css">'
        '<link rel="stylesheet" href="/assets/premium.css?v=phase24-precheckpoint-20261006">''<link rel="stylesheet" href="/assets/support.css">'
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
      ?
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
        '<script src="/assets/shell.js?v=phase24-saved-ui-v1-20261006"></script>'
        '<script src="/assets/premium.js?v=phase24-precheckpoint-20261006"></script>'
        '<script src="/assets/support.js"></script>'
        '<script src="/assets/discovery.js?v=phase24-saved-sync-v1-20261006"></script>'
        '<script src="/assets/history.js?v=phase24-search-history-v2-20261006"></script>'
        '<script src="/assets/saved.js?v=phase24-saved-ui-v1-20261006"></script>'
        "</body>",
    )

    return html
