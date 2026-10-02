"""Self-contained web dashboard for the TenderLens single-node MVP."""

from __future__ import annotations

from html import escape

from app import __version__


def dashboard_html() -> str:
    """Render the dashboard shell.

    Protected API requests are made by the browser with an API key supplied by
    the operator. The key is kept in sessionStorage only and is never embedded
    into the generated HTML.
    """

    version = escape(__version__)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  <title>TenderLens AI Dashboard</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #0b1020;
      --panel: #121a2f;
      --panel-2: #18223b;
      --text: #f4f7fb;
      --muted: #9eabc4;
      --line: #2b3653;
      --accent: #79a7ff;
      --good: #60d394;
      --warn: #ffcf70;
      --bad: #ff7b7b;
      --shadow: 0 18px 48px rgba(0,0,0,.22);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top right, rgba(80,120,220,.16), transparent 34rem),
        var(--bg);
      color: var(--text);
    }}
    a {{ color: var(--accent); }}
    button, input {{
      font: inherit;
    }}
    button {{
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: .65rem .9rem;
      background: var(--panel-2);
      color: var(--text);
      cursor: pointer;
    }}
    button:hover {{ filter: brightness(1.12); }}
    button.primary {{
      background: var(--accent);
      color: #081126;
      border-color: transparent;
      font-weight: 700;
    }}
    button:disabled {{ opacity: .55; cursor: wait; }}
    input {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: #0e1628;
      color: var(--text);
      padding: .7rem .8rem;
    }}
    .shell {{ max-width: 1240px; margin: 0 auto; padding: 24px; }}
    .topbar {{
      display: flex; align-items: center; justify-content: space-between;
      gap: 16px; margin-bottom: 22px;
    }}
    .brand h1 {{ margin: 0; font-size: clamp(1.55rem, 3vw, 2.25rem); }}
    .brand p {{ margin: 5px 0 0; color: var(--muted); }}
    .badge {{
      display: inline-flex; align-items: center; gap: 6px;
      border: 1px solid var(--line); border-radius: 999px;
      padding: .35rem .65rem; color: var(--muted); background: var(--panel);
      white-space: nowrap;
    }}
    .panel {{
      background: rgba(18,26,47,.94);
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 18px;
      box-shadow: var(--shadow);
    }}
    .connect-grid {{
      display: grid; grid-template-columns: 1fr 2fr auto; gap: 10px; align-items: end;
    }}
    .field label {{ display: block; color: var(--muted); font-size: .82rem; margin: 0 0 6px; }}
    .note {{ color: var(--muted); font-size: .82rem; line-height: 1.45; margin: 10px 0 0; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(12, 1fr);
      gap: 16px;
      margin-top: 16px;
    }}
    .span-4 {{ grid-column: span 4; }}
    .span-5 {{ grid-column: span 5; }}
    .span-7 {{ grid-column: span 7; }}
    .span-8 {{ grid-column: span 8; }}
    .span-12 {{ grid-column: span 12; }}
    .panel h2 {{
      margin: 0 0 14px; font-size: 1rem; letter-spacing: .02em;
      display: flex; align-items: center; justify-content: space-between; gap: 12px;
    }}
    .metric {{
      font-size: 1.7rem;
      font-weight: 760;
      margin: 2px 0 4px;
    }}
    .muted {{ color: var(--muted); }}
    .chips {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .chip {{
      border: 1px solid var(--line); border-radius: 999px;
      padding: .32rem .58rem; font-size: .78rem;
    }}
    .chip.good {{ color: var(--good); }}
    .chip.warn {{ color: var(--warn); }}
    .company, .row {{
      padding: 12px 0;
      border-top: 1px solid var(--line);
    }}
    .company:first-child, .row:first-child {{ border-top: 0; padding-top: 0; }}
    .company-head, .row-head {{
      display: flex; justify-content: space-between; align-items: flex-start; gap: 10px;
    }}
    .title {{ font-weight: 700; }}
    .sub {{ color: var(--muted); font-size: .82rem; margin-top: 4px; line-height: 1.45; }}
    .active {{ color: var(--good); font-weight: 700; }}
    .toolbar {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .empty {{
      padding: 18px; border: 1px dashed var(--line); border-radius: 12px;
      color: var(--muted); text-align: center;
    }}
    .error {{
      border: 1px solid rgba(255,123,123,.45);
      color: #ffd0d0; background: rgba(255,123,123,.08);
      padding: 10px 12px; border-radius: 10px; margin-top: 10px;
    }}
    .success {{
      border: 1px solid rgba(96,211,148,.4);
      color: #bdf2d3; background: rgba(96,211,148,.08);
      padding: 10px 12px; border-radius: 10px; margin-top: 10px;
    }}
    .price {{ white-space: nowrap; font-variant-numeric: tabular-nums; }}
    .scan-results {{ max-height: 520px; overflow: auto; padding-right: 4px; }}
    footer {{ color: var(--muted); font-size: .78rem; padding: 22px 0 8px; text-align: center; }}
    @media (max-width: 900px) {{
      .connect-grid {{ grid-template-columns: 1fr; }}
      .span-4, .span-5, .span-7, .span-8, .span-12 {{ grid-column: span 12; }}
      .topbar {{ align-items: flex-start; flex-direction: column; }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <div class="topbar">
      <div class="brand">
        <h1>TenderLens AI</h1>
        <p>Procurement intelligence dashboard</p>
      </div>
      <div class="toolbar">
        <span class="badge">v{version}</span>
        <a href="/docs"><button type="button">API Docs</button></a>
        <button type="button" onclick="refreshAll()">Refresh</button>
      </div>
    </div>

    <section class="panel">
      <div class="connect-grid">
        <div class="field">
          <label for="ownerId">Owner / Telegram user ID</label>
          <input id="ownerId" inputmode="numeric" autocomplete="off" placeholder="123456789">
        </div>
        <div class="field">
          <label for="apiKey">API key</label>
          <input id="apiKey" type="password" autocomplete="off" placeholder="X-API-Key">
        </div>
        <button id="connectButton" class="primary" type="button" onclick="connect()">Connect</button>
      </div>
      <p class="note">
        Local MVP dashboard. The API key is stored only in this browser tab's sessionStorage.
        Do not expose this dashboard directly to the public internet without a real authentication layer.
      </p>
      <div id="connectionMessage"></div>
    </section>

    <section class="grid">
      <article class="panel span-4">
        <h2>System <span id="healthBadge" class="chip">checking</span></h2>
        <div id="healthVersion" class="metric">—</div>
        <div class="muted">TenderLens API</div>
        <div id="components" class="chips" style="margin-top:14px"></div>
      </article>

      <article class="panel span-4">
        <h2>Monitoring</h2>
        <div id="monitorCompany" class="metric">—</div>
        <div id="monitorDetails" class="muted">Connect to load status.</div>
      </article>

      <article class="panel span-4">
        <h2>Companies</h2>
        <div id="companyCount" class="metric">—</div>
        <div class="muted">Profiles for the current owner</div>
      </article>

      <article class="panel span-5">
        <h2>
          Company workspaces
          <button type="button" onclick="loadCompanies()">Reload</button>
        </h2>
        <div id="companies"><div class="empty">Connect to load company profiles.</div></div>
      </article>

      <article class="panel span-7">
        <h2>
          Recent analyzed documents
          <button type="button" onclick="loadTenders()">Reload</button>
        </h2>
        <div id="tenders"><div class="empty">Connect to load analysis history.</div></div>
      </article>

      <article class="panel span-12">
        <h2>
          Live EIS scan
          <button id="scanButton" class="primary" type="button" onclick="scanEis()">Scan now</button>
        </h2>
        <p class="note" style="margin-top:-5px">
          Runs the same company-aware monitoring scan used by TenderLens. Deduplication still applies,
          so a repeated scan may legitimately return zero new notices.
        </p>
        <div id="scanResults" class="scan-results"><div class="empty">Run a scan to see new matching notices.</div></div>
      </article>
    </section>

    <footer>TenderLens AI v{version} · Phase 16 local dashboard</footer>
  </main>

<script>
const state = {{
  ownerId: sessionStorage.getItem("tenderlens.ownerId") || "",
  apiKey: sessionStorage.getItem("tenderlens.apiKey") || ""
}};

document.getElementById("ownerId").value = state.ownerId;
document.getElementById("apiKey").value = state.apiKey;

function esc(value) {{
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}}

function money(value, currency="RUB") {{
  if (value === null || value === undefined) return "Price not specified";
  return new Intl.NumberFormat("ru-RU", {{maximumFractionDigits: 2}}).format(value) + " " + esc(currency || "");
}}

function setMessage(text, kind="success") {{
  document.getElementById("connectionMessage").innerHTML =
    text ? `<div class="${{kind}}">${{esc(text)}}</div>` : "";
}}

function credentials() {{
  const owner = Number(document.getElementById("ownerId").value.trim());
  const key = document.getElementById("apiKey").value.trim();
  if (!Number.isInteger(owner) || owner <= 0) throw new Error("Enter a positive owner / Telegram user ID.");
  if (!key) throw new Error("Enter the API key.");
  state.ownerId = owner;
  state.apiKey = key;
  sessionStorage.setItem("tenderlens.ownerId", String(owner));
  sessionStorage.setItem("tenderlens.apiKey", key);
  return {{owner, key}};
}}

async function apiFetch(path, options={{}}) {{
  const {{key}} = credentials();
  const headers = new Headers(options.headers || {{}});
  headers.set("X-API-Key", key);
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const response = await fetch(path, {{...options, headers}});
  if (!response.ok) {{
    let detail = `${{response.status}} ${{response.statusText}}`;
    try {{
      const body = await response.json();
      if (body.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    }} catch (_) {{}}
    throw new Error(detail);
  }}
  return response.json();
}}

async function loadHealth() {{
  const response = await fetch("/health");
  const data = await response.json();
  document.getElementById("healthVersion").textContent = "v" + data.version;
  const badge = document.getElementById("healthBadge");
  badge.textContent = data.status;
  badge.className = "chip " + (data.status === "ok" ? "good" : "warn");
  document.getElementById("components").innerHTML = Object.entries(data.components || {{}})
    .map(([name, value]) => `<span class="chip ${{value === "ready" ? "good" : "warn"}}">${{esc(name)}}: ${{esc(value)}}</span>`)
    .join("");
}}

async function loadCompanies() {{
  const {{owner}} = credentials();
  const items = await apiFetch(`/api/v1/companies?owner_user_id=${{owner}}`);
  document.getElementById("companyCount").textContent = String(items.length);
  const root = document.getElementById("companies");
  if (!items.length) {{
    root.innerHTML = '<div class="empty">No company profiles yet. Create one in Telegram with /company_setup.</div>';
    return;
  }}
  root.innerHTML = items.map(item => {{
    const p = item.profile || {{}};
    const words = (p.search_keywords || p.product_keywords || []).slice(0, 5).join(", ") || "No keywords";
    return `<div class="company">
      <div class="company-head">
        <div>
          <div class="title">${{esc(item.name)}} ${{item.is_active ? '<span class="active">· ACTIVE</span>' : ""}}</div>
          <div class="sub">#${{item.id}} · ${{esc(p.business_mode || "sell")}}<br>${{esc(words)}}</div>
        </div>
        ${{item.is_active ? "" : `<button type="button" onclick="activateCompany(${{item.id}})">Activate</button>`}}
      </div>
    </div>`;
  }}).join("");
}}

async function activateCompany(id) {{
  const {{owner}} = credentials();
  await apiFetch(`/api/v1/companies/${{id}}/activate`, {{
    method: "POST",
    body: JSON.stringify({{owner_user_id: owner}})
  }});
  setMessage("Active company changed.");
  await Promise.all([loadCompanies(), loadMonitoring()]);
}}

async function loadMonitoring() {{
  const {{owner}} = credentials();
  const data = await apiFetch(`/api/v1/monitoring/status?owner_user_id=${{owner}}`);
  document.getElementById("monitorCompany").textContent = data.active_company || "No active profile";
  document.getElementById("monitorDetails").innerHTML =
    `${{data.subscription_enabled ? "Notifications ON" : "Notifications OFF"}} · ` +
    `${{esc(data.feed_mode)}} · ${{data.rss_feeds}} feed(s) · every ${{data.interval_seconds}} sec`;
}}

async function loadTenders() {{
  const {{owner}} = credentials();
  const items = await apiFetch(`/api/v1/tenders?owner_user_id=${{owner}}&limit=20`);
  const root = document.getElementById("tenders");
  if (!items.length) {{
    root.innerHTML = '<div class="empty">No analyzed PDF tenders stored for this owner yet.</div>';
    return;
  }}
  root.innerHTML = items.map(item => `<div class="row">
    <div class="row-head">
      <div>
        <div class="title">${{esc(item.title || item.source_filename || "Tender")}}</div>
        <div class="sub">
          ${{item.tender_number ? "№ " + esc(item.tender_number) + " · " : ""}}
          ${{esc(item.customer || "Customer not specified")}}<br>
          ${{item.fit_score === null || item.fit_score === undefined ? "No fit score" : "Fit score: " + esc(item.fit_score)}}
        </div>
      </div>
      <div class="price">${{money(item.initial_price, item.currency)}}</div>
    </div>
  </div>`).join("");
}}

async function scanEis() {{
  const button = document.getElementById("scanButton");
  const root = document.getElementById("scanResults");
  try {{
    button.disabled = true;
    button.textContent = "Scanning…";
    const {{owner}} = credentials();
    const items = await apiFetch("/api/v1/monitoring/scan", {{
      method: "POST",
      body: JSON.stringify({{owner_user_id: owner}})
    }});
    if (!items.length) {{
      root.innerHTML = '<div class="empty">No new matching notices. Previously seen notices are deduplicated.</div>';
      return;
    }}
    root.innerHTML = items.map(item => `<div class="row">
      <div class="row-head">
        <div>
          <div class="title">${{esc(item.title || item.tender_number || "EIS notice")}}</div>
          <div class="sub">${{esc((item.reasons || []).join(" · "))}}</div>
        </div>
        <div class="price">${{money(item.initial_price, item.currency)}}</div>
      </div>
      <div class="sub" style="margin-top:7px">
        <a href="${{esc(item.url)}}" target="_blank" rel="noopener noreferrer">Open on zakupki.gov.ru</a>
      </div>
    </div>`).join("");
  }} catch (error) {{
    root.innerHTML = `<div class="error">${{esc(error.message || error)}}</div>`;
  }} finally {{
    button.disabled = false;
    button.textContent = "Scan now";
  }}
}}

async function refreshAll() {{
  try {{
    await loadHealth();
    if (!state.ownerId || !state.apiKey) return;
    await Promise.all([loadCompanies(), loadMonitoring(), loadTenders()]);
  }} catch (error) {{
    setMessage(error.message || String(error), "error");
  }}
}}

async function connect() {{
  try {{
    credentials();
    setMessage("");
    await Promise.all([loadHealth(), loadCompanies(), loadMonitoring(), loadTenders()]);
    setMessage("Dashboard connected.");
  }} catch (error) {{
    setMessage(error.message || String(error), "error");
  }}
}}

loadHealth().catch(() => {{
  document.getElementById("healthBadge").textContent = "unavailable";
}});
if (state.ownerId && state.apiKey) connect();
</script>
</body>
</html>
"""


__all__ = ["dashboard_html"]
