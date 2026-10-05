(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);

  const categoryLabels = {
    technical_problem: "Technical problem",
    tender_data: "Tender data",
    account_access: "Account & access",
    company_profile: "Company profile",
    discovery_matching: "Discovery & matching",
    billing: "Billing",
    feature_request: "Feature request",
    other: "Other"
  };

  const statusLabels = {
    open: "Open",
    in_progress: "In progress",
    resolved: "Resolved",
    closed: "Closed"
  };

  let accountLoaded = false;
  let ticketsLoaded = false;

  function text(tag, value, className) {
    const node = document.createElement(tag);
    node.textContent = value;

    if (className) {
      node.className = className;
    }

    return node;
  }

  function supportVisible() {
    return location.hash === "#support";
  }

  async function loadAccount() {
    if (accountLoaded) {
      return;
    }

    try {
      const response = await fetch(
        "/api/v1/auth/me",
        {
          headers: {
            Accept: "application/json"
          }
        }
      );

      if (!response.ok) {
        return;
      }

      const account = await response.json();

      const email = $("supportEmail");

      if (
        email &&
        !email.value
      ) {
        email.value = account.email || "";
      }

      accountLoaded = true;
    } catch (_) {
      // Support form remains usable if account metadata
      // could not be prefetched.
    }
  }

  function formatDate(value) {
    if (!value) {
      return "—";
    }

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
      return value;
    }

    return date.toLocaleString();
  }

  function renderTicket(ticket) {
    const details = document.createElement("details");
    details.className = "support-ticket";

    const summary = document.createElement("summary");

    summary.append(
      text(
        "span",
        ticket.public_id,
        "support-ticket-id"
      ),
      text(
        "span",
        ticket.subject,
        "support-ticket-subject"
      ),
      text(
        "span",
        formatDate(ticket.created_at),
        "support-ticket-date"
      )
    );

    const status = text(
      "span",
      statusLabels[ticket.status] || ticket.status,
      "support-status"
    );

    status.classList.add(
      String(ticket.status || "open")
    );

    summary.append(status);

    const body = document.createElement("div");
    body.className = "support-ticket-body";

    const meta = document.createElement("div");
    meta.className = "support-ticket-meta";

    meta.append(
      text(
        "span",
        categoryLabels[ticket.category] ||
          ticket.category
      ),
      text(
        "span",
        "Priority: " + ticket.priority
      ),
      text(
        "span",
        "Updated: " +
          formatDate(ticket.updated_at)
      )
    );

    if (ticket.page_path) {
      meta.append(
        text(
          "span",
          "Page: " + ticket.page_path
        )
      );
    }

    body.append(
      meta,
      text(
        "p",
        ticket.description,
        "support-ticket-description"
      )
    );

    details.append(
      summary,
      body
    );

    return details;
  }

  function updateSummary(tickets) {
    const open = tickets.filter(
      (ticket) =>
        ticket.status === "open" ||
        ticket.status === "in_progress"
    ).length;

    $("supportOpenCount").textContent =
      String(open);

    $("supportLatestTicket").textContent =
      tickets.length
        ? tickets[0].public_id
        : "None";

    $("supportRequestCount").textContent =
      String(tickets.length);
  }

  async function loadTickets() {
    const container = $("supportRequests");

    if (!container) {
      return;
    }

    container.replaceChildren(
      text(
        "div",
        "Loading your support requests...",
        "support-empty"
      )
    );

    try {
      const response = await fetch(
        "/api/v1/support/tickets?limit=50",
        {
          headers: {
            Accept: "application/json"
          }
        }
      );

      if (!response.ok) {
        throw new Error(
          "Support requests could not be loaded."
        );
      }

      const tickets = await response.json();

      container.replaceChildren();

      updateSummary(tickets);

      if (!tickets.length) {
        container.append(
          text(
            "div",
            "No support requests yet. " +
              "If something is not working, " +
              "send us a request.",
            "support-empty"
          )
        );

        ticketsLoaded = true;
        return;
      }

      tickets.forEach((ticket) => {
        container.append(
          renderTicket(ticket)
        );
      });

      ticketsLoaded = true;
    } catch (_) {
      container.replaceChildren(
        text(
          "div",
          "Support requests could not be loaded. " +
            "Please retry.",
          "support-error"
        )
      );
    }
  }

  function addChatMessage(role, message) {
    const chat = $("supportChat");

    if (!chat) {
      return;
    }

    const wrapper = document.createElement("div");
    wrapper.className =
      "support-message " + role;

    if (role === "assistant") {
      wrapper.append(
        text(
          "strong",
          "VALYQON Support"
        )
      );
    }

    wrapper.append(
      text(
        "p",
        message
      )
    );

    chat.append(wrapper);

    chat.scrollTop =
      chat.scrollHeight;
  }

  const assistantHistory = [];

  function fallbackAssistantAnswer(question) {
    const q = String(question || "")
      .toLowerCase();

    if (
      q.includes("discover") ||
      q.includes("opportun") ||
      q.includes("tender")
    ) {
      return (
        "Discovery checks supported procurement sources " +
        "for the active company and can show preliminary " +
        "metadata fit. Preliminary fit is not a win " +
        "probability."
      );
    }

    if (
      q.includes("company") ||
      q.includes("profile") ||
      q.includes("match")
    ) {
      return (
        "Company matching uses information from the " +
        "company profile such as products, keywords, " +
        "markets and commercial constraints."
      );
    }

    if (
      q.includes("monitor") ||
      q.includes("alert")
    ) {
      return (
        "Monitoring supports repeat checks for configured " +
        "workflows. Some alert workflows can also use " +
        "the Telegram companion."
      );
    }

    if (q.includes("telegram")) {
      return (
        "Telegram is a companion interface for supported " +
        "VALYQON workflows and configured alerts."
      );
    }

    return (
      "The live AI assistant is temporarily unavailable. " +
      "For a specific technical or account problem, " +
      "please create a support request."
    );
  }

  async function askAssistant(question) {
    const clean = String(
      question || ""
    ).trim();

    if (!clean) {
      return;
    }

    const submit =
      $("supportAssistantSubmit");

    addChatMessage(
      "user",
      clean
    );

    const previousHistory =
      assistantHistory.slice(-8);

    assistantHistory.push({
      role: "user",
      content: clean
    });

    if (submit) {
      submit.disabled = true;
      submit.textContent = "Thinking...";
    }

    try {
      const response = await fetch(
        "/api/v1/support/assistant",
        {
          method: "POST",
          headers: {
            "Content-Type":
              "application/json",
            Accept:
              "application/json"
          },
          body: JSON.stringify({
            message: clean,
            history: previousHistory,
            page_path:
              location.pathname +
              location.hash
          })
        }
      );

      let body = null;

      try {
        body = await response.json();
      } catch (_) {
        body = null;
      }

      if (!response.ok) {
        throw new Error(
          body &&
          typeof body.detail === "string"
            ? body.detail
            : "AI Support Assistant is unavailable."
        );
      }

      const answer = String(
        body.answer || ""
      ).trim();

      if (!answer) {
        throw new Error(
          "AI Support Assistant returned no answer."
        );
      }

      assistantHistory.push({
        role: "assistant",
        content: answer
      });

      addChatMessage(
        "assistant",
        answer
      );

    } catch (_) {
      const fallback =
        fallbackAssistantAnswer(clean);

      assistantHistory.push({
        role: "assistant",
        content: fallback
      });

      addChatMessage(
        "assistant",
        fallback
      );

    } finally {
      if (submit) {
        submit.disabled = false;
        submit.textContent = "Ask AI";
      }
    }
  }

  async function submitTicket(event) {
    event.preventDefault();

    const submit = $("supportSubmit");
    const status = $("supportFormStatus");

    status.className =
      "support-form-status";

    status.textContent =
      "Saving your request...";

    submit.disabled = true;

    const payload = {
      first_name:
        $("supportFirstName").value.trim(),

      last_name:
        $("supportLastName").value.trim(),

      email:
        $("supportEmail").value.trim(),

      category:
        $("supportCategory").value,

      priority:
        $("supportPriority").value,

      subject:
        $("supportSubject").value.trim(),

      description:
        $("supportDescription").value.trim(),

      page_path:
        location.pathname + location.hash
    };

    try {
      const response = await fetch(
        "/api/v1/support/tickets",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json"
          },
          body: JSON.stringify(payload)
        }
      );

      let body = null;

      try {
        body = await response.json();
      } catch (_) {
        body = null;
      }

      if (!response.ok) {
        const detail =
          body &&
          typeof body.detail === "string"
            ? body.detail
            : "Support request could not be saved.";

        throw new Error(detail);
      }

      status.classList.add("success");

      status.textContent =
        "Request " +
        body.public_id +
        " was created successfully.";

      $("supportSubject").value = "";
      $("supportDescription").value = "";
      $("supportPriority").value = "normal";

      await loadTickets();
    } catch (error) {
      status.classList.add("error");

      status.textContent =
        error &&
        error.message
          ? error.message
          : "Support request could not be saved.";
    } finally {
      submit.disabled = false;
    }
  }

  function activateSupport() {
    if (!supportVisible()) {
      return;
    }

    loadAccount();

    if (!ticketsLoaded) {
      loadTickets();
    }
  }

  document
    .querySelectorAll(
      "[data-support-question]"
    )
    .forEach((button) => {
      button.addEventListener(
        "click",
        () => {
          void askAssistant(
            button.dataset.supportQuestion
          );
        }
      );
    });

  const assistantForm =
    $("supportAssistantForm");

  if (assistantForm) {
    assistantForm.addEventListener(
      "submit",
      (event) => {
        event.preventDefault();

        const input =
          $("supportAssistantInput");

        const question =
          input.value;

        input.value = "";

        void askAssistant(
          question
        );

        input.focus();
      }
    );
  }

  const ticketForm =
    $("supportTicketForm");

  if (ticketForm) {
    ticketForm.addEventListener(
      "submit",
      submitTicket
    );
  }

  const refresh =
    $("supportRefresh");

  if (refresh) {
    refresh.addEventListener(
      "click",
      loadTickets
    );
  }

  const create =
    $("supportCreateRequest");

  if (create) {
    create.addEventListener(
      "click",
      () => {
        $("supportRequestCard")
          .scrollIntoView({
            behavior: "smooth",
            block: "start"
          });

        $("supportFirstName")
          .focus();
      }
    );
  }

  window.addEventListener(
    "hashchange",
    activateSupport
  );



  const globalLauncher =
    $("globalSupportLauncher");

  const globalPanel =
    $("globalSupportPanel");

  const globalClose =
    $("globalSupportClose");

  const globalReportProblem =
    $("globalReportProblem");

  function closeGlobalSupport() {
    if (globalPanel) {
      globalPanel.hidden = true;
    }
  }

  if (
    globalLauncher &&
    globalPanel
  ) {
    globalLauncher.addEventListener(
      "click",
      () => {
        globalPanel.hidden =
          !globalPanel.hidden;
      }
    );
  }

  if (globalClose) {
    globalClose.addEventListener(
      "click",
      closeGlobalSupport
    );
  }

  if (globalReportProblem) {
    globalReportProblem.addEventListener(
      "click",
      () => {
        closeGlobalSupport();

        window.setTimeout(
          () => {
            const card =
              $("supportRequestCard");

            const firstName =
              $("supportFirstName");

            if (card) {
              card.scrollIntoView({
                behavior: "smooth",
                block: "start"
              });
            }

            if (firstName) {
              firstName.focus({
                preventScroll: true
              });
            }
          },
          120
        );
      }
    );
  }

  window.addEventListener(
    "hashchange",
    closeGlobalSupport
  );

  document.addEventListener(
    "keydown",
    (event) => {
      if (
        event.key === "Escape" &&
        globalPanel &&
        !globalPanel.hidden
      ) {
        closeGlobalSupport();
      }
    }
  );



  function updateSupportPageChrome() {
    const isSupport =
      location.hash === "#support";

    const orgControl =
      $("orgControl");

    const onboarding =
      $("onboarding");

    const launcher =
      $("globalSupportLauncher");

    if (orgControl) {
      orgControl.hidden = isSupport;
    }

    if (onboarding) {
      if (isSupport) {
        onboarding.hidden = true;
      } else {
        window.dispatchEvent(
          new Event("workspace-context")
        );
      }
    }

    if (launcher) {
      launcher.hidden = isSupport;
    }

    if (
      globalPanel &&
      isSupport
    ) {
      globalPanel.hidden = true;
    }
  }

  window.addEventListener(
    "hashchange",
    updateSupportPageChrome
  );

  updateSupportPageChrome();

  activateSupport();
})();


/* VALYQON SUPPORT CONVERSATIONS V1 */
(function () {
  "use strict";

  const $ = (id) =>
    document.getElementById(id);

  const STATUS_LABELS = {
    open: "Open",
    in_progress: "In progress",
    resolved: "Resolved",
    closed: "Closed",
  };

  let activeUserTicketId = null;
  let activeOperatorTicketId = null;

  let refreshTimer = null;

  function element(
    tag,
    className,
    text
  ) {
    const node =
      document.createElement(tag);

    if (className) {
      node.className = className;
    }

    if (
      text !== undefined
      && text !== null
    ) {
      node.textContent = text;
    }

    return node;
  }

  function formatDate(value) {
    if (!value) {
      return "";
    }

    const date = new Date(value);

    if (
      Number.isNaN(
        date.getTime()
      )
    ) {
      return value;
    }

    return new Intl.DateTimeFormat(
      undefined,
      {
        dateStyle: "medium",
        timeStyle: "short",
      }
    ).format(date);
  }

  function statusText(status) {
    return (
      STATUS_LABELS[status]
      || status
      || "Unknown"
    );
  }

  function statusPill(status) {
    const node = element(
      "span",
      "support-thread-status "
        + (
          "status-"
          + String(
            status || "open"
          )
        ),
      statusText(status)
    );

    return node;
  }

  async function api(
    url,
    options = {}
  ) {
    const headers = {
      ...(options.headers || {}),
    };

    if (
      options.body
      && !headers[
        "Content-Type"
      ]
    ) {
      headers[
        "Content-Type"
      ] = "application/json";
    }

    const response =
      await fetch(
        url,
        {
          ...options,
          headers,
          credentials: "same-origin",
        }
      );

    let payload = null;

    const contentType =
      response.headers.get(
        "content-type"
      ) || "";

    try {
      payload =
        contentType.includes(
          "application/json"
        )
          ? await response.json()
          : await response.text();
    } catch {
      payload = null;
    }

    if (!response.ok) {
      const message =
        payload
        && typeof payload
          === "object"
        && payload.detail
          ? String(
              payload.detail
            )
          : (
              "Request failed ("
              + response.status
              + ")."
            );

      const error =
        new Error(message);

      error.status =
        response.status;

      throw error;
    }

    return payload;
  }

  function emptyState(text) {
    return element(
      "div",
      "support-thread-empty",
      text
    );
  }

  function errorState(text) {
    return element(
      "div",
      "support-thread-error",
      text
    );
  }

  function createHeading(
    kicker,
    title,
    description,
    actionLabel,
    action
  ) {
    const heading = element(
      "div",
      "support-conversation-heading"
    );

    const copy = element(
      "div",
      "support-conversation-heading-copy"
    );

    copy.append(
      element(
        "span",
        "support-kicker",
        kicker
      ),
      element(
        "h3",
        "",
        title
      ),
      element(
        "p",
        "support-muted",
        description
      )
    );

    heading.append(copy);

    if (
      actionLabel
      && action
    ) {
      const button =
        element(
          "button",
          "support-secondary",
          actionLabel
        );

      button.type = "button";

      button.addEventListener(
        "click",
        action
      );

      heading.append(button);
    }

    return heading;
  }

  function createConversationCard({
    id,
    kicker,
    title,
    description,
  }) {
    const card = element(
      "article",
      "support-card support-conversation-card"
    );

    card.id = id;

    const list = element(
      "div",
      "support-thread-list"
    );

    const detail = element(
      "div",
      "support-thread-detail"
    );

    const grid = element(
      "div",
      "support-conversation-grid"
    );

    grid.append(
      list,
      detail
    );

    card.append(
      createHeading(
        kicker,
        title,
        description,
        "Refresh",
        () => {
          if (
            id
            === "supportUserConversations"
          ) {
            void loadUserTickets();
          } else {
            void loadOperatorTickets();
          }
        }
      ),
      grid
    );

    return {
      card,
      list,
      detail,
    };
  }

  function ticketListButton(
    ticket,
    active,
    onClick
  ) {
    const button = element(
      "button",
      "support-thread-item"
        + (
          active
            ? " active"
            : ""
        )
    );

    button.type = "button";

    button.append(
      element(
        "strong",
        "support-thread-ticket-id",
        ticket.public_id
      ),
      element(
        "span",
        "support-thread-ticket-subject",
        ticket.subject
          || "Support request"
      )
    );

    const meta = element(
      "div",
      "support-thread-item-meta"
    );

    meta.append(
      statusPill(
        ticket.status
      ),
      element(
        "time",
        "",
        formatDate(
          ticket.updated_at
          || ticket.created_at
        )
      )
    );

    button.append(meta);

    button.addEventListener(
      "click",
      onClick
    );

    return button;
  }

  function renderTicketHeader(
    container,
    ticket,
    operator
  ) {
    const header = element(
      "div",
      "support-thread-ticket-header"
    );

    const copy = element(
      "div"
    );

    copy.append(
      element(
        "span",
        "support-thread-ticket-id",
        ticket.public_id
      ),
      element(
        "h4",
        "",
        ticket.subject
          || "Support request"
      )
    );

    if (operator) {
      copy.append(
        element(
          "p",
          "support-thread-customer",
          (
            (
              ticket.first_name
              || ""
            )
            + " "
            + (
              ticket.last_name
              || ""
            )
          ).trim()
          + (
            ticket.email
              ? " \u00b7 "
                + ticket.email
              : ""
          )
        )
      );
    }

    header.append(
      copy,
      statusPill(
        ticket.status
      )
    );

    container.append(header);

    const meta = element(
      "div",
      "support-thread-meta"
    );

    const category = element(
      "span",
      "",
      "Category: "
        + String(
          ticket.category
          || "?"
        )
    );

    const priority = element(
      "span",
      "",
      "Priority: "
        + String(
          ticket.priority
          || "?"
        )
    );

    const created = element(
      "span",
      "",
      "Created: "
        + formatDate(
          ticket.created_at
        )
    );

    meta.append(
      category,
      priority,
      created
    );

    container.append(meta);
  }

  function renderOriginalRequest(
    container,
    ticket
  ) {
    const block = element(
      "section",
      "support-original-request"
    );

    block.append(
      element(
        "strong",
        "",
        "Original request"
      ),
      element(
        "p",
        "",
        ticket.description
          || "No description supplied."
      )
    );

    container.append(block);
  }

  function renderMessages(
    container,
    messages
  ) {
    const stream = element(
      "div",
      "support-thread-messages"
    );

    if (
      !messages
      || !messages.length
    ) {
      stream.append(
        emptyState(
          "No replies yet."
        )
      );
    } else {
      messages.forEach(
        (message) => {
          const bubble =
            element(
              "article",
              (
                "support-thread-message "
                + (
                  message.author_type
                  === "support"
                    ? "support"
                    : "user"
                )
              )
            );

          bubble.append(
            element(
              "strong",
              "",
              message.author_type
              === "support"
                ? "VALYQON Support"
                : "You"
            ),
            element(
              "p",
              "",
              message.body
            ),
            element(
              "time",
              "",
              formatDate(
                message.created_at
              )
            )
          );

          stream.append(
            bubble
          );
        }
      );
    }

    container.append(
      stream
    );

    requestAnimationFrame(
      () => {
        stream.scrollTop =
          stream.scrollHeight;
      }
    );
  }

  function buildReplyForm({
    label,
    buttonLabel,
    onSubmit,
  }) {
    const form = element(
      "form",
      "support-thread-reply"
    );

    const textarea =
      document.createElement(
        "textarea"
      );

    textarea.rows = 4;
    textarea.maxLength = 8000;
    textarea.required = true;
    textarea.placeholder =
      label;

    const footer = element(
      "div",
      "support-thread-reply-footer"
    );

    const status = element(
      "span",
      "support-thread-action-status"
    );

    const button = element(
      "button",
      "support-primary",
      buttonLabel
    );

    button.type = "submit";

    footer.append(
      status,
      button
    );

    form.append(
      textarea,
      footer
    );

    form.addEventListener(
      "submit",
      async (event) => {
        event.preventDefault();

        const body =
          textarea.value.trim();

        if (!body) {
          return;
        }

        button.disabled = true;
        status.textContent =
          "Sending\u2026";

        try {
          await onSubmit(body);

          textarea.value = "";

          status.textContent =
            "Sent.";

        } catch (error) {
          status.textContent =
            error.message
            || "Could not send.";
        } finally {
          button.disabled = false;
        }
      }
    );

    return form;
  }

  async function openUserTicket(
    publicId
  ) {
    const detail =
      $(
        "supportUserConversationDetail"
      );

    if (!detail) {
      return;
    }

    activeUserTicketId =
      publicId;

    detail.replaceChildren(
      emptyState(
        "Loading conversation\u2026"
      )
    );

    try {
      const conversation =
        await api(
          "/api/v1/support/tickets/"
          + encodeURIComponent(
            publicId
          )
          + "/conversation"
        );

      detail.replaceChildren();

      renderTicketHeader(
        detail,
        conversation.ticket,
        false
      );

      renderOriginalRequest(
        detail,
        conversation.ticket
      );

      renderMessages(
        detail,
        conversation.messages
      );

      detail.append(
        buildReplyForm({
          label:
            "Write a reply to VALYQON Support\u2026",
          buttonLabel:
            "Send reply",
          onSubmit:
            async (body) => {
              await api(
                "/api/v1/support/tickets/"
                + encodeURIComponent(
                  publicId
                )
                + "/messages",
                {
                  method: "POST",
                  body:
                    JSON.stringify({
                      body,
                    }),
                }
              );

              await loadUserTickets(
                publicId
              );

              await loadOperatorTickets(
                activeOperatorTicketId
              );
            },
        })
      );

    } catch (error) {
      detail.replaceChildren(
        errorState(
          error.message
          || (
            "Conversation could "
            + "not be loaded."
          )
        )
      );
    }
  }

  async function loadUserTickets(
    preferredId = null
  ) {
    const list =
      $(
        "supportUserConversationList"
      );

    const detail =
      $(
        "supportUserConversationDetail"
      );

    if (
      !list
      || !detail
    ) {
      return;
    }

    list.replaceChildren(
      emptyState(
        "Loading requests\u2026"
      )
    );

    try {
      const tickets =
        await api(
          "/api/v1/support/tickets?limit=50"
        );

      list.replaceChildren();

      if (!tickets.length) {
        list.append(
          emptyState(
            "You have no support requests yet."
          )
        );

        detail.replaceChildren(
          emptyState(
            "Create a request and it will appear here."
          )
        );

        activeUserTicketId =
          null;

        return;
      }

      const chosen =
        preferredId
        || (
          tickets.some(
            (ticket) =>
              ticket.public_id
              === activeUserTicketId
          )
            ? activeUserTicketId
            : tickets[0].public_id
        );

      tickets.forEach(
        (ticket) => {
          list.append(
            ticketListButton(
              ticket,
              ticket.public_id
                === chosen,
              () => {
                void loadUserTickets(
                  ticket.public_id
                );
              }
            )
          );
        }
      );

      await openUserTicket(
        chosen
      );

    } catch (error) {
      list.replaceChildren(
        errorState(
          error.message
          || (
            "Support requests "
            + "could not be loaded."
          )
        )
      );
    }
  }

  async function updateOperatorStatus(
    publicId,
    status
  ) {
    await api(
      "/api/v1/support/operator/tickets/"
      + encodeURIComponent(
        publicId
      )
      + "/status",
      {
        method: "PATCH",
        body:
          JSON.stringify({
            status,
          }),
      }
    );
  }

  async function openOperatorTicket(
    publicId
  ) {
    const detail =
      $(
        "supportOperatorConversationDetail"
      );

    if (!detail) {
      return;
    }

    activeOperatorTicketId =
      publicId;

    detail.replaceChildren(
      emptyState(
        "Loading customer conversation\u2026"
      )
    );

    try {
      const conversation =
        await api(
          "/api/v1/support/operator/tickets/"
          + encodeURIComponent(
            publicId
          )
          + "/conversation"
        );

      detail.replaceChildren();

      renderTicketHeader(
        detail,
        conversation.ticket,
        true
      );

      const controls = element(
        "div",
        "support-operator-controls"
      );

      const label = element(
        "label",
        "",
        "Ticket status"
      );

      const select =
        document.createElement(
          "select"
        );

      Object.entries(
        STATUS_LABELS
      ).forEach(
        ([value, text]) => {
          const option =
            document.createElement(
              "option"
            );

          option.value = value;
          option.textContent =
            text;

          if (
            conversation.ticket
              .status
            === value
          ) {
            option.selected = true;
          }

          select.append(
            option
          );
        }
      );

      const actionStatus =
        element(
          "span",
          "support-thread-action-status"
        );

      select.addEventListener(
        "change",
        async () => {
          select.disabled = true;
          actionStatus.textContent =
            "Updating\u2026";

          try {
            await updateOperatorStatus(
              publicId,
              select.value
            );

            actionStatus.textContent =
              "Status updated.";

            await loadOperatorTickets(
              publicId
            );

            await loadUserTickets(
              activeUserTicketId
            );

          } catch (error) {
            actionStatus.textContent =
              error.message
              || (
                "Could not update "
                + "status."
              );

            select.disabled = false;
          }
        }
      );

      label.append(select);

      controls.append(
        label,
        actionStatus
      );

      detail.append(
        controls
      );

      renderOriginalRequest(
        detail,
        conversation.ticket
      );

      renderMessages(
        detail,
        conversation.messages
      );

      detail.append(
        buildReplyForm({
          label:
            "Reply as VALYQON Support\u2026",
          buttonLabel:
            "Send support reply",
          onSubmit:
            async (body) => {
              await api(
                "/api/v1/support/operator/tickets/"
                + encodeURIComponent(
                  publicId
                )
                + "/messages",
                {
                  method: "POST",
                  body:
                    JSON.stringify({
                      body,
                    }),
                }
              );

              await loadOperatorTickets(
                publicId
              );

              await loadUserTickets(
                activeUserTicketId
              );
            },
        })
      );

    } catch (error) {
      detail.replaceChildren(
        errorState(
          error.message
          || (
            "Customer conversation "
            + "could not be loaded."
          )
        )
      );
    }
  }

  async function loadOperatorTickets(
    preferredId = null
  ) {
    const card =
      $(
        "supportOperatorInbox"
      );

    const list =
      $(
        "supportOperatorConversationList"
      );

    const detail =
      $(
        "supportOperatorConversationDetail"
      );

    if (
      !card
      || !list
      || !detail
    ) {
      return;
    }

    try {
      const tickets =
        await api(
          "/api/v1/support/operator/tickets?limit=100"
        );

      card.hidden = false;

      list.replaceChildren();

      if (!tickets.length) {
        list.append(
          emptyState(
            "The support queue is empty."
          )
        );

        detail.replaceChildren(
          emptyState(
            "No customer ticket selected."
          )
        );

        activeOperatorTicketId =
          null;

        return;
      }

      const chosen =
        preferredId
        || (
          tickets.some(
            (ticket) =>
              ticket.public_id
              === activeOperatorTicketId
          )
            ? activeOperatorTicketId
            : tickets[0].public_id
        );

      tickets.forEach(
        (ticket) => {
          list.append(
            ticketListButton(
              ticket,
              ticket.public_id
                === chosen,
              () => {
                void loadOperatorTickets(
                  ticket.public_id
                );
              }
            )
          );
        }
      );

      await openOperatorTicket(
        chosen
      );

    } catch (error) {
      if (
        error.status === 403
        || error.status === 401
      ) {
        card.hidden = true;
        return;
      }

      card.hidden = false;

      list.replaceChildren(
        errorState(
          error.message
          || (
            "Support Inbox "
            + "could not be loaded."
          )
        )
      );
    }
  }

  async function refreshAll(
    preferredUserId = null
  ) {
    await loadUserTickets(
      preferredUserId
    );

    await loadOperatorTickets(
      activeOperatorTicketId
    );
  }

  function mount() {
    const center =
      $("supportCenter");

    const oldRequests =
      document.querySelector(
        ".support-requests-card"
      );

    if (
      !center
      || !oldRequests
    ) {
      return;
    }

    if (
      $("supportConversationHub")
    ) {
      return;
    }

    const hub = element(
      "section",
      "support-conversation-hub"
    );

    hub.id =
      "supportConversationHub";

    const user =
      createConversationCard({
        id:
          "supportUserConversations",
        kicker:
          "MY REQUESTS",
        title:
          "Support conversations",
        description:
          (
            "Open a request, review its history "
            + "and continue the conversation "
            + "with VALYQON Support."
          ),
      });

    user.list.id =
      "supportUserConversationList";

    user.detail.id =
      "supportUserConversationDetail";

    const operator =
      createConversationCard({
        id:
          "supportOperatorInbox",
        kicker:
          "SUPPORT OPERATIONS",
        title:
          "Support Inbox",
        description:
          (
            "Platform operator workspace for "
            + "customer requests, replies "
            + "and ticket status."
          ),
      });

    operator.card.hidden = true;

    operator.list.id =
      "supportOperatorConversationList";

    operator.detail.id =
      "supportOperatorConversationDetail";

    hub.append(
      user.card,
      operator.card
    );

    oldRequests.insertAdjacentElement(
      "afterend",
      hub
    );

    oldRequests.hidden = true;

    void refreshAll();

    const refresh =
      $("supportRefresh");

    if (refresh) {
      refresh.addEventListener(
        "click",
        () => {
          window.setTimeout(
            () => {
              void refreshAll(
                activeUserTicketId
              );
            },
            100
          );
        }
      );
    }

    const createForm =
      $("supportTicketForm");

    if (createForm) {
      createForm.addEventListener(
        "submit",
        () => {
          window.setTimeout(
            () => {
              void refreshAll();
            },
            700
          );
        }
      );
    }

    const legacyRequests =
      $("supportRequests");

    if (
      legacyRequests
      && window.MutationObserver
    ) {
      const observer =
        new MutationObserver(
          () => {
            clearTimeout(
              refreshTimer
            );

            refreshTimer =
              window.setTimeout(
                () => {
                  void refreshAll(
                    activeUserTicketId
                  );
                },
                250
              );
          }
        );

      observer.observe(
        legacyRequests,
        {
          childList: true,
          subtree: true,
        }
      );
    }
  }

  if (
    document.readyState
    === "loading"
  ) {
    document.addEventListener(
      "DOMContentLoaded",
      mount,
      {
        once: true,
      }
    );
  } else {
    mount();
  }
})();
