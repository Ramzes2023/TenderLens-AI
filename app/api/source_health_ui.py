"""Procurement Source Health workspace markup."""

SOURCE_HEALTH_HTML = """
<section
  id="sourceHealthWorkspace"
  class="p"
  data-page="source-health"
  hidden
>
  <div class="toolbar">
    <div>
      <span class="eyebrow">
        CONNECTOR OBSERVABILITY
      </span>

      <h2>
        Source Health
      </h2>

      <p>
        Review the latest recorded condition of procurement
        sources for the active company.
        Opening this page does not query procurement sources.
      </p>
    </div>

    <button
      id="refreshSourceHealth"
      type="button"
    >
      Refresh status
    </button>
  </div>

  <div
    class="overview-metrics"
    aria-label="Source health summary"
  >
    <article>
      <small>Healthy</small>
      <strong
        id="sourceHealthyCount"
        class="metric"
      >
        0
      </strong>
      <span>Last recorded check</span>
    </article>

    <article>
      <small>Failed</small>
      <strong
        id="sourceFailedCount"
        class="metric"
      >
        0
      </strong>
      <span>Requires attention</span>
    </article>

    <article>
      <small>Disabled</small>
      <strong
        id="sourceDisabledCount"
        class="metric"
      >
        0
      </strong>
      <span>Not configured or disabled</span>
    </article>

    <article>
      <small>Not checked</small>
      <strong
        id="sourceUncheckedCount"
        class="metric"
      >
        0
      </strong>
      <span>No recorded probe yet</span>
    </article>
  </div>

  <p
    id="sourceHealthContext"
    class="muted"
  >
    Loading workspace...
  </p>

  <p
    id="sourceHealthLastChecked"
    class="fine"
  >
    No recorded Discovery check yet.
  </p>

  <p
    id="sourceHealthMessage"
    role="status"
    aria-live="polite"
  >
    Open Source Health to load the latest recorded status.
  </p>

  <div
    id="sourceHealthResults"
    aria-label="Procurement source status"
  ></div>
</section>
"""
