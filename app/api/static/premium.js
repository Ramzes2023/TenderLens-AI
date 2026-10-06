/* Navigation-only command menu: no implied global search or hidden API calls. */
(function(){
 const $=id=>document.getElementById(id),dialog=$('commandPalette');
 function render(){const query=$('commandQuery').value.trim().toLowerCase();const links=[...document.querySelectorAll('[data-nav]')].filter(a=>a.textContent.trim().toLowerCase().includes(query));$('commandResults').replaceChildren();for(const link of links){const button=document.createElement('button');button.textContent='Go to '+link.textContent.trim();button.onclick=()=>{location.hash=link.dataset.nav;dialog.close();};$('commandResults').append(button);}if(!links.length)$('commandResults').textContent='No matching pages.';}
 function open(){render();dialog.showModal();$('commandQuery').focus();}
 $('openCommands').onclick=open;$('closeCommands').onclick=()=>dialog.close();$('commandQuery').addEventListener('input',render);
 window.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();if(!dialog.open)open();}});
 const system=$('healthBadge')?.closest('article');if(system)system.dataset.page='settings';
 window.addEventListener('workspace-context',()=>{$('sideCompany').textContent=state.activeCompanyName||'Choose a company';});
 window.addEventListener('discovery-report',e=>{const r=e.detail;$('sourcesChecked').textContent=r?String((r.attempted_sources||[]).length):'—';$('lastDiscovery').textContent=r?new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}):'Not run';});
 // Reconcile the technical card after initial shell navigation.
 if(system)system.hidden=(location.hash.slice(1)||'overview')!=='settings';
})();


/* VALYQON OVERVIEW V2 */
(function () {
  "use strict";

  const qs = (selector, root = document) =>
    root.querySelector(selector);

  const qsa = (selector, root = document) =>
    Array.from(root.querySelectorAll(selector));

  function findOverviewBlock(text) {
    return qsa('[data-page="overview"]').find(
      (node) =>
        node.textContent
          .replace(/\s+/g, " ")
          .includes(text)
    ) || null;
  }

  function findOverviewCard(title) {
    const roots =
      qsa('[data-page="overview"]');

    for (const root of roots) {
      const heading =
        qsa("h2,h3,h4,strong", root)
          .find(
            (node) =>
              node.textContent.trim()
              === title
          );

      if (!heading) {
        continue;
      }

      return (
        heading.closest("article")
        || heading.closest("section")
        || heading.parentElement
      );
    }

    return null;
  }

  function ensureSetupSteps(onboarding) {
    if (
      !onboarding
      || qs(
        ".overview-setup-steps",
        onboarding
      )
    ) {
      return;
    }

    const steps =
      document.createElement("div");

    steps.className =
      "overview-setup-steps";

    const content = [
      [
        "01",
        "Shared workspace",
        "Create or select the organization that will own procurement activity."
      ],
      [
        "02",
        "Company intelligence",
        "Add your company, products and search keywords for relevant matching."
      ],
      [
        "03",
        "Global discovery",
        "Search connected procurement sources and review preliminary fit."
      ],
    ];

    content.forEach(
      ([number, title, copy]) => {
        const item =
          document.createElement("article");

        const index =
          document.createElement("span");

        const heading =
          document.createElement("strong");

        const paragraph =
          document.createElement("p");

        index.className =
          "overview-step-index";

        index.textContent =
          number;

        heading.textContent =
          title;

        paragraph.textContent =
          copy;

        item.append(
          index,
          heading,
          paragraph
        );

        steps.append(item);
      }
    );

    const button =
      qs(
        "button,a",
        onboarding
      );

    if (button) {
      button.before(steps);
    } else {
      onboarding.append(steps);
    }
  }

  function normalizeWorkspaceLabels() {
    qsa(
      ".workspace-context option"
    ).forEach(
      (option) => {
        option.textContent =
          option.textContent
            .replace(
              /\s\?\s/g,
              " \u00b7 "
            );
      }
    );
  }

  function updateOverview() {
    /* OVERVIEW PAGE SCOPE FIX */
    const currentPage =
      location.hash.slice(1) || "overview";

    if (currentPage !== "overview") {
      document.body.classList.remove(
        "overview-no-company"
      );
      return;
    }

    const welcome =
      qs(".overview-welcome");

    const metrics =
      qs(".overview-metrics");

    const onboarding =
      document.getElementById(
        "onboarding"
      );

    const companyLabel =
      document.getElementById(
        "activeCompanyLabel"
      );

    const noCompany =
      !companyLabel
      || /no active company/i.test(
        companyLabel.textContent
      );

    document.body.classList.toggle(
      "overview-no-company",
      noCompany
    );

    normalizeWorkspaceLabels();

    const review =
      findOverviewBlock(
        "Your next review starts here."
      );

    if (review) {
      review.classList.add(
        "overview-review-panel"
      );
    }

    if (onboarding) {
      onboarding.classList.add(
        "overview-onboarding-v2"
      );

      ensureSetupSteps(
        onboarding
      );
    }

    const monitoring =
      findOverviewCard(
        "Monitoring"
      );

    const companies =
      findOverviewCard(
        "Companies"
      );

    if (monitoring) {
      monitoring.classList.add(
        "overview-compact-card"
      );
    }

    if (companies) {
      companies.classList.add(
        "overview-compact-card"
      );
    }

    if (
      monitoring
      && companies
      && monitoring.parentElement
         === companies.parentElement
    ) {
      monitoring.parentElement
        .classList.add(
          "overview-secondary-grid"
        );
    }

    if (!welcome) {
      return;
    }

    const heading =
      qs("h2", welcome);

    const subtitle =
      qs("p", welcome);

    const buttons =
      qsa("a", welcome);

    const primary =
      buttons.find(
        (button) =>
          button.classList.contains(
            "primary"
          )
      ) || buttons[0];

    const secondary =
      buttons.find(
        (button) =>
          button !== primary
      );

    if (heading) {
      if (
        !heading.dataset
          .overviewOriginal
      ) {
        heading.dataset
          .overviewOriginal =
          heading.textContent;
      }

      heading.textContent =
        noCompany
          ? "Build your procurement workspace."
          : heading.dataset
              .overviewOriginal;
    }

    if (subtitle) {
      if (
        !subtitle.dataset
          .overviewOriginal
      ) {
        subtitle.dataset
          .overviewOriginal =
          subtitle.textContent;
      }

      subtitle.textContent =
        noCompany
          ? (
              "Set up your organization and "
              + "company profile before running "
              + "global opportunity discovery."
            )
          : subtitle.dataset
              .overviewOriginal;
    }

    if (primary) {
      if (
        !primary.dataset
          .overviewText
      ) {
        primary.dataset
          .overviewText =
          primary.textContent;

        primary.dataset
          .overviewHref =
          primary.getAttribute(
            "href"
          ) || "#discover";
      }

      if (noCompany) {
        primary.textContent =
          "Set up workspace \u2192";

        primary.setAttribute(
          "href",
          "#team"
        );
      } else {
        primary.textContent =
          primary.dataset
            .overviewText;

        primary.setAttribute(
          "href",
          primary.dataset
            .overviewHref
        );
      }
    }

    if (secondary) {
      secondary.hidden =
        noCompany;
    }

    if (metrics) {
      metrics.setAttribute(
        "aria-hidden",
        noCompany
          ? "true"
          : "false"
      );
    }
  }

  function mountOverviewV2() {
    updateOverview();

    window.addEventListener(
      "workspace-context",
      () => {
        window.setTimeout(
          updateOverview,
          0
        );
      }
    );

    window.addEventListener(
      "hashchange",
      () => {
        window.setTimeout(
          updateOverview,
          0
        );
      }
    );
  }

  if (
    document.readyState
    === "loading"
  ) {
    document.addEventListener(
      "DOMContentLoaded",
      mountOverviewV2,
      {
        once: true,
      }
    );
  } else {
    mountOverviewV2();
  }
})();
/* VALYQON DISCOVERY FILTER CATALOG V2 */
(function () {
  "use strict";

  const SOURCES = [
    ["eis", "Russia - EIS"],
    ["ted", "European Union - TED"],
    ["sam_gov", "United States - SAM.gov"],
    ["uk_fts", "United Kingdom - Find a Tender"],
    ["canada_buys", "Canada - CanadaBuys"],
    ["austender", "Australia - AusTender"],
    ["nz_gets", "New Zealand - GETS"],
    ["za_etenders", "South Africa - eTenders"],
    ["india_cppp", "India - CPPP"],
    ["kz_goszakup", "Kazakhstan - Goszakup"]
  ];

  const CURRENCIES = [
    ["EUR", "EUR - Euro"],
    ["USD", "USD - US Dollar"],
    ["GBP", "GBP - British Pound"],
    ["RUB", "RUB - Russian Ruble"],
    ["KZT", "KZT - Kazakhstani Tenge"],
    ["BYN", "BYN - Belarusian Ruble"],
    ["UZS", "UZS - Uzbekistani Som"],
    ["AZN", "AZN - Azerbaijani Manat"],
    ["AMD", "AMD - Armenian Dram"],
    ["GEL", "GEL - Georgian Lari"],
    ["KGS", "KGS - Kyrgyzstani Som"],
    ["TJS", "TJS - Tajikistani Somoni"],
    ["MDL", "MDL - Moldovan Leu"],
    ["TRY", "TRY - Turkish Lira"],
    ["CAD", "CAD - Canadian Dollar"],
    ["AUD", "AUD - Australian Dollar"],
    ["NZD", "NZD - New Zealand Dollar"],
    ["INR", "INR - Indian Rupee"],
    ["ZAR", "ZAR - South African Rand"],
    ["CNY", "CNY - Chinese Yuan"],
    ["JPY", "JPY - Japanese Yen"],
    ["CHF", "CHF - Swiss Franc"],
    ["AED", "AED - UAE Dirham"],
    ["SAR", "SAR - Saudi Riyal"]
  ];

  function findSelectByExistingOption(text) {
    return Array.from(
      document.querySelectorAll("select")
    ).find(
      (select) =>
        Array.from(select.options).some(
          (option) =>
            option.textContent.trim() === text
        )
    ) || null;
  }

  function ensureOptions(select, entries) {
    if (!select) {
      return false;
    }

    const currentValue = select.value;

    const existing = new Set(
      Array.from(select.options).map(
        (option) => option.value
      )
    );

    let added = 0;

    entries.forEach(
      ([value, label]) => {
        if (existing.has(value)) {
          return;
        }

        const option =
          document.createElement("option");

        option.value = value;
        option.textContent = label;

        select.appendChild(option);

        existing.add(value);
        added += 1;
      }
    );

    if (
      Array.from(select.options).some(
        (option) =>
          option.value === currentValue
      )
    ) {
      select.value = currentValue;
    }

    return added > 0;
  }

  function repairWorkspaceLabels() {
    document
      .querySelectorAll(
        ".workspace-context option"
      )
      .forEach(
        (option) => {
          option.textContent =
            option.textContent.replace(
              /\s\?\s/g,
              " \u00b7 "
            );
        }
      );
  }

  function hydrateDiscoveryCatalog() {
    repairWorkspaceLabels();

    const page =
      location.hash.slice(1)
      || "overview";

    if (page !== "discover") {
      return;
    }

    const sourceSelect =
      findSelectByExistingOption(
        "All fetched sources"
      );

    const currencySelect =
      findSelectByExistingOption(
        "All currencies"
      );

    ensureOptions(
      sourceSelect,
      SOURCES
    );

    ensureOptions(
      currencySelect,
      CURRENCIES
    );

    if (sourceSelect) {
      sourceSelect.dataset
        .valyqonCatalog = "ready";
    }

    if (currencySelect) {
      currencySelect.dataset
        .valyqonCatalog = "ready";
    }
  }

  function scheduleHydration() {
    window.setTimeout(
      hydrateDiscoveryCatalog,
      0
    );

    window.setTimeout(
      hydrateDiscoveryCatalog,
      150
    );

    window.setTimeout(
      hydrateDiscoveryCatalog,
      500
    );
  }

  if (
    document.readyState === "loading"
  ) {
    document.addEventListener(
      "DOMContentLoaded",
      scheduleHydration,
      { once: true }
    );
  } else {
    scheduleHydration();
  }

  window.addEventListener(
    "hashchange",
    scheduleHydration
  );

  window.addEventListener(
    "workspace-context",
    scheduleHydration
  );

  const observer =
    new MutationObserver(
      () => {
        if (
          (
            location.hash.slice(1)
            || "overview"
          ) === "discover"
        ) {
          window.setTimeout(
            hydrateDiscoveryCatalog,
            0
          );
        }
      }
    );

  if (document.body) {
    observer.observe(
      document.body,
      {
        childList: true,
        subtree: true
      }
    );
  }

  window.__valyqonDiscoveryCatalogV2 = {
    hydrate: hydrateDiscoveryCatalog,
    sources: SOURCES.length,
    currencies: CURRENCIES.length
  };
})();
