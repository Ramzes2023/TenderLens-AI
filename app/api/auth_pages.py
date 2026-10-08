"""Self-contained authentication pages for VALYQON AI web accounts."""
from __future__ import annotations

import json

from html import escape
from urllib.parse import quote

from app import __version__


def _page(
    mode: str,
    next_path: str = "/dashboard",
) -> str:
    register = mode == "register"
    if mode not in {"login", "register"}:
        raise ValueError("Unsupported auth page mode")

    title = "Create your account" if register else "Welcome back"
    endpoint = "/api/v1/auth/register" if register else "/api/v1/auth/login"
    button = "Create account" if register else "Sign in"
    switch_href = "/login" if register else "/register"

    if next_path != "/dashboard":
        switch_href = (
            f"{switch_href}?next="
            f"{quote(next_path, safe='')}"
        )
    switch_label = "Sign in" if register else "Create account"
    switch_text = "Already have an account?" if register else "New to VALYQON AI?"
    autocomplete = "new-password" if register else "current-password"
    hint = '<div class="hint">Use at least 12 characters.</div>' if register else ""
    version = escape(__version__)
    next_path_json = (
        json.dumps(next_path)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  <title>{escape(title)} · VALYQON AI</title>
  <style>
    :root {{ color-scheme:dark; --bg:#07101f; --panel:#0f1b31; --line:#263a5d; --text:#f4f7fb; --muted:#9fb0cb; --accent:#79a7ff; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; min-height:100vh; display:grid; place-items:center; padding:24px; font-family:Inter,system-ui,sans-serif; background:radial-gradient(circle at 80% 10%,rgba(70,120,235,.2),transparent 28rem),var(--bg); color:var(--text); }}
    .card {{ width:min(940px,100%); display:grid; grid-template-columns:1fr 1fr; border:1px solid var(--line); border-radius:24px; overflow:hidden; background:var(--panel); box-shadow:0 28px 80px rgba(0,0,0,.35); }}
    .hero {{ padding:52px; background:linear-gradient(145deg,rgba(121,167,255,.13),transparent); }}
    .form {{ padding:52px; display:flex; flex-direction:column; justify-content:center; }}
    .logo {{ font-weight:900; }}
    h1 {{ font-size:clamp(2rem,4vw,3.2rem); line-height:1.05; letter-spacing:-.04em; margin:48px 0 14px; }}
    h2 {{ margin:0; font-size:1.8rem; }}
    p {{ color:var(--muted); line-height:1.6; }}
    label {{ display:block; color:#c9d5e8; font-size:.82rem; margin:0 0 7px; }}
    .field {{ margin:0 0 16px; }}
    input {{ width:100%; padding:.85rem .9rem; border:1px solid var(--line); border-radius:12px; background:#091426; color:var(--text); font:inherit; outline:none; }}
    input:focus {{ border-color:var(--accent); box-shadow:0 0 0 3px rgba(121,167,255,.12); }}
    button {{ width:100%; padding:.9rem; border:0; border-radius:12px; background:var(--accent); color:#071020; font:inherit; font-weight:800; cursor:pointer; }}
    button:disabled {{ opacity:.6; cursor:wait; }}
    .hint {{ font-size:.76rem; color:var(--muted); margin-top:6px; }}
    .msg {{ display:none; color:#ffd0d0; background:rgba(255,133,133,.08); border:1px solid rgba(255,133,133,.4); border-radius:10px; padding:10px 12px; margin-bottom:14px; font-size:.84rem; }}
    .switch {{ text-align:center; font-size:.88rem; }}
    a {{ color:#aac7ff; text-decoration:none; font-weight:650; }}
    .version {{ text-align:center; color:#7184a3; font-size:.74rem; margin-top:22px; }}
    @media(max-width:760px) {{ .card {{ grid-template-columns:1fr; }} .hero {{ display:none; }} .form {{ padding:34px 24px; }} }}
  </style>
<link rel="stylesheet" href="/assets/premium.css">
<link rel="stylesheet" href="/assets/responsive.css?v=phase24q">
</head>
<body class="auth-premium">
  <main class="card">
    <section class="hero">
      <div class="logo">VALYQON AI</div>
      <h1>Procurement intelligence.<br>Built around you.</h1>
      <p>Find. Analyze. Score. Win.</p>
      <p>Track opportunities, analyze tender documents and keep company-specific procurement intelligence in one secure workspace.</p>
      <ul class="auth-capabilities"><li>Global procurement sources</li><li>Company matching</li><li>Explainable scoring</li></ul>
    </section>
    <section class="form">
      <a class="back-link" href="/">← Back to VALYQON</a>
      <h2>{escape(title)}</h2>
      <p>{'Start your VALYQON AI workspace.' if register else 'Sign in to your procurement intelligence workspace.'}</p>
      <div id="msg" class="msg"></div>
      <form id="auth">
        <div class="field">
          <label for="email">Email</label>
          <input id="email" type="email" maxlength="254" autocomplete="email" required placeholder="you@company.com">
        </div>
        <div class="field">
          <label for="password">Password</label>
          <div class="password-control"><input id="password" type="password" maxlength="128" autocomplete="{autocomplete}" required placeholder="••••••••••••"><button type="button" id="togglePassword" class="password-toggle" aria-controls="password" aria-pressed="false">Show</button></div>
          {hint}
        </div>
        <button id="submit" type="submit">{escape(button)}</button>
      </form>
      {'' if register else '<p class="switch"><a href="/forgot-password">Forgot password?</a></p>'}
      <p class="switch">{escape(switch_text)} <a href="{switch_href}">{escape(switch_label)}</a></p>
      <div class="version">VALYQON AI v{version}</div>
    </section>
  </main>
  <script>
    document.getElementById('togglePassword').addEventListener('click',()=>{{const input=document.getElementById('password'),toggle=document.getElementById('togglePassword');const show=input.type==='password';input.type=show?'text':'password';toggle.textContent=show?'Hide':'Show';toggle.setAttribute('aria-pressed',String(show));}});
    const form=document.getElementById('auth'),msg=document.getElementById('msg'),btn=document.getElementById('submit');
    const registerMode={str(register).lower()};
    form.addEventListener('submit',async e=>{{
      e.preventDefault();
      msg.style.display='none';
      btn.disabled=true;

      const email=
        document.getElementById('email').value.trim();

      try {{
        const r=await fetch(
          '{endpoint}',
          {{
            method:'POST',
            headers:{{
              'Content-Type':'application/json'
            }},
            credentials:'same-origin',
            body:JSON.stringify({{
              email,
              password:
                document.getElementById('password').value
            }})
          }}
        );

        let data={{}};

        try {{
          data=await r.json();
        }} catch(_error) {{}}

        if(!r.ok){{
          if(
            !registerMode
            &&r.status===403
            &&data.detail==='Email verification required.'
          ){{
            window.location.replace(
              '/verify-email?email='
              +encodeURIComponent(email)
              +'&next='
              +encodeURIComponent({next_path_json})
            );
            return;
          }}

          throw new Error(
            r.status===429
              ?'Too many attempts. Please try again later.'
              :(data.detail||'Unable to sign in or create this account. Check your details and try again.')
          );
        }}

        if(registerMode){{
          window.location.replace(
            '/verify-email?email='
            +encodeURIComponent(data.email||email)
            +'&next='
            +encodeURIComponent({next_path_json})
            +'&sent='
            +(data.verification_sent?'1':'0')
          );
          return;
        }}

        window.location.replace(
          {next_path_json}
        );

      }} catch(err) {{
        msg.textContent=
          err instanceof TypeError
            ?'Connection unavailable. Please try again.'
            :(err.message||'Authentication unavailable. Please try again.');

        msg.style.display='block';

      }} finally {{
        btn.disabled=false;
      }}
    }});
  </script>
</body>
</html>"""


def login_html(
    next_path: str = "/dashboard",
) -> str:
    return _page(
        "login",
        next_path,
    )


def register_html(
    next_path: str = "/dashboard",
) -> str:
    return _page(
        "register",
        next_path,
    )




def verify_email_html(
    *,
    token: str | None = None,
    email: str | None = None,
    next_path: str = "/dashboard",
    sent: bool | None = None,
) -> str:
    token_json = (
        json.dumps(token or "")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )

    email_json = (
        json.dumps(email or "")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )

    next_json = (
        json.dumps(next_path)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )

    sent_json = (
        "true"
        if sent is True
        else (
            "false"
            if sent is False
            else "null"
        )
    )

    version = escape(
        __version__
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport"
        content="width=device-width,initial-scale=1">
  <meta name="robots"
        content="noindex,nofollow">
  <meta name="referrer"
        content="no-referrer">
  <title>Verify your email ? VALYQON AI</title>

  <style>
    :root {{
      color-scheme:dark;
      --bg:#07101f;
      --panel:#0f1b31;
      --line:#263a5d;
      --text:#f4f7fb;
      --muted:#9fb0cb;
      --accent:#79a7ff;
      --ok:#9fe3b1;
    }}

    * {{ box-sizing:border-box; }}

    body {{
      margin:0;
      min-height:100vh;
      display:grid;
      place-items:center;
      padding:24px;
      font-family:Inter,system-ui,sans-serif;
      background:
        radial-gradient(
          circle at 80% 10%,
          rgba(70,120,235,.2),
          transparent 28rem
        ),
        var(--bg);
      color:var(--text);
    }}

    .card {{
      width:min(620px,100%);
      border:1px solid var(--line);
      border-radius:24px;
      padding:42px;
      background:var(--panel);
      box-shadow:0 28px 80px rgba(0,0,0,.35);
    }}

    .logo {{
      font-weight:900;
      margin-bottom:36px;
    }}

    h1 {{
      font-size:2.1rem;
      letter-spacing:-.035em;
      margin:0 0 12px;
    }}

    p {{
      color:var(--muted);
      line-height:1.6;
    }}

    .status {{
      margin:22px 0;
      border:1px solid var(--line);
      border-radius:14px;
      padding:14px 16px;
      color:var(--muted);
    }}

    .status.ok {{
      color:var(--ok);
    }}

    input {{
      width:100%;
      padding:.85rem .9rem;
      border:1px solid var(--line);
      border-radius:12px;
      background:#091426;
      color:var(--text);
      font:inherit;
      outline:none;
      margin:8px 0 12px;
    }}

    button {{
      width:100%;
      padding:.9rem;
      border:0;
      border-radius:12px;
      background:var(--accent);
      color:#071020;
      font:inherit;
      font-weight:800;
      cursor:pointer;
    }}

    button:disabled {{
      opacity:.6;
      cursor:wait;
    }}

    a {{
      color:#aac7ff;
      text-decoration:none;
      font-weight:650;
    }}

    .version {{
      text-align:center;
      color:#7184a3;
      font-size:.74rem;
      margin-top:28px;
    }}
  </style>

  <link rel="stylesheet"
        href="/assets/premium.css">
  <link rel="stylesheet" href="/assets/responsive.css?v=phase24q">
</head>

<body class="auth-premium">
  <main class="card">
    <div class="logo">VALYQON AI</div>

    <h1>Verify your email</h1>

    <p>
      Confirm your email address before entering your
      procurement intelligence workspace.
    </p>

    <div id="status"
         class="status">
      Checking verification status...
    </div>

    <div id="resendBox">
      <label for="verifyEmail">
        Email
      </label>

      <input id="verifyEmail"
             type="email"
             maxlength="254"
             autocomplete="email"
             placeholder="you@company.com">

      <button id="resend"
              type="button">
        Send verification email again
      </button>
    </div>

    <p style="margin-top:20px">
      <a href="/login">
        Back to sign in
      </a>
    </p>

    <div class="version">
      VALYQON AI v{version}
    </div>
  </main>

  <script>
    const token={token_json};
    const initialEmail={email_json};
    const nextPath={next_json};
    const initialSent={sent_json};

    const statusNode=
      document.getElementById('status');

    const emailNode=
      document.getElementById('verifyEmail');

    const resendButton=
      document.getElementById('resend');

    emailNode.value=
      initialEmail;

    function statusMessage(
      value,
      ok=false
    ){{
      statusNode.textContent=value;
      statusNode.classList.toggle(
        'ok',
        Boolean(ok)
      );
    }}

    async function verify(){{
      if(!token){{
        if(initialSent===false){{
          statusMessage(
            'Your account was created, but the verification email could not be delivered. You can request another email below.'
          );

        }}else{{
          statusMessage(
            'Check your inbox for the VALYQON AI verification link.'
          );
        }}

        return;
      }}

      statusMessage(
        'Verifying your email...'
      );

      try {{
        const response=await fetch(
          '/api/v1/auth/verify-email',
          {{
            method:'POST',
            headers:{{
              'Content-Type':'application/json'
            }},
            credentials:'same-origin',
            body:JSON.stringify({{
              token
            }})
          }}
        );

        if(!response.ok){{
          throw new Error(
            response.status===422
              ?'This verification link is invalid, expired, or already used.'
              :'Email verification is temporarily unavailable.'
          );
        }}

        history.replaceState(
          {{}},
          '',
          '/verify-email'
        );

        statusMessage(
          'Email verified. Opening your workspace...',
          true
        );

        setTimeout(
          ()=>window.location.replace(
            nextPath
          ),
          500
        );

      }} catch(error) {{
        statusMessage(
          error instanceof TypeError
            ?'Connection unavailable. Please try again.'
            :(error.message||'Unable to verify email.')
        );
      }}
    }}

    resendButton.addEventListener(
      'click',
      async()=>{{
        const email=
          emailNode.value.trim();

        if(!email){{
          statusMessage(
            'Enter your email address.'
          );
          return;
        }}

        resendButton.disabled=true;

        try {{
          const response=await fetch(
            '/api/v1/auth/resend-verification',
            {{
              method:'POST',
              headers:{{
                'Content-Type':'application/json'
              }},
              credentials:'same-origin',
              body:JSON.stringify({{
                email
              }})
            }}
          );

          if(!response.ok){{
            throw new Error(
              response.status===503
                ?'Email delivery is temporarily unavailable.'
                :'Unable to request another verification email.'
            );
          }}

          statusMessage(
            'If an unverified account exists for this address and a resend is allowed, a new verification email has been sent.',
            true
          );

        }} catch(error) {{
          statusMessage(
            error instanceof TypeError
              ?'Connection unavailable. Please try again.'
              :(error.message||'Unable to resend verification email.')
          );

        }} finally {{
          resendButton.disabled=false;
        }}
      }}
    );

    verify();
  </script>
</body>
</html>"""


def _password_reset_page(*, reset: bool) -> str:
    # Reuse the established auth layout, typography and premium stylesheet.
    page = _page("register" if reset else "login")
    title = "Reset your password" if reset else "Forgot password?"
    page = page.replace("Create your account" if reset else "Welcome back", title)
    page = page.replace("Start your VALYQON AI workspace." if reset else
                        "Sign in to your procurement intelligence workspace.",
                        "Choose a new password for your account." if reset else
                        "Enter your email to request a password reset link.")
    page = page.replace('<meta name="robots" content="noindex,nofollow">',
                        '<meta name="robots" content="noindex,nofollow">\n'
                        '  <meta name="referrer" content="no-referrer">')
    form_start = page.index('      <form id="auth">')
    form_end = page.index('      <div class="version">', form_start)
    fields = '''<div class="field"><label for="email">Email</label>
      <input id="email" type="email" maxlength="254" autocomplete="email" required placeholder="you@company.com"></div>'''
    if reset:
        fields = '''<div class="field"><label for="password">New password</label>
          <input id="password" type="password" minlength="12" maxlength="128" autocomplete="new-password" required>
          <div class="hint">Use at least 12 characters.</div></div>
          <div class="field"><label for="confirmPassword">Confirm password</label>
          <input id="confirmPassword" type="password" minlength="12" maxlength="128" autocomplete="new-password" required></div>'''
    button = "Reset password" if reset else "Send reset link"
    page = page[:form_start] + f'''      <form id="auth">{fields}
        <button id="submit" type="submit">{button}</button></form>
      <p class="switch"><a href="/login">Back to sign in</a></p>
''' + page[form_end:]
    script_start = page.index('  <script>')
    script_end = page.index('  </script>', script_start) + len('  </script>')
    script = '''  <script>
    const resetMode=RESET_MODE;
    const token=new URLSearchParams(window.location.search).get('token')||'';
    if(resetMode) history.replaceState({},'', '/reset-password');
    const form=document.getElementById('auth'),msg=document.getElementById('msg'),btn=document.getElementById('submit');
    msg.setAttribute('role','status');
    function message(text){msg.textContent=text;msg.style.display='block';}
    if(resetMode&&!token){message('Password reset link is invalid or expired. Request a new link.');btn.disabled=true;}
    form.addEventListener('submit',async event=>{
      event.preventDefault();
      const payload=resetMode?{token,password:document.getElementById('password').value}:{email:document.getElementById('email').value.trim()};
      if(resetMode&&payload.password!==document.getElementById('confirmPassword').value){message('Passwords must match.');return;}
      btn.disabled=true;
      let completed=false;
      try{
        const response=await fetch('/api/v1/auth/'+(resetMode?'reset-password':'forgot-password'),{
          method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify(payload)
        });
        if(!response.ok){
          let data={};try{data=await response.json();}catch(_error){}
          throw new Error(typeof data.detail==='string'?data.detail:'Password reset is temporarily unavailable.');
        }
        if(resetMode){
          completed=true;
          message('Password reset complete. Returning to sign in...');
          setTimeout(()=>window.location.replace('/login'),500);
        }else{
          message('If an eligible account exists for this email, a password reset link has been sent.');
        }
      }catch(error){message(error instanceof TypeError?'Connection unavailable. Please try again.':error.message);}
      finally{if(!completed)btn.disabled=false;}
    });
  </script>'''.replace('RESET_MODE', 'true' if reset else 'false')
    return page[:script_start] + script + page[script_end:]


def forgot_password_html() -> str:
    return _password_reset_page(reset=False)


def reset_password_html() -> str:
    return _password_reset_page(reset=True)


__all__ = [
    "forgot_password_html",
    "reset_password_html",
    "login_html",
    "register_html",
    "verify_email_html",
]
