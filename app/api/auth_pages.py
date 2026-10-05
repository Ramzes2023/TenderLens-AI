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
      <p class="switch">{escape(switch_text)} <a href="{switch_href}">{escape(switch_label)}</a></p>
      <div class="version">VALYQON AI v{version}</div>
    </section>
  </main>
  <script>
    document.getElementById('togglePassword').addEventListener('click',()=>{{const input=document.getElementById('password'),toggle=document.getElementById('togglePassword');const show=input.type==='password';input.type=show?'text':'password';toggle.textContent=show?'Hide':'Show';toggle.setAttribute('aria-pressed',String(show));}});
    const form=document.getElementById('auth'),msg=document.getElementById('msg'),btn=document.getElementById('submit');
    form.addEventListener('submit',async e=>{{
      e.preventDefault(); msg.style.display='none'; btn.disabled=true;
      try {{
        const r=await fetch('{endpoint}',{{method:'POST',headers:{{'Content-Type':'application/json'}},credentials:'same-origin',body:JSON.stringify({{email:document.getElementById('email').value.trim(),password:document.getElementById('password').value}})}});
        if(!r.ok){{throw new Error(r.status===429?'Too many attempts. Please try again later.':'Unable to sign in or create this account. Check your details and try again.')}}
        window.location.replace({next_path_json});
      }} catch(err) {{ msg.textContent=err instanceof TypeError?'Connection unavailable. Please try again.':err.message||'Authentication unavailable. Please try again.'; msg.style.display='block'; }}
      finally {{ btn.disabled=false; }}
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


__all__ = ["login_html", "register_html"]
