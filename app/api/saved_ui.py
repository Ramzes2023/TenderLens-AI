"""Saved opportunities workspace markup."""

SAVED_HTML = """
<section
  id="savedWorkspace"
  class="p"
  data-page="saved"
  hidden
>
  <div class="toolbar">
    <div>
      <span class="eyebrow">
        COMPANY SHORTLIST
      </span>

      <h2>
        Saved opportunities
      </h2>

      <p>
        Opportunities saved from Discover for the active company.
        Switching company switches this shortlist as well.
      </p>
    </div>

    <button
      id="refreshSaved"
      type="button"
    >
      Refresh saved
    </button>
    <a id="exportSavedCsv" href="#saved" hidden>Export CSV</a>
    <a id="exportSavedXlsx" href="#saved" hidden>Export Excel</a>
  </div>

  <section class="p" id="savedDeadlineSettings" aria-label="Deadline notifications">
    <h3>Deadline reminders (48 hours before)</h3>
    <p>Available for saved tenders with an exact timezone-aware deadline.
       Enable explicitly; check dates at the official source.
       Telegram requires a connected account and an active Telegram subscription.</p>
    <label><input type="checkbox" id="deadlineEmailOptin"> Email reminders</label>
    <label><input type="checkbox" id="deadlineTelegramOptin"> Telegram reminders</label>
    <button id="saveDeadlinePreferences" type="button" disabled>Save reminder preferences</button>
    <p role="status" id="deadlinePreferencesStatus"></p>
  </section>

  <div class="overview-metrics">
    <article>
      <small>
        Saved opportunities
      </small>

      <strong
        id="savedCount"
        class="metric"
      >
        Not loaded
      </strong>

      <span>
        Active company shortlist
      </span>
    </article>
  </div>

  <p
    id="savedContext"
    class="muted"
  >
    Loading workspace...
  </p>

  <p
    id="savedMessage"
    role="status"
    aria-live="polite"
  >
    Open Saved to load the active company shortlist.
  </p>

  <div
    id="savedResults"
    aria-label="Saved opportunities"
  ></div>
</section>

<dialog
  id="savedDetail"
  aria-labelledby="savedDetailTitle"
>
  <div class="toolbar">
    <h2 id="savedDetailTitle">
      Saved opportunity
    </h2>

    <button
      id="closeSavedDetail"
      type="button"
      autofocus
    >
      Close detail
    </button>
  </div>

  <div id="savedDetailBody"></div>
</dialog>
"""
