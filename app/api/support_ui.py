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
        VALYQON SUPPORT CENTER
      </span>

      <h2>
        Support that stays with your workflow.
      </h2>

      <p>
        Find trustworthy product guidance, follow an existing case or send an issue to the support team.
      </p>
    </div>

    <div class="support-hero-actions">
      <button
        id="supportCreateRequest"
        type="button"
        class="support-primary"
      >
        Report a problem
      </button>

      <button
        id="supportRefresh"
        type="button"
        class="support-secondary"
      >
        Refresh requests
      </button>
    </div>
  </header>

  <section
    class="support-summary"
    aria-label="Support overview"
  >
    <article>
      <small>Open requests</small>
      <strong id="supportOpenCount">—</strong>
      <span>Requests awaiting a resolution</span>
    </article>

    <article>
      <small>Latest request</small>
      <strong id="supportLatestTicket">—</strong>
      <span>Your latest support case</span>
    </article>

    <article>
      <small>Assistant</small>
      <strong>Product guidance</strong>
      <span>AI answers when the provider is available</span>
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
            Ask VALYQON
          </h3>
        </div>

        <span class="support-live-pill">
          Provider-dependent
        </span>
      </div>

      <p class="support-muted">
        Ask about discovery, company profiles,
        monitoring, Telegram or account access.
        For account-specific investigation,
        create a support request.
      </p>

      <nav class="support-knowledge-links" aria-label="Help resources">
        <a href="/how-it-works">Getting started ↗</a>
        <a href="/scoring-methodology">Scoring methodology ↗</a>
        <a href="/status">Service status ↗</a>
      </nav>

      <div
        id="supportChat"
        class="support-chat"
        aria-live="polite"
      >
        <div class="support-message assistant">
          <strong>VALYQON Support</strong>
          <p>
            Explore the help guides above, or ask a product question
            when the AI provider is available. For a personal account
            issue, use the support request form.
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
        AI-generated product guidance may contain mistakes.
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
            Report a problem
          </h3>
        </div>
      </div>

      <p class="support-muted">
        Describe the issue clearly.
        Your request will be saved in your
        VALYQON Support Center.
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
          Support history
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