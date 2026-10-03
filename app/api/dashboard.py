"""Authenticated browser dashboard for TenderLens."""
from __future__ import annotations

from html import escape

from app import __version__


def dashboard_html() -> str:
    version = escape(__version__)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow">
  <title>TenderLens AI Dashboard</title>
  <style>
    :root {{ color-scheme:dark; --bg:#08111f; --panel:#101c31; --panel2:#162641; --text:#f4f7fb; --muted:#9eacc4; --line:#293c5d; --accent:#79a7ff; --good:#60d394; --warn:#ffcf70; }}
    * {{ box-sizing:border-box; }} body {{ margin:0; font-family:Inter,system-ui,sans-serif; background:radial-gradient(circle at top right,rgba(80,120,220,.16),transparent 34rem),var(--bg); color:var(--text); }}
    a {{ color:var(--accent); }} button {{ font:inherit; border:1px solid var(--line); border-radius:10px; padding:.65rem .9rem; background:var(--panel2); color:var(--text); cursor:pointer; }}
    button.primary {{ background:var(--accent); color:#081126; border-color:transparent; font-weight:700; }} button:disabled {{ opacity:.55; }}
    .shell {{ max-width:1240px; margin:auto; padding:24px; }} .top {{ display:flex; justify-content:space-between; gap:16px; align-items:center; margin-bottom:20px; }} h1 {{ margin:0; }} .muted {{ color:var(--muted); }}
    .toolbar {{ display:flex; gap:8px; flex-wrap:wrap; align-items:center; }} .badge {{ border:1px solid var(--line); border-radius:999px; padding:.35rem .65rem; color:var(--muted); background:var(--panel); }}
    .grid {{ display:grid; grid-template-columns:repeat(12,1fr); gap:16px; }} .p {{ background:var(--panel); border:1px solid var(--line); border-radius:16px; padding:18px; }} .s4 {{ grid-column:span 4; }} .s5 {{ grid-column:span 5; }} .s7 {{ grid-column:span 7; }} .s12 {{ grid-column:span 12; }}
    .p h2 {{ margin:0 0 14px; font-size:1rem; display:flex; justify-content:space-between; gap:10px; }} .metric {{ font-size:1.7rem; font-weight:760; }} .chips {{ display:flex; gap:8px; flex-wrap:wrap; margin-top:12px; }} .chip {{ border:1px solid var(--line); border-radius:999px; padding:.3rem .55rem; font-size:.78rem; }} .good {{ color:var(--good); }} .warn {{ color:var(--warn); }}
    .row {{ padding:12px 0; border-top:1px solid var(--line); }} .row:first-child {{ border-top:0; padding-top:0; }} .head {{ display:flex; justify-content:space-between; gap:10px; }} .title {{ font-weight:700; }} .sub {{ color:var(--muted); font-size:.82rem; margin-top:4px; line-height:1.45; }} .active {{ color:var(--good); font-weight:700; }}
    .empty {{ padding:18px; border:1px dashed var(--line); border-radius:12px; color:var(--muted); text-align:center; }} .error {{ padding:10px 12px; border:1px solid rgba(255,123,123,.45); border-radius:10px; color:#ffd0d0; background:rgba(255,123,123,.08); }}
    footer {{ text-align:center; color:var(--muted); font-size:.78rem; padding:22px 0; }} @media(max-width:900px) {{ .s4,.s5,.s7,.s12 {{ grid-column:span 12; }} .top {{ align-items:flex-start; flex-direction:column; }} }}
  </style>
</head>
<body>
<main class="shell">
  <div class="top">
    <div><h1>TenderLens AI</h1><div class="muted">Procurement intelligence dashboard</div></div>
    <div class="toolbar"><span id="email" class="badge">Loading account…</span><span class="badge">v{version}</span><a href="/docs"><button>API Docs</button></a><button onclick="refreshAll()">Refresh</button><button onclick="logout()">Sign out</button></div>
  </div>
  <section class="grid">
    <article class="p s4"><h2>System <span id="healthBadge" class="chip">checking</span></h2><div id="healthVersion" class="metric">—</div><div id="components" class="chips"></div></article>
    <article class="p s4"><h2>Monitoring</h2><div id="monitorCompany" class="metric">—</div><div id="monitorDetails" class="muted">Loading…</div></article>
    <article class="p s4"><h2>Companies</h2><div id="companyCount" class="metric">—</div><div class="muted">Profiles in your account</div></article>
    <article class="p s5"><h2>Company workspaces <button onclick="loadCompanies()">Reload</button></h2><div id="companies"><div class="empty">Loading…</div></div></article>
    <article class="p s7"><h2>Recent analyzed documents <button onclick="loadTenders()">Reload</button></h2><div id="tenders"><div class="empty">Loading…</div></div></article>
    <article class="p s12"><h2>Live EIS scan <button id="scanButton" class="primary" onclick="scanEis()">Scan now</button></h2><div id="scanResults"><div class="empty">Run a scan to see new matching notices.</div></div></article>
  </section>
  <footer>TenderLens AI v{version} · authenticated web workspace</footer>
</main>
<script>
const state={{ownerId:null,hasActiveCompany:false}};
const esc=v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
async function read(r){{if(r.status===401){{location.replace('/login');throw new Error('Authentication required')}}if(!r.ok){{let d=`${{r.status}} ${{r.statusText}}`;try{{const j=await r.json();if(j.detail)d=typeof j.detail==='string'?j.detail:JSON.stringify(j.detail)}}catch(_){{}}throw new Error(d)}}return r.status===204?null:r.json()}}
async function api(path,opt={{}}){{const h=new Headers(opt.headers||{{}});if(opt.body&&!(opt.body instanceof FormData))h.set('Content-Type','application/json');return read(await fetch(path,{{...opt,headers:h,credentials:'same-origin',cache:'no-store'}}))}}
async function loadAccount(){{const a=await api('/api/v1/auth/me');state.ownerId=a.owner_user_id;document.getElementById('email').textContent=a.email}}
function owner(){{if(!Number.isInteger(state.ownerId))throw new Error('Account owner unavailable');return state.ownerId}}
async function loadHealth(){{const d=await (await fetch('/health',{{cache:'no-store'}})).json();document.getElementById('healthVersion').textContent='v'+d.version;const b=document.getElementById('healthBadge');b.textContent=d.status;b.className='chip '+(d.status==='ok'?'good':'warn');document.getElementById('components').innerHTML=Object.entries(d.components||{{}}).map(([k,v])=>`<span class="chip ${{v==='ready'?'good':'warn'}}">${{esc(k)}}: ${{esc(v)}}</span>`).join('')}}
async function loadCompanies(){{const items=await api(`/api/v1/companies?owner_user_id=${{owner()}}`);document.getElementById('companyCount').textContent=items.length;const r=document.getElementById('companies');if(!items.length){{r.innerHTML='<div class="empty">No company profiles are linked to this account yet.</div>';return}}r.innerHTML=items.map(i=>`<div class="row"><div class="head"><div><div class="title">${{esc(i.name)}} ${{i.is_active?'<span class="active">· ACTIVE</span>':''}}</div><div class="sub">#${{i.id}} · ${{esc(i.profile?.business_mode||'sell')}}</div></div>${{i.is_active?'':`<button onclick="activateCompany(${{i.id}})">Activate</button>`}}</div></div>`).join('')}}
async function activateCompany(id){{await api(`/api/v1/companies/${{id}}/activate`,{{method:'POST',body:JSON.stringify({{owner_user_id:owner()}})}});await Promise.all([loadCompanies(),loadMonitoring()])}}
async function loadMonitoring(){{const d=await api(`/api/v1/monitoring/status?owner_user_id=${{owner()}}`);state.hasActiveCompany=Boolean(d.active_company);document.getElementById('monitorCompany').textContent=d.active_company||'No active company';document.getElementById('monitorDetails').textContent=state.hasActiveCompany?`${{d.subscription_enabled?'Notifications ON':'Notifications OFF'}} · ${{d.feed_mode}} · ${{d.rss_feeds}} feed(s)`:'Create a company profile to start monitoring.';const b=document.getElementById('scanButton');b.disabled=!state.hasActiveCompany;b.title=state.hasActiveCompany?'':'Create a company profile first'}}
async function loadTenders(){{const items=await api(`/api/v1/tenders?owner_user_id=${{owner()}}&limit=20`);const r=document.getElementById('tenders');if(!items.length){{r.innerHTML='<div class="empty">No analyzed PDF tenders stored for this account yet.</div>';return}}r.innerHTML=items.map(i=>`<div class="row"><div class="title">${{esc(i.title||i.source_filename||'Tender')}}</div><div class="sub">${{esc(i.customer||'Customer not specified')}} · ${{i.fit_score??'No fit score'}}</div></div>`).join('')}}
async function scanEis(){{const b=document.getElementById('scanButton'),r=document.getElementById('scanResults');try{{if(!state.hasActiveCompany){{r.innerHTML='<div class="empty">Create a company profile before running monitoring.</div>';return}}b.disabled=true;b.textContent='Scanning…';const items=await api('/api/v1/monitoring/scan',{{method:'POST',body:JSON.stringify({{owner_user_id:owner()}})}});r.innerHTML=items.length?items.map(i=>`<div class="row"><div class="title">${{esc(i.title||'EIS notice')}}</div><div class="sub">${{esc((i.reasons||[]).join(' · '))}} · <a href="${{esc(i.url)}}" target="_blank" rel="noopener noreferrer">Open notice</a></div></div>`).join(''):'<div class="empty">No new matching notices.</div>'}}catch(e){{r.innerHTML=`<div class="error">${{esc(e.message||e)}}</div>`}}finally{{b.disabled=false;b.textContent='Scan now'}}}}
async function refreshAll(){{await loadAccount();await Promise.all([loadHealth(),loadCompanies(),loadMonitoring(),loadTenders()])}}
async function logout(){{try{{await api('/api/v1/auth/logout',{{method:'POST'}})}}finally{{location.replace('/login')}}}}
refreshAll().catch(e=>{{if(!String(e.message||e).includes('Authentication required'))document.getElementById('companies').innerHTML=`<div class="error">${{esc(e.message||e)}}</div>`}});
</script>
</body>
</html>"""


__all__ = ["dashboard_html"]
