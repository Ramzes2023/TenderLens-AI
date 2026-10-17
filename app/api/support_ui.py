"""Support Center UI for the authenticated VALYQON workspace."""

SUPPORT_HTML = r"""
<section
  id="supportCenter"
  class="support-page"
  data-page="support"
  hidden
>
  <header class="support-hero">
    <div>
      <span class="eyebrow">
        YOUR SUPPORT WORKSPACE
      </span>

      <h2>
        Get help, without the friction.
      </h2>

      <p>
        Explore product guides, ask a question, or create a ticket that your team can follow up.
      </p>
    </div>

    <div class="support-hero-actions">
      <button
        id="supportCreateRequest"
        type="button"
        class="support-primary"
      >
        Create a request
      </button>

      <button
        id="supportRefresh"
        type="button"
        class="support-secondary"
      >
        Refresh requests
      </button>
      <a class="support-guide-link" href="/scoring-methodology">Scoring methodology ↗</a>
    </div>
  </header>

  <section
    class="support-summary"
    aria-label="Support overview"
  >
    <article>
      <small>Open requests</small>
      <strong id="supportOpenCount">—</strong>
      <span>
        Requests awaiting resolution
      </span>
    </article>

    <article>
      <small>Latest request</small>
      <strong id="supportLatestTicket">—</strong>
      <span>
        Last recorded support request
      </span>
    </article>

    <article>
      <small>Assistant</small>
      <strong>Product guide</strong>
      <span>
        Answers and help articles when available
      </span>
    </article>
  </section>

  <div class="support-main-grid">
    <article class="support-card support-assistant-card">
      <div class="support-card-heading">
        <div>
          <span class="support-kicker">
            SUPPORT ASSISTANT
          </span>

          <h3>
            Ask VALYQON about the platform
          </h3>
        </div>

        <span class="support-live-pill">
          Product guide
        </span>
      </div>

      <p class="support-muted">
        Ask about discovery, company profiles,
        monitoring, Telegram or account access.
        For account-specific investigation,
        create a support request.
      </p>

      <div
        id="supportChat"
        class="support-chat"
        aria-live="polite"
      >
        <div class="support-message assistant">
          <strong>VALYQON Support</strong>
          <p>
            Hi. I can help you navigate VALYQON
            and explain common product workflows.
            What do you need help with?
          </p>
        </div>
      </div>

      <div class="support-topic-row">
        <button
          type="button"
          data-support-question="How do I discover opportunities?"
        >
          Discovery
        </button>

        <button
          type="button"
          data-support-question="How does company matching work?"
        >
          Company matching
        </button>

        <button
          type="button"
          data-support-question="How does monitoring work?"
        >
          Monitoring
        </button>

        <button
          type="button"
          data-support-question="How do I connect Telegram?"
        >
          Telegram
        </button>
      </div>

      <form
        id="supportAssistantForm"
        class="support-assistant-form"
      >
        <label
          class="sr-only"
          for="supportAssistantInput"
        >
          Ask Support Assistant
        </label>

        <input
          id="supportAssistantInput"
          type="text"
          maxlength="500"
          placeholder="Ask a product question..."
          autocomplete="off"
        >

        <button
          id="supportAssistantSubmit"
          type="submit"
          class="support-primary"
        >
          Ask AI
        </button>
      </form>

      <p class="support-assistant-note">
        Automated answers may be limited or unavailable.
        For account-specific investigation, create a support
        request. Never share passwords or API keys.
      </p>
    </article>

    <article
      id="supportRequestCard"
      class="support-card support-request-card"
    >
      <div class="support-card-heading">
        <div>
          <span class="support-kicker">
            CONTACT SUPPORT
          </span>

          <h3>
            Create a support request
          </h3>
        </div>
      </div>

      <p class="support-muted">
        Tell us what happened and what you expected. Your request stays visible in your VALYQON Support Center.
      </p>

      <form id="supportTicketForm">
        <div class="support-form-grid">
          <label>
            <span>First name</span>
            <input
              id="supportFirstName"
              name="first_name"
              type="text"
              maxlength="80"
              required
              autocomplete="given-name"
            >
          </label>

          <label>
            <span>Last name</span>
            <input
              id="supportLastName"
              name="last_name"
              type="text"
              maxlength="80"
              required
              autocomplete="family-name"
            >
          </label>

          <label class="support-wide">
            <span>Email</span>
            <input
              id="supportEmail"
              name="email"
              type="email"
              maxlength="254"
              required
              autocomplete="email"
            >
          </label>

          <label>
            <span>Category</span>
            <select
              id="supportCategory"
              name="category"
              required
            >
              <option value="technical_problem">
                Technical problem
              </option>

              <option value="tender_data">
                Tender data
              </option>

              <option value="account_access">
                Account & access
              </option>

              <option value="company_profile">
                Company profile
              </option>

              <option value="discovery_matching">
                Discovery & matching
              </option>

              <option value="billing">
                Billing
              </option>

              <option value="feature_request">
                Feature request
              </option>

              <option value="other">
                Other
              </option>
            </select>
          </label>

          <label>
            <span>Priority</span>
            <select
              id="supportPriority"
              name="priority"
            >
              <option value="low">
                Low
              </option>

              <option
                value="normal"
                selected
              >
                Normal
              </option>

              <option value="high">
                High
              </option>

              <option value="urgent">
                Urgent
              </option>
            </select>
          </label>

          <label class="support-wide">
            <span>Subject</span>
            <input
              id="supportSubject"
              name="subject"
              type="text"
              minlength="3"
              maxlength="160"
              required
              placeholder="Short summary of the problem"
            >
          </label>

          <label class="support-wide">
            <span>Description</span>
            <textarea
              id="supportDescription"
              name="description"
              minlength="10"
              maxlength="8000"
              required
              rows="5"
              placeholder="What happened? What were you trying to do? What did you expect to happen?"
            ></textarea>
          </label>
        </div>

        <div class="support-form-footer">
          <p>
            Do not include passwords,
            API keys or authentication tokens.
          </p>

          <button
            id="supportSubmit"
            type="submit"
            class="support-primary"
          >
            Submit request
          </button>
        </div>

        <div
          id="supportFormStatus"
          class="support-form-status"
          role="status"
          aria-live="polite"
        ></div>
      </form>
    </article>
  </div>

  <article class="support-card support-requests-card">
    <div class="support-card-heading">
      <div>
        <span class="support-kicker">
          MY REQUESTS
        </span>

        <h3>
          Your request history
        </h3>
      </div>

      <span
        id="supportRequestCount"
        class="support-count-pill"
      >
        —
      </span>
    </div>

    <div
      id="supportRequests"
      class="support-requests"
      aria-live="polite"
    >
      <div class="support-empty">
        Loading your support requests...
      </div>
    </div>
  </article>
</section>
"""