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

  <section id="savedTeamAudit" class="p" aria-label="Team activity">
    <h3>Recent company activity</h3>
    <p>Read-only for organization owners and admins. Includes who saved or removed
       tenders and who generated an export. Internal activity is not proof of an
       official tender action or that the file was downloaded.</p>
    <button id="refreshSavedActivity" type="button">Refresh activity</button>
    <p id="savedActivityStatus" role="status">Activity has not been loaded.</p>
    <ol id="savedActivityEvents"></ol>
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
  <section id="savedWorkflowPanel" class="p" hidden aria-label="Tender team workflow">
    <h3>Team tender pipeline</h3>
    <p>Internal team status only; not proof of official submission or award.</p>
    <label for="savedWorkflowStage">Internal stage</label>
    <select id="savedWorkflowStage">
      <option value="new">New</option><option value="reviewing">Reviewing</option>
      <option value="preparing">Preparing application</option><option value="submitted">Submitted (team-recorded)</option>
      <option value="won">Won (team-recorded)</option><option value="lost">Lost (team-recorded)</option>
      <option value="archived">Archived</option>
    </select>
    <label for="savedWorkflowNote">Private team note (up to 2000 characters)</label>
    <textarea id="savedWorkflowNote" maxlength="2000" rows="3"></textarea>
    <button type="button" id="saveSavedWorkflow" disabled>Save status and note</button>
    <p id="savedWorkflowStatus" role="status">Not loaded.</p>
    <h4>Recent changes</h4><ol id="savedWorkflowEvents"></ol>
  </section>
</dialog>
"""
