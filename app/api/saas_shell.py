"""Extend the existing authenticated dashboard without duplicating its services."""
PAGES = ['Overview', 'Discover', 'Recommended', 'Saved', 'Monitoring', 'AI Analysis', 'Documents', 'Companies', 'Notifications', 'Team', 'Billing', 'Support', 'Settings']


def shell_html(html: str) -> str:
    nav = ''.join(f'<a href="#{label.lower().replace(" ", "-")}" data-nav="{label.lower().replace(" ", "-")}">{label}</a>' for label in PAGES)
    shell = f'''<a class="skip-link" href="#pageHeading">Skip to content</a><button id="navToggle" class="nav-toggle" aria-controls="appNav" aria-expanded="false">Menu</button><aside id="appNav" class="app-nav"><a class="brand" href="/">VALYQON AI</a><p class="fine">Find. Analyze. Score. Win.</p><nav aria-label="Main navigation">{nav}</nav></aside>'''
    context = '''<section class="workspace-context" aria-label="Active workspace"><div id="orgControl"></div><div><span class="fine">Active company</span><strong id="activeCompanyLabel">Loading workspace…</strong><a href="#companies">Switch / manage company</a></div></section><div id="appNotice" role="status" aria-live="polite"></div><h2 id="pageHeading" tabindex="-1">Overview</h2><section id="onboarding" class="p" hidden><h2>Welcome to VALYQON</h2><p>Create a company → Add products and search keywords → Discover opportunities.</p><button id="onboardingStart" onclick="location.hash='companies';showCompanyForm()">Create company</button></section><section id="discoveryWorkspace" class="p" data-page="discover" hidden><h2>Discover opportunities</h2><p>Discovery workspace is being prepared.</p></section><section id="futurePage" class="p" hidden><h2 id="futureTitle"></h2><p id="futureText">Coming in the next phase. This feature is not available yet.</p></section>'''
    html = html.replace('</head>', '<link rel="stylesheet" href="/assets/saas.css"></head>')
    html = html.replace('<body>', '<body class="saas">'+shell)
    html = html.replace('<section class="grid">', context+'<section class="grid" id="existingWorkspace">', 1)
    html = html.replace('AI Procurement Intelligence Platform', 'Global Procurement Intelligence powered by AI')
    html = html.replace('Existing personal company and tender cards remain unchanged in this checkpoint.', 'Select a workspace before managing its companies or opportunities.')
    html = html.replace('</body>', '<script src="/assets/shell.js"></script></body>')
    return html
