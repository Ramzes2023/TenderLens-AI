"""Public product overview; no external assets or fabricated usage metrics."""
from html import escape


def landing_html(authenticated: bool = False) -> str:
    secondary = 'Open Dashboard' if authenticated else 'Sign In'
    target = '/dashboard' if authenticated else '/login'
    sections = [
        ('Find → Match → Analyze → Score → Win', 'Discover source notices, match available metadata to your company, then review documents and decide. Winning remains a human commercial outcome, not a prediction.'),
        ('Multi-country procurement coverage', 'Explore integrated public procurement sources across Russia, Europe, North America, Asia, Africa and Oceania. Availability depends on source configuration and access; some sources require credentials.'),
        ('Your company, your criteria', 'Use products, search keywords, markets, currencies and commercial limits to understand preliminary company fit. Data completeness is shown separately.'),
        ('AI analysis with clear boundaries', 'Metadata previews are not full document analysis. The existing PDF workflow supports structured extraction, deterministic scoring and grounded document questions.'),
        ('Monitoring and a Telegram companion', 'Review monitoring status and run supported scans. Telegram supports personal workflows and configured alerts; team notification automation is not implied.'),
        ('Organization workspaces', 'Personal and shared company contexts, authenticated sessions, membership roles and invitations keep collaboration explicit. Backend permissions govern access.'),
        ('Pricing', 'Commercial plans and billing are coming in a later phase. No checkout or payment collection is available here.'),
    ]
    cards = ''.join(f'<article class="feature"><h2>{escape(title)}</h2><p>{escape(body)}</p></article>' for title, body in sections)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VALYQON AI · Global Procurement Intelligence</title><link rel="stylesheet" href="/assets/saas.css"></head>
<body class="landing"><a class="skip-link" href="#content">Skip to content</a><header class="landing-top"><a class="brand" href="/">VALYQON AI</a><a href="{target}">{secondary}</a></header>
<main id="content"><section class="hero"><span class="eyebrow">Global Procurement Intelligence powered by AI</span><h1>Find. Analyze.<br>Score. Win.</h1><p>Turn procurement discovery into a focused company workspace. Find relevant opportunities, inspect the evidence and decide what deserves your team's attention.</p><div class="toolbar"><a class="cta" href="/dashboard#discover">Find Opportunities</a><a class="secondary" href="{target}">{secondary}</a></div><p class="fine">Metadata previews · Explainable company fit · Human decisions</p></section>
<section class="features" aria-label="What VALYQON does">{cards}</section><section class="faq"><h2>Questions before you start</h2><details><summary>Is a preliminary match a prediction of winning?</summary><p>No. It measures company fit using available metadata. Missing information remains visible and full documents need review.</p></details><details><summary>Does every opportunity include analyzed documents?</summary><p>No. Discovery returns metadata previews. Documents must be imported through supported workflows before full AI analysis.</p></details><details><summary>Can my team collaborate?</summary><p>Yes. Shared organizations support company workspaces, role-based access and invitations.</p></details></section><section class="final-cta"><h2>A clearer starting point for procurement.</h2><a class="cta" href="/dashboard#discover">Find Opportunities</a></section></main><footer>VALYQON AI · Find. Analyze. Score. Win.</footer></body></html>'''
