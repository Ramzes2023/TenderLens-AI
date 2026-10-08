"""Browser page for organization invitation acceptance."""

from __future__ import annotations

import json

from html import escape

from app import __version__


def invitation_page_html(
    token: str,
) -> str:
    version = escape(
        __version__
    )

    token_json = (
        json.dumps(token)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport"
        content="width=device-width,initial-scale=1">
  <meta name="robots"
        content="noindex,nofollow">

  <title>
    Organization invitation ? VALYQON AI
  </title>

  <style>
    :root {{
      color-scheme:dark;
      --bg:#07101f;
      --panel:#0f1b31;
      --line:#263a5d;
      --text:#f4f7fb;
      --muted:#9fb0cb;
      --accent:#79a7ff;
    }}

    * {{
      box-sizing:border-box;
    }}

    body {{
      margin:0;
      min-height:100vh;
      display:grid;
      place-items:center;
      padding:24px;
      font-family:Inter,system-ui,sans-serif;
      background:var(--bg);
      color:var(--text);
    }}

    .card {{
      width:min(640px,100%);
      border:1px solid var(--line);
      border-radius:22px;
      padding:34px;
      background:var(--panel);
    }}

    h1 {{
      margin:0 0 8px;
    }}

    p {{
      color:var(--muted);
      line-height:1.55;
    }}

    .row {{
      margin-top:18px;
      padding:14px;
      border:1px solid var(--line);
      border-radius:12px;
    }}

    .label {{
      color:var(--muted);
      font-size:.78rem;
    }}

    .value {{
      font-weight:750;
      margin-top:4px;
    }}

    .actions {{
      display:flex;
      gap:10px;
      flex-wrap:wrap;
      margin-top:20px;
    }}

    button,
    a.button {{
      border:1px solid var(--line);
      border-radius:11px;
      padding:.75rem 1rem;
      background:#162641;
      color:var(--text);
      cursor:pointer;
      text-decoration:none;
      font:inherit;
    }}

    button.primary {{
      background:var(--accent);
      color:#071020;
      border-color:transparent;
      font-weight:800;
    }}

    .msg {{
      margin-top:16px;
    }}

    .error {{
      color:#ffd0d0;
    }}

    .success {{
      color:#bdf2d3;
    }}

    .hidden {{
      display:none;
    }}

    .version {{
      color:#7184a3;
      font-size:.75rem;
      margin-top:24px;
    }}
  </style>
  <link rel="stylesheet" href="/assets/responsive.css?v=phase24q">
</head>

<body class="invitation-page">
  <main class="card">
    <div class="label">
      VALYQON AI
    </div>

    <h1>
      Organization invitation
    </h1>

    <p id="intro">
      Checking invitation?
    </p>

    <div id="details"
         class="hidden">

      <div class="row">
        <div class="label">
          Organization
        </div>

        <div id="organization"
             class="value">
          ?
        </div>
      </div>

      <div class="row">
        <div class="label">
          Invited account
        </div>

        <div id="emailHint"
             class="value">
          ?
        </div>
      </div>

      <div class="row">
        <div class="label">
          Role
        </div>

        <div id="role"
             class="value">
          ?
        </div>
      </div>

      <div class="actions">
        <button id="acceptButton"
                class="primary"
                onclick="acceptInvitation()">
          Accept invitation
        </button>

        <a class="button"
           href="/dashboard">
          Dashboard
        </a>
      </div>
    </div>

    <div id="authActions"
         class="actions hidden">

      <a id="loginLink"
         class="button"
         href="/login">
        Sign in
      </a>

      <a id="registerLink"
         class="button"
         href="/register">
        Create account
      </a>
    </div>

    <div id="message"
         class="msg">
    </div>

    <div class="version">
      VALYQON AI v{version}
    </div>
  </main>

<script>
const token={token_json};
const encodedToken=encodeURIComponent(token);

const previewPath=
  `/api/v1/organizations/invitations/${{encodedToken}}`;

const acceptPath=
  `${{previewPath}}/accept`;

const returnPath=
  `/invite/${{encodedToken}}`;

async function responseDetail(response){{
  let detail=`${{response.status}} ${{response.statusText}}`;

  try{{
    const data=await response.json();

    if(data.detail){{
      detail=typeof data.detail==='string'
        ?data.detail
        :JSON.stringify(data.detail);
    }}
  }}catch(_){{}}

  return detail;
}}

function showAuth(){{
  const next=encodeURIComponent(
    returnPath
  );

  document.getElementById(
    'loginLink'
  ).href=
    `/login?next=${{next}}`;

  document.getElementById(
    'registerLink'
  ).href=
    `/register?next=${{next}}`;

  document.getElementById(
    'authActions'
  ).classList.remove(
    'hidden'
  );
}}

async function loadInvitation(){{
  const message=document.getElementById(
    'message'
  );

  try{{
    const response=await fetch(
      previewPath,
      {{
        credentials:'same-origin',
        cache:'no-store'
      }}
    );

    if(!response.ok){{
      throw new Error(
        await responseDetail(
          response
        )
      );
    }}

    const data=await response.json();

    document.getElementById(
      'intro'
    ).textContent=
      'You have been invited to join a VALYQON AI organization.';

    document.getElementById(
      'organization'
    ).textContent=
      data.organization_name;

    document.getElementById(
      'emailHint'
    ).textContent=
      data.email_hint;

    document.getElementById(
      'role'
    ).textContent=
      data.role;

    document.getElementById(
      'details'
    ).classList.remove(
      'hidden'
    );

  }}catch(e){{
    document.getElementById(
      'intro'
    ).textContent=
      'This invitation cannot be used.';

    message.className=
      'msg error';

    message.textContent=
      e.message||String(e);
  }}
}}

async function acceptInvitation(){{
  const button=document.getElementById(
    'acceptButton'
  );

  const message=document.getElementById(
    'message'
  );

  message.textContent='';

  try{{
    button.disabled=true;
    button.textContent='Accepting?';

    const response=await fetch(
      acceptPath,
      {{
        method:'POST',
        credentials:'same-origin',
        cache:'no-store'
      }}
    );

    if(response.status===401){{
      showAuth();

      throw new Error(
        'Sign in or create the invited account, then accept the invitation.'
      );
    }}

    if(!response.ok){{
      throw new Error(
        await responseDetail(
          response
        )
      );
    }}

    message.className=
      'msg success';

    message.textContent=
      'Invitation accepted. Opening your dashboard?';

    setTimeout(
      ()=>location.replace(
        '/dashboard'
      ),
      500
    );

  }}catch(e){{
    message.className=
      'msg error';

    message.textContent=
      e.message||String(e);

  }}finally{{
    button.disabled=false;
    button.textContent=
      'Accept invitation';
  }}
}}

loadInvitation();
</script>
</body>
</html>"""


__all__ = [
    "invitation_page_html",
]
