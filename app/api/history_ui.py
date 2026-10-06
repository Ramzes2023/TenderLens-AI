"""Discovery Search History workspace markup."""

HISTORY_HTML = """
<section
  id="historyWorkspace"
  class="p"
  data-page="search-history"
  hidden
>
  <div class="toolbar">
    <div>
      <span class="eyebrow">
        DISCOVERY ARCHIVE
      </span>

      <h2>
        Search history
      </h2>

      <p>
        Review previous Discovery runs for the active company
        without querying procurement sources again.
      </p>
    </div>

    <button
      id="refreshHistory"
      type="button"
    >
      Refresh history
    </button>
  </div>

  <div class="overview-metrics">
    <article>
      <small>
        Previous searches
      </small>

      <strong
        id="historyCount"
        class="metric"
      >
        0
      </strong>

      <span>
        Active company archive
      </span>
    </article>
  </div>

  <p
    id="historyContext"
    class="muted"
  >
    Loading workspace...
  </p>

  <p
    id="historyMessage"
    role="status"
    aria-live="polite"
  >
    Open Search History to load previous Discovery runs.
  </p>

  <div
    id="historyRuns"
    aria-label="Discovery search history"
  ></div>

  <section
    id="historySnapshot"
    hidden
  >
    <div class="toolbar">
      <div>
        <span class="eyebrow">
          SAVED DISCOVERY SNAPSHOT
        </span>

        <h3 id="historySnapshotTitle">
          Previous search
        </h3>
      </div>

      <button
        id="closeHistorySnapshot"
        type="button"
      >
        Close results
      </button>
    </div>

    <p
      id="historySnapshotMeta"
      class="fine"
    ></p>

    <div
      id="historySnapshotResults"
      aria-label="Historical discovery results"
    ></div>
  </section>
</section>

<dialog
  id="historyTenderDetail"
  aria-labelledby="historyTenderDetailTitle"
>
  <div class="toolbar">
    <h2 id="historyTenderDetailTitle">
      Historical opportunity
    </h2>

    <button
      id="closeHistoryTenderDetail"
      type="button"
      autofocus
    >
      Close detail
    </button>
  </div>

  <div id="historyTenderDetailBody"></div>
</dialog>
"""
