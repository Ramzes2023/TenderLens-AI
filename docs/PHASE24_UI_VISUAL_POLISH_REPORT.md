# PHASE24 UI visual polish

## Review evidence

The user supplied findings from a real local 8765/dashboard browser screenshot:
Overview was dark; AI Analysis, Discover, Monitoring and Source Health were light.
The three dark Document Intelligence cards had dark navy headings/descriptions.
AI Analysis also displayed an old white Planned workspace placeholder.
The language label wrapped awkwardly; an early translation announcement was intrusive.
The workspace select displayed Loading. Port 8765 intentionally disables /api.
These findings are supplied evidence, not a new browser review performed here.

## Inspection and changes

CSS order is embedded dashboard styles, geography.css, saas.css, premium.css,
support.css, responsive.css. saas.css sets light shell defaults; premium.css
contains both light defaults and conditional command-view dark rules. Hub dark
card backgrounds were unconditional, while readable text depended on the page
class. Existing source already excluded AI Analysis from the future-page table;
the reported duplicate is inconsistent with that current router. Older asset
cache versions were present. A stale preview/cache is a possible explanation,
not proven by a new browser capture.

Added explicit scoped hub colors after premium light defaults for headings,
paragraphs, help, badges, anchors, focus and disabled buttons. Disabled buttons
use solid readable colors instead of fading their content. Existing gate text
and RAG worker/UI limitation explanation remain intact.

Added an explicit AI Analysis future-page exclusion, removed its leftover next
link mapping, and versioned changed CSS/JS assets to request fresh files. There
is one AI Analysis data-page section. Legacy PDF controls and their handlers
remain intact. Company PDF navigation still checks shared workspace, write
permission and an existing active company. Preview then explicit apply remains
the contract. No autoapply, autoscan or new backend workflow was added.

Discover, Saved, Search History and Recommended now reuse the existing dark
shell mode. Scoped operational surfaces include inputs, placeholders, tender
cards, metadata, errors, notices and disabled controls. Geography is excluded
from this shell-mode expansion; its map, data and handlers were not edited.
Existing desktop/sidebar and responsive menu behavior was preserved.

Language uses concise Language / Russian equivalent labels, without wrapping
inside the control. The early scope announcement is hidden but retained as the
language control's accessible description. It does not claim full translation.
Company profile and tender analysis badges are bilingual. Workspace-unavailable
sidebar and initial API failure messages are locale-aware through textContent.
The initial Loading organization option becomes unavailable only when it is
the sole loading option after failure; real API options are not translated.
Locale behavior still changes presentation only and retains existing storage,
company context, dropdown handlers and business events.

Local PDF preview notice remains conditional on port 8765. No backend health,
real scan, AI result or metric was verified from this preview.

## Files changed in this implementation

- app/api/dashboard.py
- app/api/saas_shell.py
- app/api/static/premium.css
- app/api/static/locale.js
- app/api/static/shell.js
- tests/js/main_ui_consistency.test.cjs
- tests/js/main_pdf_ai_visual.test.cjs
- docs/PHASE24_UI_VISUAL_POLISH_REPORT.md

Existing uncommitted work was retained. Git diff totals include prior changes
and must not be interpreted as this implementation's standalone diff.

## Verification

Local PowerShell source checks passed: one AI Analysis section and explicit
future-page exclusion. WCAG luminance calculations for actual selected colors:
heading/card 15.68:1, body/card 10.45:1, link/card 11.07:1,
badge 7.45:1, disabled CTA 7.54:1, primary CTA 6.31:1.
These are static color checks, not browser-computed style verification.

Added main_pdf_ai_visual.test.cjs to resolve actual scoped CSS declarations and
variables, check contrast, focus, disabled RAG, coherent routing, labels, asset
versions and exclusion of map selectors. It also executes the existing PDF UX
and UI consistency suites. Updated the consistency suite's expected dark-page
list without weakening its locale/context invariants.

Node and Python were absent from PATH and checked standard local locations.
JS suites were not executed here. Required host commands:

    node tests/js/main_pdf_ai_visual.test.cjs
    node tests/js/main_pdf_ai_ux.test.cjs
    node tests/js/main_ui_consistency.test.cjs
    node tests/js/main_geography.test.cjs
    node tests/js/main_i18n.test.cjs

Geography and main_i18n tests were not edited and were not run locally.
No network, API, database, install, production or browser session was started.

## Manual browser review TODO and blockers

- Refresh the local preview with the new asset versions; confirm all three
  cards have readable computed colors and only the hub appears in AI Analysis.
- Review EN/RU at 1440, 1280, 1024 and phone widths. Check menu visibility,
  keyboard focus, disabled help text, inputs, errors and Account actions.
- Confirm preview shows unavailable workspace instead of indefinite Loading,
  and switching locale preserves organization/company without writes/refetch.
- Confirm the 176 Geography outlines, selection and interaction still work.
- In an authorized backend environment later, check company permissions and
  review-before-apply, plus existing tender upload navigation. Not verified here.

P3.9 safety gate remains BLOCKED. RAG worker/UI wiring remains unavailable;
RAG CTA stays disabled. No production readiness claim is made.
