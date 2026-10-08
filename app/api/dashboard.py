"""Authenticated browser dashboard for VALYQON AI."""

from __future__ import annotations

from html import escape

from app import __version__
from .organization_ui import ORGANIZATION_SCRIPT
from .telegram_ui import TELEGRAM_SCRIPT
from .saas_shell import shell_html


def _dashboard_html() -> str:
    version = escape(__version__)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow">
  <title>VALYQON AI Dashboard</title>
  <style>
    :root {{ color-scheme:dark; --bg:#08111f; --panel:#101c31; --panel2:#162641; --text:#f4f7fb; --muted:#9eacc4; --line:#293c5d; --accent:#79a7ff; --good:#60d394; --warn:#ffcf70; }}
    * {{ box-sizing:border-box; }} body {{ margin:0; font-family:Inter,system-ui,sans-serif; background:radial-gradient(circle at top right,rgba(80,120,220,.16),transparent 34rem),var(--bg); color:var(--text); }}
    a {{ color:var(--accent); }} button,input,select,textarea {{ font:inherit; }}
    button {{ border:1px solid var(--line); border-radius:10px; padding:.65rem .9rem; background:var(--panel2); color:var(--text); cursor:pointer; }}
    button.primary {{ background:var(--accent); color:#081126; border-color:transparent; font-weight:700; }} button:disabled {{ opacity:.55; cursor:not-allowed; }}
    input,select,textarea {{ width:100%; border:1px solid var(--line); border-radius:10px; padding:.7rem .8rem; background:#0b1728; color:var(--text); }}
    textarea {{ resize:vertical; min-height:84px; }}
    label {{ display:block; color:var(--muted); font-size:.82rem; margin-bottom:6px; }}
    .shell {{ max-width:1240px; margin:auto; padding:24px; }} .top {{ display:flex; justify-content:space-between; gap:16px; align-items:center; margin-bottom:20px; }} h1 {{ margin:0; }} .muted {{ color:var(--muted); }}
    .toolbar {{ display:flex; gap:8px; flex-wrap:wrap; align-items:center; }} .badge {{ border:1px solid var(--line); border-radius:999px; padding:.35rem .65rem; color:var(--muted); background:var(--panel); }}
    .grid {{ display:grid; grid-template-columns:repeat(12,1fr); gap:16px; }} .p {{ background:var(--panel); border:1px solid var(--line); border-radius:16px; padding:18px; }} .s4 {{ grid-column:span 4; }} .s5 {{ grid-column:span 5; }} .s6 {{ grid-column:span 6; }} .s7 {{ grid-column:span 7; }} .s12 {{ grid-column:span 12; }}
    .p h2 {{ margin:0 0 14px; font-size:1rem; display:flex; justify-content:space-between; gap:10px; align-items:center; }} .metric {{ font-size:1.7rem; font-weight:760; }} .chips {{ display:flex; gap:8px; flex-wrap:wrap; margin-top:12px; }} .chip {{ border:1px solid var(--line); border-radius:999px; padding:.3rem .55rem; font-size:.78rem; }} .good {{ color:var(--good); }} .warn {{ color:var(--warn); }}
    .row {{ padding:12px 0; border-top:1px solid var(--line); }} .row:first-child {{ border-top:0; padding-top:0; }} .head {{ display:flex; justify-content:space-between; gap:10px; }} .title {{ font-weight:700; }} .sub {{ color:var(--muted); font-size:.82rem; margin-top:4px; line-height:1.45; }} .active {{ color:var(--good); font-weight:700; }}
    .empty {{ padding:18px; border:1px dashed var(--line); border-radius:12px; color:var(--muted); text-align:center; }} .error {{ padding:10px 12px; border:1px solid rgba(255,123,123,.45); border-radius:10px; color:#ffd0d0; background:rgba(255,123,123,.08); }}
    .success {{ padding:10px 12px; border:1px solid rgba(96,211,148,.4); border-radius:10px; color:#bdf2d3; background:rgba(96,211,148,.08); margin-bottom:12px; }}
    .form-grid {{ display:grid; grid-template-columns:repeat(12,1fr); gap:12px; }} .f4 {{ grid-column:span 4; }} .f6 {{ grid-column:span 6; }} .f12 {{ grid-column:span 12; }}
    .help {{ color:var(--muted); font-size:.76rem; margin-top:5px; line-height:1.4; }} .actions {{ display:flex; gap:8px; justify-content:flex-end; margin-top:14px; flex-wrap:wrap; }}
    .hidden {{ display:none; }}
    footer {{ text-align:center; color:var(--muted); font-size:.78rem; padding:22px 0; }} @media(max-width:900px) {{ .s4,.s5,.s6,.s7,.s12,.f4,.f6,.f12 {{ grid-column:span 12; }} .top {{ align-items:flex-start; flex-direction:column; }} }}
  </style>
</head>
<body>
<main class="shell">
  <div class="top">
    <div><h1>VALYQON AI</h1><div class="muted">AI Procurement Intelligence Platform</div></div>
    <div class="toolbar"><span id="email" class="badge">Loading account…</span><span class="badge">v{version}</span><a href="/docs" class="badge">API Docs</a><button onclick="refreshAll()">Refresh</button><button onclick="logout()">Sign out</button></div>
  </div>

  <section class="grid">
    <article class="p s4"><h2>System <span id="healthBadge" class="chip">checking</span></h2><div id="healthVersion" class="metric">—</div><div id="components" class="chips"></div></article>
    <article class="p s4"><h2>Monitoring</h2><div id="monitorCompany" class="metric">—</div><div id="monitorDetails" class="muted">Loading…</div></article>
    <article class="p s4"><h2>Companies</h2><div id="companyCount" class="metric">—</div><div id="companyScopeLabel" class="muted">Personal account workspace</div></article>

    <article class="p s12" id="telegramCard">
      <h2>Telegram <span id="telegramStatus" class="chip">Checking…</span></h2>
      <p class="muted">Connect your Telegram account to use the same VALYQON AI workspace in the bot and on the web.</p>
      <div class="toolbar"><button id="connectTelegram" class="primary" disabled onclick="connectTelegram()">Connect Telegram</button>
      <a id="telegramOpen" hidden target="_blank" rel="noopener noreferrer">Open Telegram</a></div>
      <p id="telegramMessage" class="sub" role="status" aria-live="polite"></p>
    </article>

    <article class="p s12" id="organizationCard">
      <h2>
        Team &amp; organizations
        <span class="chip"><span id="organizationCount">?</span> workspace(s)</span>
      </h2>

      <div class="form-grid">
        <div class="f6">
          <label for="organizationSelect">Organization to manage</label>
          <select id="organizationSelect" onchange="selectOrganization()">
            <option>Loading?</option>
          </select>
          <div class="help">
            This selector controls organization members and invitations.
            Existing personal company and tender cards remain unchanged in this checkpoint.
          </div>
        </div>

        <div class="f6">
          <label for="newOrganizationName">Create organization</label>
          <div class="toolbar">
            <input id="newOrganizationName"
                   maxlength="200"
                   placeholder="Example: AluTrade Team">
            <button id="createOrganizationButton"
                    onclick="createOrganization()">
              Create organization
            </button>
          </div>
        </div>
      </div>

      <div id="organizationMessage"></div>

      <div style="margin-top:18px">
        <div class="title" id="selectedOrganizationName">
          Loading?
        </div>
        <div class="sub">
          Organization members and pending invitations
        </div>
      </div>

      <div class="form-grid" style="margin-top:14px">
        <div class="f6">
          <h2>Members</h2>
          <div id="organizationMembers">
            <div class="empty">Loading?</div>
          </div>
        </div>

        <div class="f6">
          <h2>Pending invitations</h2>
          <div id="organizationInvitations">
            <div class="empty">Loading?</div>
          </div>
        </div>
      </div>

      <div id="organizationManagerControls"
           class="hidden"
           style="margin-top:18px">

        <div class="form-grid">
          <div class="f6">
            <label for="inviteEmail">Invite by email</label>
            <input id="inviteEmail"
                   type="email"
                   maxlength="254"
                   placeholder="colleague@company.com">
          </div>

          <div class="f6">
            <label for="inviteRole">Role</label>
            <select id="inviteRole">
              <option value="member">Member</option>
              <option value="viewer">Viewer</option>
              <option value="admin">Admin</option>
            </select>
          </div>
        </div>

        <div class="actions">
          <button id="inviteButton"
                  class="primary"
                  onclick="createOrganizationInvitation()">
            Create invitation
          </button>
        </div>

        <div id="inviteMessage"></div>

        <div id="inviteLinkRoot"
             class="hidden"
             style="margin-top:12px">
          <label for="inviteLink">One-time invitation link</label>

          <div class="toolbar">
            <input id="inviteLink"
                   readonly
                   aria-label="Invitation link">

            <button onclick="copyInviteLink()">
              Copy invite link
            </button>
          </div>
        </div>
      </div>
    </article>

    <article id="companyCreator" class="p s12 hidden">
      <h2><span id="companyFormTitle">Create company</span> <button onclick="hideCompanyForm()">Close</button></h2>
      <div class="form-grid">
        <div class="f6">
          <label for="companyName">Company name *</label>
          <input id="companyName" maxlength="200" placeholder="Example: AluTrade">
        </div>
        <div class="f6">
          <label for="businessMode">Business mode</label>
          <select id="businessMode">
            <option value="sell">Sell — we supply goods/services</option>
            <option value="buy">Buy — we procure goods/services</option>
            <option value="both">Both</option>
          </select>
        </div>
        <div class="f6">
          <label for="industry">Industry</label>
          <input id="industry" maxlength="500" placeholder="Example: Aluminium profiles and construction materials">
        </div>
        <div class="f6">
          <label for="regions">Target regions</label>
          <input id="regions" placeholder="Moscow, Moscow region, Saint Petersburg">
          <div class="help">Separate several values with commas or semicolons.</div>
        </div>
        <div class="f12">
          <label for="keywords">Products &amp; services *</label>
          <textarea id="keywords" placeholder="aluminium profiles, aluminum structures, фасадный профиль"></textarea>
          <div class="help">Product keywords describe your capabilities. Search keywords below control discovery.</div>
        </div>
        <div class="f12"><label for="searchKeywords">Search keywords</label><textarea id="searchKeywords" placeholder="Optional: leave empty to use products / services"></textarea></div>
        <div class="f6"><label for="countries">Target countries</label><input id="countries" placeholder="Germany, Canada"><div class="help">Comma-separated supported markets.</div></div>
        <div class="f6"><label for="currencies">Accepted currencies</label><input id="currencies" value="RUB" placeholder="EUR, USD, RUB"><div class="help">Currency labels are normalized to standard currency codes. No FX conversion is performed; budget limits are compared only within the same currency.</div></div>
        <div class="f12"><label for="documentsAvailable">Available certificates / document keywords</label><input id="documentsAvailable" placeholder="ISO 9001, supplier registration"></div>
        <div class="f12">
          <label for="excludedKeywords">Excluded keywords</label>
          <input id="excludedKeywords" placeholder="repair, used, scrap">
        </div>
        <div class="f6">
          <label for="minContract">Minimum contract value</label>
          <input id="minContract" type="number" min="0" step="1" placeholder="0">
        </div>
        <div class="f6">
          <label for="maxContract">Maximum contract value</label>
          <input id="maxContract" type="number" min="1" step="1" placeholder="50000000">
        </div>
      </div>

      <div id="companyPdfAssistant"
           class="hidden"
           style="margin-top:18px;padding:16px;border:1px solid var(--line);border-radius:12px">
        <h3 style="margin-top:0">Build search profile from company PDF</h3>

        <p class="help">
          Upload a company brochure, catalog, capability statement or product sheet.
          VALYQON will propose discovery fields only. Budget limits, currencies,
          exclusions, hard-stop rules and company identity are preserved.
        </p>

        <div class="toolbar">
          <input id="companyPdfFile"
                 aria-label="Company profile PDF"
                 type="file"
                 accept=".pdf,application/pdf">

          <button id="companyPdfAnalyzeButton"
                  type="button"
                  onclick="previewCompanyProfilePdf()">
            Analyze PDF
          </button>
        </div>

        <div class="help">
          PDF only ? maximum 10 MiB ? scanned image-only PDFs require OCR and are not supported yet.
        </div>

        <div id="companyPdfStatus"></div>
        <div id="companyPdfPreview"></div>
      </div>

      <div id="companyFormError"></div>
      <div class="actions">
        <button onclick="hideCompanyForm()">Cancel</button>
        <button id="createCompanyButton" class="primary" onclick="createCompany()">Create & activate</button>
      </div>
    </article>

    <article class="p s5">
      <h2>Company workspaces <span><button id="addCompanyButton" onclick="showCompanyForm()">Add company</button> <button onclick="loadCompanies()">Reload</button></span></h2>
      <div id="companyActionMessage"></div>
      <div id="companies"><div class="empty">Loading…</div></div>
    </article>
    <article class="p s7"><h2>Recent analyzed documents <button onclick="loadTenders()">Reload</button></h2><div id="tenders"><div class="empty">Loading…</div></div></article>
    <article id="monitoringCenter"
             class="p s12"
             data-page="monitoring">
      <h2>
        <span>Monitoring center</span>
        <span class="toolbar">
          <button type="button"
                  onclick="loadMonitoring()">
            Refresh status
          </button>
          <button id="scanButton"
                  class="primary"
                  type="button"
                  onclick="scanEis()">
            Scan for new matches
          </button>
        </span>
      </h2>

      <p class="muted">
        Live EIS scan for the active company profile.
        A manual scan returns only matching notices that have not already
        been seen in this monitoring scope. Previously seen notices are
        intentionally suppressed by deduplication.
      </p>

      <div class="form-grid"
           style="margin-top:16px">

        <div class="f4">
          <label>Active company</label>
          <div id="monitoringCompany"
               class="title">
            Loading...
          </div>
        </div>

        <div class="f4">
          <label>Monitoring mode</label>
          <div id="monitoringMode"
               class="title">
            Loading...
          </div>
        </div>

        <div class="f4">
          <label>Configured feeds</label>
          <div id="monitoringFeeds"
               class="title">
            Loading...
          </div>
        </div>

        <div class="f4">
          <label>Background monitoring</label>
          <div id="monitoringBackground"
               class="title">
            Loading...
          </div>
        </div>

        <div class="f4">
          <label>Notifications</label>
          <div id="monitoringNotifications"
               class="title">
            Loading...
          </div>
        </div>

        <div class="f4">
          <label>Access</label>
          <div id="monitoringAccess"
               class="title">
            Loading...
          </div>
        </div>
      </div>

      <div id="monitoringExplanation"
           class="help"
           style="margin-top:14px">
        Loading monitoring status...
      </div>

      <div id="monitoringScanSummary"
           style="margin-top:16px"></div>

      <div id="scanResults"
           style="margin-top:14px">
        <div class="empty">
          Run a scan to see new matching notices.
        </div>
      </div>
    </article>
  </section>

  <footer>VALYQON AI v{version} · authenticated web workspace</footer>
</main>
<script>
const state={{accountId:null,ownerId:null,hasActiveCompany:false}};
const esc=v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
async function read(r){{if(r.status===401){{location.replace('/login');throw new Error('Authentication required')}}if(!r.ok){{throw new Error(r.status===403?'Access denied for this workspace.':r.status===409?'The workspace changed or this name already exists. Refresh and try again.':r.status===422?'Check the form values and required fields.':'Service unavailable. Please retry.')}}return r.status===204?null:r.json()}}
async function api(path,opt={{}}){{const epoch=state.uiEpoch||0;const h=new Headers(opt.headers||{{}});if(opt.body&&!(opt.body instanceof FormData))h.set('Content-Type','application/json');let r;try{{r=await fetch(path,{{...opt,headers:h,credentials:'same-origin',cache:'no-store'}})}}catch{{throw new Error('Network unavailable. Please retry.')}}const data=await read(r);if(epoch!==(state.uiEpoch||0))throw new Error('Workspace changed. Refresh to continue.');return data}}
async function loadAccount(){{const a=await api('/api/v1/auth/me');state.accountId=a.id;state.ownerId=a.owner_user_id;document.getElementById('email').textContent=a.email;renderTelegram(a)}}
function owner(){{if(!Number.isInteger(state.ownerId))throw new Error('Account owner unavailable');return state.ownerId}}
function listValue(id){{return document.getElementById(id).value.split(/[,;\\n]+/).map(v=>v.trim()).filter(Boolean)}}
function optionalMoney(id){{const raw=document.getElementById(id).value.trim();if(!raw)return null;const value=Number(raw);if(!Number.isFinite(value)||value<0)throw new Error('Contract values must be valid positive numbers.');return value}}
function showCompanyForm(){{if(!canWriteWorkspace())return;resetCompanyForm();document.getElementById('companyCreator').classList.remove('hidden');document.getElementById('companyName').focus()}}
function resetCompanyPdfAssistant(){{
  state.companyPdfPreview=null;

  const root=document.getElementById(
    'companyPdfAssistant'
  );

  const input=document.getElementById(
    'companyPdfFile'
  );

  const statusRoot=document.getElementById(
    'companyPdfStatus'
  );

  const previewRoot=document.getElementById(
    'companyPdfPreview'
  );

  if(root)root.classList.add('hidden');
  if(input)input.value='';
  if(statusRoot)statusRoot.innerHTML='';
  if(previewRoot)previewRoot.innerHTML='';
}}

function hideCompanyForm(){{
  document.getElementById(
    'companyCreator'
  ).classList.add('hidden');

  document.getElementById(
    'companyFormError'
  ).innerHTML='';

  resetCompanyPdfAssistant();
}}

function resetCompanyForm(){{
  [
    'companyName',
    'industry',
    'regions',
    'keywords',
    'searchKeywords',
    'countries',
    'documentsAvailable',
    'excludedKeywords',
    'minContract',
    'maxContract'
  ].forEach(
    id=>document.getElementById(id).value=''
  );

  document.getElementById(
    'businessMode'
  ).value='sell';

  document.getElementById(
    'currencies'
  ).value='RUB';

  state.editCompanyId=null;
  state.editProfile=null;

  resetCompanyPdfAssistant();

  document.getElementById(
    'companyFormTitle'
  ).textContent='Create company';

  document.getElementById(
    'createCompanyButton'
  ).textContent='Create & activate';
}}
async function loadHealth(){{const d=await (await fetch('/health',{{cache:'no-store'}})).json();document.getElementById('healthVersion').textContent='v'+d.version;const b=document.getElementById('healthBadge');b.textContent=d.status;b.className='chip '+(d.status==='ok'?'good':'warn');document.getElementById('components').innerHTML=Object.entries(d.components||{{}}).map(([k,v])=>`<span class="chip ${{v==='ready'?'good':'warn'}}">${{esc(k)}}: ${{esc(v)}}</span>`).join('')}}
async function loadCompanies(){{
  const path=usingSharedOrganization()
    ?`${{organizationBase()}}/companies`
    :`/api/v1/companies?owner_user_id=${{owner()}}`;

  const items=await api(path);
  state.companies=items;
  const active=items.find(item=>item.is_active);
  state.activeCompanyId=active?.id??null;
  state.activeCompanyName=active?.name||'No active company';
  window.dispatchEvent(new Event('workspace-context'));

  document.getElementById(
    'companyCount'
  ).textContent=items.length;

  const root=document.getElementById(
    'companies'
  );

  if(!items.length){{
    root.innerHTML=usingSharedOrganization()
      ?'<div class="empty">No company profiles exist in this shared organization yet.</div>'
      :'<div class="empty">No company profiles are linked to this account yet. Click <b>Add company</b> to create the first one.</div>';

    updateWorkspaceControls();
    return;
  }}

  root.innerHTML=items.map(item=>{{
    const words=(
      item.profile?.search_keywords
      ||item.profile?.product_keywords
      ||[]
    ).slice(
      0,
      4
    ).join(', ');

    const activate=(
      !item.is_active
      && canWriteWorkspace()
    )
      ?`<button onclick="activateCompany(${{item.id}})">Activate</button>`
      :'';

    return `<div class="row">
      <div class="head">
        <div>
          <div class="title">
            ${{esc(item.name)}}
            ${{item.is_active?'<span class="active">? ACTIVE</span>':''}}
          </div>

          <div class="sub">
            #${{item.id}} ?
            ${{esc(item.profile?.business_mode||'sell')}}
            ${{words?'<br>'+esc(words):''}}
          </div>
        </div>

        <div>${{activate}} ${{usingSharedOrganization()&&canWriteWorkspace()?`<button onclick="editCompany(${{item.id}})">Edit profile</button>`:''}}</div>
      </div>
    </div>`;
  }}).join('');

  updateWorkspaceControls();
}}
function editCompany(id){{
  if(!usingSharedOrganization()||!canWriteWorkspace())return;
  const item=state.companies.find(x=>x.id===id);if(!item)return;
  showCompanyForm();state.editCompanyId=id;state.editProfile=item.profile;
  const p=item.profile;
  const fields={{companyName:item.name,businessMode:p.business_mode,industry:p.industry,regions:(p.allowed_regions||[]).join(', '),keywords:(p.product_keywords||[]).join(', '),searchKeywords:(p.search_keywords||[]).join(', '),countries:(p.allowed_countries||[]).join(', '),currencies:(p.accepted_currencies||[]).join(', '),documentsAvailable:(p.available_document_keywords||[]).join(', '),excludedKeywords:(p.excluded_keywords||[]).join(', '),minContract:p.min_contract_value,maxContract:p.max_contract_value}};
  Object.entries(fields).forEach(([key,value])=>document.getElementById(key).value=value??'');
  document.getElementById(
    'companyFormTitle'
  ).textContent='Edit company profile';

  document.getElementById(
    'createCompanyButton'
  ).textContent='Save profile';

  document.getElementById(
    'companyPdfAssistant'
  ).classList.remove('hidden');
}}

function companyProfileDisplay(value){{
  if(Array.isArray(value)){{
    return value.length
      ?value.join(', ')
      :'?';
  }}

  if(
    value===null
    ||value===undefined
    ||value===''
  ){{
    return '?';
  }}

  return String(value);
}}

function companyProfilePdfDiff(
  current,
  suggested
){{
  const fields=[
    ['industry','Industry'],
    ['product_keywords','Products & services'],
    ['search_keywords','Search keywords'],
    ['allowed_regions','Target regions'],
    ['allowed_countries','Target countries'],
    ['available_document_keywords','Certificates / documents']
  ];

  const changed=fields.filter(
    ([key])=>JSON.stringify(
      current?.[key]??null
    )!==JSON.stringify(
      suggested?.[key]??null
    )
  );

  if(!changed.length){{
    return '<div class="empty" style="margin-top:12px">AI found no supported profile changes in this PDF.</div>';
  }}

  const rows=changed.map(
    ([key,label])=>`
      <div class="row">
        <div class="head">
          <div style="width:100%">
            <div class="title">${{esc(label)}}</div>
            <div class="sub">
              <b>Current:</b> ${{esc(companyProfileDisplay(current?.[key]))}}
              <br>
              <b>Suggested:</b> ${{esc(companyProfileDisplay(suggested?.[key]))}}
            </div>
          </div>
        </div>
      </div>`
  ).join('');

  return `
    <div style="margin-top:14px">
      <div class="success">
        AI draft ready. Review the differences before applying.
      </div>

      ${{rows}}

      <div class="help" style="margin-top:10px">
        Protected settings such as currencies, budget limits, exclusions,
        security limits and hard-stop rules are not generated by AI.
      </div>

      <div class="actions" style="margin-top:12px">
        <button type="button"
                onclick="discardCompanyPdfPreview()">
          Discard
        </button>

        <button id="companyPdfApplyButton"
                type="button"
                class="primary"
                onclick="applyCompanyPdfProfile()">
          Apply AI profile
        </button>
      </div>
    </div>`;
}}

function discardCompanyPdfPreview(){{
  state.companyPdfPreview=null;

  document.getElementById(
    'companyPdfPreview'
  ).innerHTML='';

  document.getElementById(
    'companyPdfStatus'
  ).innerHTML='';

  const input=document.getElementById(
    'companyPdfFile'
  );

  if(input)input.value='';
}}

async function previewCompanyProfilePdf(){{
  const statusRoot=document.getElementById(
    'companyPdfStatus'
  );

  const previewRoot=document.getElementById(
    'companyPdfPreview'
  );

  const button=document.getElementById(
    'companyPdfAnalyzeButton'
  );

  statusRoot.innerHTML='';
  previewRoot.innerHTML='';
  state.companyPdfPreview=null;

  try{{
    if(
      !usingSharedOrganization()
      ||!canWriteWorkspace()
      ||!state.editCompanyId
    ){{
      throw new Error(
        'Open an existing shared company profile first.'
      );
    }}

    const input=document.getElementById(
      'companyPdfFile'
    );

    const file=input.files?.[0];

    if(!file){{
      throw new Error(
        'Choose a company PDF first.'
      );
    }}

    const lowerName=(
      file.name||''
    ).toLowerCase();

    if(
      file.type!=='application/pdf'
      &&!lowerName.endsWith('.pdf')
    ){{
      throw new Error(
        'Only PDF files are supported.'
      );
    }}

    if(file.size>10*1024*1024){{
      throw new Error(
        'PDF exceeds the 10 MiB limit.'
      );
    }}

    const form=new FormData();
    form.append(
      'file',
      file
    );

    button.disabled=true;
    button.textContent='Analyzing?';

    statusRoot.innerHTML=
      '<div class="empty" style="margin-top:12px">Extracting PDF text and building an AI search-profile draft?</div>';

    const companyId=state.editCompanyId;

    const preview=await api(
      `${{organizationBase()}}/companies/${{companyId}}/profile-from-pdf/preview`,
      {{
        method:'POST',
        body:form
      }}
    );

    if(
      companyId!==state.editCompanyId
    ){{
      throw new Error(
        'The edited company changed. Generate the preview again.'
      );
    }}

    state.companyPdfPreview=preview;

    const warning=(
      preview.warnings||[]
    ).map(
      value=>`<div class="error" style="margin-top:10px">${{esc(value)}}</div>`
    ).join('');

    statusRoot.innerHTML=`
      <div class="success" style="margin-top:12px">
        Analyzed ${{esc(preview.source_filename)}} ?
        ${{esc(preview.pages??'?')}} page(s) ?
        ${{esc(preview.characters)}} extracted characters.
      </div>
      ${{warning}}
    `;

    previewRoot.innerHTML=
      companyProfilePdfDiff(
        preview.current_profile,
        preview.suggested_profile
      );

  }}catch(e){{
    statusRoot.innerHTML=
      `<div class="error" style="margin-top:12px">${{esc(e.message||e)}}</div>`;

  }}finally{{
    button.disabled=false;
    button.textContent='Analyze PDF';
  }}
}}

async function applyCompanyPdfProfile(){{
  const preview=state.companyPdfPreview;

  const statusRoot=document.getElementById(
    'companyPdfStatus'
  );

  const previewRoot=document.getElementById(
    'companyPdfPreview'
  );

  const button=document.getElementById(
    'companyPdfApplyButton'
  );

  try{{
    if(
      !usingSharedOrganization()
      ||!canWriteWorkspace()
      ||!state.editCompanyId
      ||!preview
    ){{
      throw new Error(
        'Generate and review an AI profile preview first.'
      );
    }}

    if(button){{
      button.disabled=true;
      button.textContent='Applying?';
    }}

    const companyId=state.editCompanyId;

    const latest=await api(
      `${{organizationBase()}}/companies/${{companyId}}`
    );

    if(
      JSON.stringify(latest.profile)
      !==JSON.stringify(
        preview.current_profile
      )
    ){{
      state.companyPdfPreview=null;

      previewRoot.innerHTML='';

      throw new Error(
        'The company profile changed after this AI preview was generated. Analyze the PDF again before applying.'
      );
    }}

    const updated=await api(
      `${{organizationBase()}}/companies/${{companyId}}`,
      {{
        method:'PATCH',
        body:JSON.stringify({{
          profile:preview.suggested_profile
        }})
      }}
    );

    state.editProfile=updated.profile;
    state.companyPdfPreview=null;

    const p=updated.profile;

    const fields={{
      companyName:updated.name,
      businessMode:p.business_mode,
      industry:p.industry,
      regions:(p.allowed_regions||[]).join(', '),
      keywords:(p.product_keywords||[]).join(', '),
      searchKeywords:(p.search_keywords||[]).join(', '),
      countries:(p.allowed_countries||[]).join(', '),
      currencies:(p.accepted_currencies||[]).join(', '),
      documentsAvailable:(p.available_document_keywords||[]).join(', '),
      excludedKeywords:(p.excluded_keywords||[]).join(', '),
      minContract:p.min_contract_value,
      maxContract:p.max_contract_value
    }};

    Object.entries(
      fields
    ).forEach(
      ([key,value])=>
        document.getElementById(key).value=
          value??''
    );

    previewRoot.innerHTML='';

    statusRoot.innerHTML=
      '<div class="success" style="margin-top:12px">AI search profile applied. Protected company constraints were preserved.</div>';

    const input=document.getElementById(
      'companyPdfFile'
    );

    if(input)input.value='';

    await loadCompanies();

  }}catch(e){{
    statusRoot.innerHTML=
      `<div class="error" style="margin-top:12px">${{esc(e.message||e)}}</div>`;

  }}finally{{
    if(button){{
      button.disabled=false;
      button.textContent='Apply AI profile';
    }}
  }}
}}

async function createCompany(){{
  const errorRoot=document.getElementById(
    'companyFormError'
  );

  const button=document.getElementById(
    'createCompanyButton'
  );

  errorRoot.innerHTML='';

  try{{
    if(!canWriteWorkspace()){{
      throw new Error(
        'This organization role is read-only.'
      );
    }}

    const name=document.getElementById(
      'companyName'
    ).value.trim();

    const keywords=listValue(
      'keywords'
    );

    if(!name){{
      throw new Error(
        'Enter the company name.'
      );
    }}

    if(!keywords.length){{
      throw new Error(
        'Enter at least one product or monitoring keyword.'
      );
    }}

    const minValue=optionalMoney(
      'minContract'
    );

    const maxValue=optionalMoney(
      'maxContract'
    );

    if(
      minValue!==null
      && maxValue!==null
      && minValue>maxValue
    ){{
      throw new Error(
        'Minimum contract value cannot exceed maximum contract value.'
      );
    }}

    const regions=listValue(
      'regions'
    );

    button.disabled=true;
    button.textContent='Creating?';

    const profile={{
      ...state.editProfile,
      profile_version:state.editProfile?.profile_version||'1',
      company_name:name,
      business_mode:document.getElementById('businessMode').value,
      industry:document.getElementById('industry').value.trim()||null,
      product_keywords:keywords,
      search_keywords:listValue('searchKeywords'),
      excluded_keywords:listValue('excludedKeywords'),
      allowed_regions:regions,
      allowed_countries:listValue('countries'),
      accepted_currencies:listValue('currencies').map(v=>v.toUpperCase()),
      min_contract_value:minValue,
      max_contract_value:maxValue,
      max_bid_security_percent:state.editProfile?.max_bid_security_percent??null,
      max_contract_security_percent:state.editProfile?.max_contract_security_percent??null,
      available_document_keywords:listValue('documentsAvailable'),
      hard_stop_on_region:state.editProfile?.hard_stop_on_region??(regions.length>0),
      hard_stop_on_budget:state.editProfile?.hard_stop_on_budget??(true),
      hard_stop_on_currency:state.editProfile?.hard_stop_on_currency??(true),
      hard_stop_on_bid_security:state.editProfile?.hard_stop_on_bid_security??(false),
      hard_stop_on_contract_security:state.editProfile?.hard_stop_on_contract_security??(false)
    }};

    const editing=Boolean(state.editCompanyId);
    state.uiEpoch=(state.uiEpoch||0)+1;
    state.activeCompanyId=null;
    state.activeCompanyName='Loading workspace…';
    window.dispatchEvent(new Event('workspace-context'));
    if(editing){{
      if(!usingSharedOrganization())throw new Error('Select a shared organization to edit profiles.');
      await api(`${{organizationBase()}}/companies/${{state.editCompanyId}}`,{{method:'PATCH',body:JSON.stringify({{name,profile}})}});
    }}else if(usingSharedOrganization()){{
      const created=await api(
        `${{organizationBase()}}/companies`,
        {{
          method:'POST',
          body:JSON.stringify({{
            name,
            profile
          }})
        }}
      );

      await api(
        `${{organizationBase()}}/companies/${{created.id}}/activate`,
        {{
          method:'POST'
        }}
      );

    }}else{{
      await api(
        '/api/v1/companies',
        {{
          method:'POST',
          body:JSON.stringify({{
            owner_user_id:owner(),
            name,
            profile,
            make_active:true
          }})
        }}
      );
    }}

    resetCompanyForm();
    hideCompanyForm();

    document.getElementById(
      'companyActionMessage'
    ).innerHTML=
      editing?'<div class="success">Company profile saved.</div>':'<div class="success">Company created and activated.</div>';

    await Promise.all([
      loadCompanies(),
      loadMonitoring()
    ]);
    if(!editing&&usingSharedOrganization())location.hash='discover';

  }}catch(e){{
    errorRoot.innerHTML=
      `<div class="error" style="margin-top:12px">${{esc(e.message||e)}}</div>`;

  }}finally{{
    button.disabled=false;
    button.textContent=
      state.editCompanyId?'Save profile':'Create & activate';
  }}
}}
async function activateCompany(id){{
  if(!canWriteWorkspace()){{
    return;
  }}

  if(usingSharedOrganization()){{
    await api(
      `${{organizationBase()}}/companies/${{id}}/activate`,
      {{
        method:'POST'
      }}
    );

  }}else{{
    await api(
      `/api/v1/companies/${{id}}/activate`,
      {{
        method:'POST',
        body:JSON.stringify({{
          owner_user_id:owner()
        }})
      }}
    );
  }}

  document.getElementById(
    'companyActionMessage'
  ).innerHTML=
    '<div class="success">Active company changed.</div>';

  await Promise.all([
    loadCompanies(),
    loadMonitoring()
  ]);
}}
function monitoringContextKey(){{
  return [
    state.organizationId??'personal',
    state.activeCompanyId??'none',
    state.ownerId??'none'
  ].join(':');
}}

function monitoringModeLabel(mode){{
  if(mode==='company-profile'){{
    return 'Company profile';
  }}

  if(mode==='static'){{
    return 'Static feed';
  }}

  if(mode==='no-company'){{
    return 'No active company';
  }}

  return mode||'Unknown';
}}

function monitoringIntervalLabel(seconds){{
  const value=Number(seconds);

  if(
    !Number.isFinite(value)
    ||value<=0
  ){{
    return 'Not configured';
  }}

  if(value%3600===0){{
    const hours=value/3600;

    return `${{hours}} hour${{hours===1?'':'s'}}`;
  }}

  if(value%60===0){{
    const minutes=value/60;

    return `${{minutes}} min`;
  }}

  return `${{value}} sec`;
}}

async function loadMonitoring(){{
  const path=usingSharedOrganization()
    ?`${{organizationBase()}}/monitoring/status`
    :`/api/v1/monitoring/status?owner_user_id=${{owner()}}`;

  const data=await api(path);

  state.monitoringStatus=data;

  state.hasActiveCompany=Boolean(
    data.active_company
  );

  document.getElementById(
    'monitorCompany'
  ).textContent=
    data.active_company
    ||'No active company';

  document.getElementById(
    'monitorDetails'
  ).textContent=
    state.hasActiveCompany
      ?`${{monitoringModeLabel(data.feed_mode)}} ? ${{data.rss_feeds}} feed(s)`
      :'Create a company profile to start monitoring.';

  const companyRoot=document.getElementById(
    'monitoringCompany'
  );

  const modeRoot=document.getElementById(
    'monitoringMode'
  );

  const feedsRoot=document.getElementById(
    'monitoringFeeds'
  );

  const backgroundRoot=document.getElementById(
    'monitoringBackground'
  );

  const notificationsRoot=document.getElementById(
    'monitoringNotifications'
  );

  const accessRoot=document.getElementById(
    'monitoringAccess'
  );

  const explanationRoot=document.getElementById(
    'monitoringExplanation'
  );

  if(companyRoot){{
    companyRoot.textContent=
      data.active_company
      ||'No active company';
  }}

  if(modeRoot){{
    modeRoot.textContent=
      monitoringModeLabel(
        data.feed_mode
      );
  }}

  if(feedsRoot){{
    feedsRoot.textContent=
      state.hasActiveCompany
        ?`${{data.rss_feeds}} configured`
        :'0 configured';
  }}

  if(backgroundRoot){{
    backgroundRoot.textContent=
      data.background_enabled
        ?`Enabled ? every ${{monitoringIntervalLabel(data.interval_seconds)}}`
        :'Manual scans only';
  }}

  if(notificationsRoot){{
    notificationsRoot.textContent=
      data.subscription_enabled
        ?'Enabled'
        :'Not enabled';
  }}

  if(accessRoot){{
    accessRoot.textContent=
      canWriteWorkspace()
        ?'Can run scans'
        :'Read-only viewer';
  }}

  if(explanationRoot){{
    if(!state.hasActiveCompany){{
      explanationRoot.textContent=
        'Create and activate a company profile before running Monitoring.';

    }}else if(!canWriteWorkspace()){{
      explanationRoot.textContent=
        'You can inspect Monitoring status, but the Viewer role cannot start a scan.';

    }}else{{
      explanationRoot.textContent=
        'Scan for new matches checks the configured EIS monitoring feed for the active company. Only matching notices not already recorded in this monitoring scope are returned.';
    }}
  }}

  updateWorkspaceControls();
}}

async function loadTenders(){{
  const path=usingSharedOrganization()
    ?`${{organizationBase()}}/tenders?limit=20`
    :`/api/v1/tenders?owner_user_id=${{owner()}}&limit=20`;

  const items=await api(path);

  const root=document.getElementById(
    'tenders'
  );

  if(!items.length){{
    root.innerHTML=usingSharedOrganization()
      ?'<div class="empty">No analyzed PDF tenders stored in this organization yet.</div>'
      :'<div class="empty">No analyzed PDF tenders stored for this account yet.</div>';

    return;
  }}

  root.innerHTML=items.map(item=>
    `<div class="row">
      <div class="title">
        ${{esc(item.title||item.source_filename||'Tender')}}
      </div>

      <div class="sub">
        ${{esc(item.customer||'Customer not specified')}}
        ? ${{item.fit_score??'No fit score'}}
      </div>
    </div>`
  ).join('');
}}
async function scanEis(){{
  const button=document.getElementById(
    'scanButton'
  );

  const root=document.getElementById(
    'scanResults'
  );

  const summary=document.getElementById(
    'monitoringScanSummary'
  );

  const context=
    monitoringContextKey();

  const epoch=
    state.uiEpoch||0;

  try{{
    if(!canWriteWorkspace()){{
      summary.innerHTML=
        '<div class="error">Viewer role is read-only. Monitoring status remains available.</div>';

      return;
    }}

    if(!state.hasActiveCompany){{
      summary.innerHTML=
        '<div class="error">Create and activate a company profile before running Monitoring.</div>';

      return;
    }}

    button.disabled=true;
    button.textContent='Scanning...';

    summary.innerHTML=
      '<div class="empty">Checking the monitoring feed for new matching notices...</div>';

    root.innerHTML=
      '<div class="empty">Scan in progress...</div>';

    const items=usingSharedOrganization()
      ?await api(
          `${{organizationBase()}}/monitoring/scan`,
          {{
            method:'POST'
          }}
        )
      :await api(
          '/api/v1/monitoring/scan',
          {{
            method:'POST',
            body:JSON.stringify({{
              owner_user_id:owner()
            }})
          }}
        );

    if(
      context!==monitoringContextKey()
      ||epoch!==(state.uiEpoch||0)
    ){{
      return;
    }}

    const scannedAt=
      new Intl.DateTimeFormat(
        undefined,
        {{
          hour:'2-digit',
          minute:'2-digit',
          second:'2-digit'
        }}
      ).format(
        new Date()
      );

    if(items.length){{
      summary.innerHTML=
        `<div class="success">${{items.length}} new matching notice${{items.length===1?'':'s'}} found ? ${{esc(scannedAt)}}. These notices are now recorded as seen for this monitoring scope.</div>`;

      root.innerHTML=
        items.map(item=>{{
          const value=
            item.initial_price==null
              ?'Value not provided'
              :`${{item.initial_price}} ${{item.currency||''}}`;

          const metadata=[
            item.source,
            item.customer,
            item.tender_number,
            item.deadline,
            value
          ]
            .filter(Boolean)
            .map(esc)
            .join(' ? ');

          const reasons=
            (item.reasons||[])
              .map(reason=>esc(reason))
              .join(' ? ');

          return `
            <div class="row">
              <div class="head">
                <div>
                  <div class="title">
                    ${{esc(item.title||'EIS notice')}}
                  </div>

                  <div class="sub">
                    ${{metadata||'Tender metadata unavailable'}}
                  </div>
                </div>

                <span class="chip">
                  New
                </span>
              </div>

              <div class="sub"
                   style="margin-top:8px">
                ${{reasons||'Matched the active company monitoring profile.'}}
              </div>

              <div class="toolbar"
                   style="margin-top:10px">
                <a href="${{esc(item.url)}}"
                   target="_blank"
                   rel="noopener noreferrer">
                  Open notice
                </a>
              </div>
            </div>
          `;
        }}).join('');

    }}else{{
      summary.innerHTML=
        `<div class="success">Scan completed ? ${{esc(scannedAt)}}. No new matching notices were found.</div>`;

      root.innerHTML=
        '<div class="empty">No new matching notices. Previously seen matches are intentionally suppressed by Monitoring deduplication.</div>';
    }}

  }}catch(e){{
    if(
      context!==monitoringContextKey()
      ||epoch!==(state.uiEpoch||0)
    ){{
      return;
    }}

    summary.innerHTML=
      `<div class="error">${{esc(e.message||e)}}</div>`;

    root.innerHTML=
      '<div class="empty">The scan did not complete. No result state was updated in this view.</div>';

  }}finally{{
    if(
      context===monitoringContextKey()
      &&epoch===(state.uiEpoch||0)
    ){{
      button.textContent=
        'Scan for new matches';

      updateWorkspaceControls();
    }}
  }}
}}

async function refreshAll(){{
  await loadAccount();
  await loadOrganizations();

  await Promise.all([
    loadHealth(),
    loadWorkspaceData()
  ]);
}}
async function logout(){{try{{await api('/api/v1/auth/logout',{{method:'POST'}})}}finally{{location.replace('/login')}}}}
{ORGANIZATION_SCRIPT}
{TELEGRAM_SCRIPT}
refreshAll().catch(e=>{{if(!String(e.message||e).includes('Authentication required'))document.getElementById('appNotice').textContent='Workspace unavailable. Check your connection and select Refresh to retry.'}});
</script>
</body>
</html>"""


def dashboard_html() -> str:
    return shell_html(_dashboard_html())


__all__ = ["dashboard_html"]
