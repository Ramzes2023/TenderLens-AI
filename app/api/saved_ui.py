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
  </div>

  <div class="overview-metrics">
    <article>
      <small>
        Saved opportunities
      </small>

      <strong
        id="savedCount"
        class="metric"
      >
        0
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
