"""Real Chromium journey against ONLY the loopback preview and Mailpit.

No CLI flags required. Uses host-installed Playwright/browser; never installs or
downloads anything. Mailpit messages are inspected only for this run's customer.
Tokens/passwords never enter diagnostics, screenshots, traces or HAR files.
"""
from __future__ import annotations

import argparse
from html import unescape
from html.parser import HTMLParser
import os
from pathlib import Path
import re
import secrets
import time
from urllib.parse import parse_qs, urljoin, urlsplit
import uuid

GATES = ("PRIVATE_GUEST", "PRIVATE_LOGIN", "PRIVATE_REGISTER", "PRIVATE_VERIFY_EMAIL",
         "PRIVATE_FORGOT_RESET", "PRIVATE_WORKSPACE", "PRIVATE_MAILBOX")


class SmokeFailure(AssertionError):
    pass


def require(value, diagnostic):
    if not value:
        raise SmokeFailure(diagnostic)


def origin(value):
    parsed = urlsplit(value)
    require(parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}
            and parsed.port and not parsed.username and not parsed.password
            and not parsed.query and not parsed.fragment and parsed.path in {"", "/"},
            "only explicit HTTP loopback origins are permitted")
    return f"http://{parsed.hostname}:{parsed.port}"


def load_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as error:
        # Module names are safe to report; arbitrary exception messages can
        # contain credentials or one-time URLs later in the journey.
        name = error.name or "unknown"
        if not re.fullmatch(r"[A-Za-z0-9_.]+", name):
            name = "unknown"
        raise SmokeFailure(
            f"browser dependency missing: {name}; install "
            "ops/private_preview/requirements.browser.txt into the exact "
            "host Python used by this smoke; use an already installed Chromium"
        ) from None
    return sync_playwright


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.urls.extend(value for key, value in attrs if key == "href" and value)


def preview_path(value, base, path):
    parsed = urlsplit(str(value))
    return (f"{parsed.scheme}://{parsed.netloc}" == base and parsed.path == path
            and not parsed.fragment and all(key == "lang" and values in (["en"], ["ru"])
                for key, values in parse_qs(parsed.query, keep_blank_values=True).items()))


def email_link(request, mailbox, base, email, purpose, report=lambda message: None):
    # Enforce the same loopback boundary for direct callers as for the browser
    # journey, before issuing any mailbox request.
    mailbox = origin(mailbox)
    base = origin(base)
    # A new UUID recipient per run excludes historical mail without clock-skew
    # cutoffs that could discard delivery preceding the registration response.
    deadline = time.monotonic() + 30
    found = False
    responsive = False
    while time.monotonic() < deadline:
        try:
            listing = request.get(mailbox + "/api/v1/messages", max_redirects=0, timeout=5000)
        except Exception:
            raise SmokeFailure("MAILPIT_API_RESPONSIVE=FAIL listing request failed") from None
        require(listing.status == 200, "Mailpit message listing failed")
        try:
            payload = listing.json()
        except Exception:
            raise SmokeFailure("Mailpit listing JSON invalid") from None
        require(isinstance(payload, dict) and isinstance(payload.get("messages"), list),
                "Mailpit listing schema invalid")
        if not responsive:
            report("MAILPIT_API_RESPONSIVE=VERIFIED")
            responsive = True
        messages = list(payload["messages"])
        total = payload.get("total", len(messages))
        require(isinstance(total, int) and total >= 0, "Mailpit pagination schema invalid")
        while messages and len(messages) < total and time.monotonic() < deadline:
            try:
                more = request.get(mailbox + f"/api/v1/messages?start={len(messages)}&limit=50",
                                   max_redirects=0, timeout=5000)
                require(more.status == 200, "Mailpit pagination failed")
                batch = more.json()["messages"]
                require(isinstance(batch, list), "Mailpit pagination schema invalid")
            except SmokeFailure:
                raise
            except Exception:
                raise SmokeFailure("Mailpit pagination request or JSON failed") from None
            if not batch:
                raise SmokeFailure("Mailpit pagination incomplete; delivery cannot be determined")
            messages.extend(batch)
        require(len(messages) >= total, "Mailpit pagination incomplete; delivery cannot be determined")
        for message in messages:
            require(isinstance(message, dict) and isinstance(message.get("To"), list),
                    "Mailpit recipient schema invalid")
            if not any(isinstance(recipient, dict) and
                       str(recipient.get("Address", "")).casefold() == email.casefold()
                       for recipient in message["To"]):
                continue
            if not found:
                report("MATCHING_SYNTHETIC_VERIFICATION_MESSAGE_FOUND=VERIFIED" if purpose == "/verify-email"
                       else "MATCHING_SYNTHETIC_RESET_MESSAGE_FOUND=VERIFIED")
                found = True
            identifier = message.get("ID", "")
            require(re.fullmatch(r"[A-Za-z0-9_-]+", identifier), "Mailpit returned an invalid message identifier")
            try:
                detail = request.get(mailbox + "/api/v1/message/" + identifier, max_redirects=0, timeout=5000)
            except Exception:
                raise SmokeFailure("Mailpit matching synthetic message read failed") from None
            require(detail.status == 200, "Mailpit message read failed")
            try:
                body = detail.json()
                text, html = body.get("Text", ""), body.get("HTML", "")
                require(isinstance(text, str) and isinstance(html, str), "Mailpit body schema invalid")
                parser = _Links()
                parser.feed(html)
            except SmokeFailure:
                raise
            except Exception:
                raise SmokeFailure("Mailpit matching message body parsing failed") from None
            for candidate in re.findall(r"https?://[^\s<>\"']+", text) + parser.urls:
                candidate = unescape(candidate)
                parsed = urlsplit(candidate)
                if parsed.path != purpose:
                    continue
                require(f"{parsed.scheme}://{parsed.netloc}" == base and not parsed.fragment,
                        "email link origin differs from forwarded preview origin")
                tokens = parse_qs(parsed.query, keep_blank_values=True).get("token", [])
                require(len(tokens) == 1 and bool(tokens[0].strip()),
                        "email has no single-use link token")
                report("VALID_VERIFY_LINK_FOUND=VERIFIED" if purpose == "/verify-email"
                       else "VALID_RESET_LINK_FOUND=VERIFIED")
                return candidate
        time.sleep(0.5)
    if found:
        raise SmokeFailure("matching synthetic message found; no valid purpose link within 30 seconds (content/parsing failure)")
    raise SmokeFailure("no matching test email delivered within 30 seconds; API responsive; BLOCKED delivery/environment investigation required")


def run(screenshot_dir=None):
    states = {gate: ("NOT_VERIFIED", "journey not reached") for gate in GATES}
    stage = "PRIVATE_GUEST"
    step = "browser startup"
    browser = None
    manager = None
    server_errors = []
    browser_errors = []
    blocked_external = []
    try:
        base = origin(os.environ.get("VALYQON_PREVIEW_BASE_URL", "http://127.0.0.1:18765"))
        mailbox = origin(os.environ.get("VALYQON_PREVIEW_MAILPIT_URL", "http://127.0.0.1:18766"))
        screenshots = Path(screenshot_dir or os.environ.get(
            "VALYQON_PREVIEW_SCREENSHOT_DIR", "ops/private_preview/screenshots"))
        screenshots.mkdir(parents=True, exist_ok=True)
        sync_playwright = load_playwright()
        manager = sync_playwright().start()
        launch = {"headless": True}
        # Optional host-installed Chromium executable; normal PLAYWRIGHT_BROWSERS_PATH also works.
        executable = os.environ.get("VALYQON_PREVIEW_BROWSER_EXECUTABLE")
        if executable:
            launch["executable_path"] = executable
        browser = manager.chromium.launch(**launch)
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, service_workers="block")
        context.set_default_timeout(20000)

        def restrict(route):
            parsed = urlsplit(route.request.url)
            if f"{parsed.scheme}://{parsed.netloc}" in {base, mailbox}:
                route.continue_()
            elif parsed.scheme in {"data", "blob", "about"}:
                route.continue_()
            else:
                blocked_external.append("external request blocked")
                route.abort()

        context.route("**/*", restrict)
        page = context.new_page()
        page.on("pageerror", lambda error: browser_errors.append(type(error).__name__))
        page.on("response", lambda response: server_errors.append(
            f"HTTP {response.status} on {urlsplit(response.url).path}") if response.status >= 500 else None)

        def visit(path, filename, heading=None):
            response = page.goto(base + path, wait_until="networkidle")
            require(response and response.status == 200 and urlsplit(page.url).path == path,
                    "page unavailable or unexpected authentication redirect")
            if heading:
                require(page.get_by_role("heading", name=heading, exact=True).is_visible(), "expected page heading missing")
            if path == "/":
                # Locale binding adds ?lang= and makes public links absolute.
                sign_in_visible = any(
                    link.is_visible() and urlsplit(urljoin(base, link.get_attribute("href") or ""))._replace(
                        query="", fragment="").geturl() == base + "/login"
                    for link in page.get_by_role("link", name=re.compile(r"\S")).all()
                )
                require(page.get_by_role("main").get_by_role("heading", level=1, name=re.compile(r"\S")).is_visible()
                        and sign_in_visible,
                        "guest product website or sign-in navigation missing")
            page.screenshot(path=str(screenshots / filename), full_page=True)
            require(not server_errors and not browser_errors, "page produced server or JavaScript errors")

        for stage, path, filename, heading in (
            ("PRIVATE_GUEST", "/", "guest.png", None),
            ("PRIVATE_LOGIN", "/login", "login.png", "Welcome back"),
            ("PRIVATE_REGISTER", "/register", "register.png", "Create your account"),
            ("PRIVATE_FORGOT_RESET", "/forgot-password", "forgot.png", "Forgot password?"),
        ):
            try:
                visit(path, filename, heading)
                states[stage] = ("VERIFIED" if stage != "PRIVATE_FORGOT_RESET" else "NOT_VERIFIED",
                                 "page rendered" if stage != "PRIVATE_FORGOT_RESET" else "page rendered; reset journey pending")
            except Exception as error:
                states[stage] = ("FAIL", str(error) if isinstance(error, SmokeFailure) else type(error).__name__)
        initial_failures = [gate for gate, (state, _) in states.items() if state == "FAIL"]
        if initial_failures:
            stage = initial_failures[0]
            raise SmokeFailure(states[stage][1])

        stage = "PRIVATE_MAILBOX"
        mailbox_page = context.new_page()
        response = mailbox_page.goto(mailbox, wait_until="networkidle")
        require(response and response.status == 200, "Mailpit browser UI unavailable")
        require('mailpit' in mailbox_page.title().lower(), "Mailpit browser UI title missing")
        require(context.request.get(mailbox + "/api/v1/messages", max_redirects=0).status == 200,
                "Mailpit API unavailable")
        states[stage] = ("NOT_VERIFIED", "UI/API available; delivery pending")
        mailbox_page.close()
        response = context.request.get(base + "/private-preview/ready", max_redirects=0)
        require(response.status == 200 and response.json().get("status") == "ready", "auth/workspace/SMTP readiness failed")

        email = "preview-" + uuid.uuid4().hex + "@example.test"
        password = "Synthetic-preview-" + secrets.token_hex(18)
        replacement = "Reset-" + secrets.token_hex(18)
        stage = "PRIVATE_REGISTER"
        step = "registration form and verification-page transition"
        page.goto(base + "/register")
        page.locator("#email").fill(email)
        page.locator("#password").fill(password)
        with page.expect_response(lambda response: urlsplit(response.url).path == "/api/v1/auth/register") as reply:
            page.locator("#submit").click()
        require(reply.value.status == 201, f"synthetic registration rejected (HTTP {reply.value.status})")
        page.wait_for_url("**/verify-email?**")
        require(not context.cookies() or not any(cookie['name'] == 'tenderlens_session' for cookie in context.cookies()),
                "registration authenticated an unverified account")
        require(context.request.post(base + "/api/v1/auth/login", data={"email": email, "password": password},
                                     headers={"Origin": base}).status == 403, "unverified login was not blocked")
        states[stage] = ("VERIFIED", "SYNTHETIC_REGISTER_201; blocked-unverified-login")
        print("SYNTHETIC_REGISTER_201=VERIFIED blocked-unverified-login")

        stage = "PRIVATE_VERIFY_EMAIL"
        step = "verification email lookup"
        try:
            link = email_link(context.request, mailbox, base, email, "/verify-email", report=print)
        except SmokeFailure:
            states["PRIVATE_MAILBOX"] = ("FAIL", "verification delivery/lookup failed; see PRIVATE_VERIFY_EMAIL")
            raise
        token = parse_qs(urlsplit(link).query)["token"][0]
        step = "verification link navigation and API response"
        with page.expect_response(lambda response: urlsplit(response.url).path == "/api/v1/auth/verify-email") as verification:
            response = page.goto(link)
        require(response and response.status == 200, "verification page navigation failed")
        print("VERIFY_NAVIGATION_SUCCEEDED=VERIFIED")
        require(verification.value.status == 200,
                f"verification API rejected link (HTTP {verification.value.status})")
        print("VERIFICATION_STATUS=VERIFIED HTTP 200")
        step = "verified workspace redirect"
        page.wait_for_url(lambda url: preview_path(url, base, "/dashboard"))
        require(context.request.get(base + "/api/v1/auth/me").status == 200, "verified session unavailable")
        require(context.request.post(base + "/api/v1/auth/verify-email", data={"token": token},
                                     headers={"Origin": base}).status == 422, "verification link was reusable")
        states[stage] = ("VERIFIED", "Mailpit one-time link verified through UI; replay rejected")
        states["PRIVATE_MAILBOX"] = ("VERIFIED", "browser UI/API and verification delivery")

        stage = "PRIVATE_LOGIN"
        step = "password login and workspace initialization"
        require(context.request.post(base + "/api/v1/auth/logout", headers={"Origin": base}).status == 204, "logout failed")

        def login(secret):
            page.goto(base + "/login")
            page.locator("#email").fill(email)
            page.locator("#password").fill(secret)
            with page.expect_response(lambda response: urlsplit(response.url).path == "/api/v1/auth/login") as reply:
                page.locator("#submit").click()
            require(reply.value.status == 200, "UI login failed")
            page.wait_for_url(lambda url: preview_path(url, base, "/dashboard"))
            page.wait_for_function("typeof state!=='undefined' && state.accountId && state.organizations?.length>0")

        login(password)
        states[stage] = ("VERIFIED", "password login through UI; authenticated workspace loaded")

        stage = "PRIVATE_WORKSPACE"
        step = "shared organization creation"
        page.goto(base + "/dashboard#team")
        page.wait_for_function("typeof state!=='undefined' && state.accountId && state.organizations?.length>0")
        page.locator("#newOrganizationName").fill("Synthetic preview team")
        page.locator("#createOrganizationButton").click()
        page.wait_for_function("typeof usingSharedOrganization==='function' && usingSharedOrganization() && state.organizationId")
        page.locator("#createOrganizationButton").wait_for(state="visible")
        page.wait_for_function("document.getElementById('createOrganizationButton').disabled===false")
        step = "company creation and activation"
        page.locator('[data-nav="companies"]').click()
        # Existing new-company UI trigger; no data/state is substituted.
        page.locator('button[onclick="showCompanyForm()"]:visible').first.click()
        page.locator("#companyName").fill("Synthetic preview company")
        page.locator("#keywords").fill("office supplies")
        page.locator("#createCompanyButton").click()
        page.wait_for_function("state.activeCompanyId && state.companies.some(c=>c.name==='Synthetic preview company')")
        organization_id = page.evaluate("state.organizationId")
        step = "reload and shared organization reselection"
        page.reload(wait_until="networkidle")
        page.wait_for_function("state.organizations?.length>0 && !document.getElementById('organizationSelect').disabled")
        page.locator("#organizationSelect").select_option(str(organization_id))
        page.wait_for_function("state.activeCompanyId && state.companies.some(c=>c.name==='Synthetic preview company')")
        require(not server_errors and not browser_errors, "workspace produced server or JavaScript errors")
        page.screenshot(path=str(screenshots / "workspace.png"), full_page=True)
        states[stage] = ("VERIFIED", "UI organization/company creation and reload persistence")

        stage = "PRIVATE_FORGOT_RESET"
        step = "forgot-password form and reset email lookup"
        page.goto(base + "/forgot-password")
        page.locator("#email").fill(email)
        with page.expect_response(lambda response: urlsplit(response.url).path == "/api/v1/auth/forgot-password") as reply:
            page.locator("#submit").click()
        require(reply.value.status == 202, "forgot-password UI request failed")
        try:
            link = email_link(context.request, mailbox, base, email, "/reset-password")
        except SmokeFailure:
            states["PRIVATE_MAILBOX"] = ("FAIL", "password reset email missing or invalid")
            raise
        token = parse_qs(urlsplit(link).query)["token"][0]
        step = "reset form, single-use checks and replacement-password login"
        page.goto(link)
        page.locator("#password").fill(replacement)
        page.locator("#confirmPassword").fill(replacement)
        with page.expect_response(lambda response: urlsplit(response.url).path == "/api/v1/auth/reset-password") as reply:
            page.locator("#submit").click()
        require(reply.value.status == 200, "reset-password UI request failed")
        page.wait_for_url(lambda url: preview_path(url, base, "/login"))
        require(context.request.get(base + "/api/v1/auth/me").status == 401, "old session survived password reset")
        require(context.request.post(base + "/api/v1/auth/reset-password", data={"token": token, "password": replacement},
                                     headers={"Origin": base}).status == 422, "reset link was reusable")
        require(context.request.post(base + "/api/v1/auth/login", data={"email": email, "password": password},
                                     headers={"Origin": base}).status == 401, "old password still works")
        login(replacement)
        require(not server_errors and not browser_errors and not blocked_external,
                "journey produced server/JavaScript errors or attempted external HTTP")
        states[stage] = ("VERIFIED", "Mailpit reset link through UI; replay/old password rejected; re-login passed")
        states["PRIVATE_MAILBOX"] = ("VERIFIED", "browser UI/API and both synthetic emails captured")
    except Exception as error:
        diagnostic = str(error) if isinstance(error, SmokeFailure) else type(error).__name__ + " during " + step
        states[stage] = ("FAIL", diagnostic)
    finally:
        if browser:
            browser.close()
        if manager:
            manager.stop()
        for gate in GATES:
            state, diagnostic = states[gate]
            print(f"{gate}={state} {diagnostic}")
    return 0 if all(state == "VERIFIED" for state, _ in states.values()) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshot-dir", default=None)
    args = parser.parse_args()
    raise SystemExit(run(args.screenshot_dir))
