"""Public guidance for the implemented workspace, distinct from contractual legal terms."""
from html import escape
from .public_locale import public_html, language_selector

GUIDE = [
    ('Create and verify your account', 'Available',
     'Choose Create account, enter your email and a password of at least 12 characters, then follow the verification link. Sign in after verification. Forgot password requests a reset link without revealing whether an account exists.', '/register', 'Create account'),
    ('Choose your organization', 'Available',
     'In Team, create or select an organization for shared work. A personal workspace is also supported; an organization is required for shared company work. Accept an invitation using the invited account. Check the selected organization before editing company data.', '/dashboard#team', 'Open Team'),
    ('Build and select a company profile', 'Available',
     'In Companies, create a profile with products and services, keywords, markets, currencies and contract range. Save it and select the active company. Discovery and monitoring need an active company; incomplete profiles limit matching. Currency comparisons do not perform exchange-rate conversion.', '/dashboard#companies', 'Open Companies'),
    ('Check sources and set filters', 'Requires configuration',
     'Open Source Health to inspect configured, disabled or failing sources. In Discover, choose countries, sources and supported filters. Public-source adapters still need enabled configuration and reachable upstream services. SAM.gov and Goszakup need credentials; EIS needs configured feeds. A map outline does not establish tender coverage.', '/dashboard#source-health', 'Check Source Health'),
    ('Search and evaluate evidence', 'Available',
     'Run a search in Discover. Review the official notice, deadline, source status and partial failures. Company fit measures preliminary compatibility with your profile, not the probability of winning. Read the criteria, supporting metadata and missing information separately. Missing information is not evidence of eligibility.', '/dashboard#discover', 'Open Discover'),
    ('Save and monitor', 'Requires configuration',
     'Save an opportunity from Discover to the active company shortlist and review it in Saved. Monitoring requires a supported configured source and company profile. Supported EIS manual scans suppress previously seen notices. Personal Telegram alerts require linking and configuration; shared team notifications are planned.', '/dashboard#saved', 'Open Saved'),
    ('Analyze a PDF', 'Requires configuration',
     'Upload a tender PDF from Discover or Saved, or use AI Analysis. PDF processing and document-grounded questions require the configured analysis services. Discovery does not fetch documents automatically. Review extracted facts and citations against the original PDF; an AI answer can be incomplete or wrong. Do not upload confidential material without authorization.', '/dashboard#ai-analysis', 'Open AI Analysis'),
    ('Work with your team', 'Available',
     'Team supports organizations, membership roles and invitations. Owners and administrators manage access within server-enforced permissions; members can work on company data, while viewers have read-only access. Check your role before changing shared data. Billing, automatic document acquisition and richer recommended actions are planned, not available checkout or guaranteed outcomes.', '/dashboard#team', 'Open Team'),
]

GUIDELINES = [
    ('Use procurement intelligence responsibly', 'Informational guidance',
     'These guidelines explain responsible use. They are not contractual Terms of Service or a lawyer-approved Privacy Policy. Legal and data-processing requirements must be reviewed for your organization and jurisdiction.'),
    ('Keep the official source in view', 'Source attribution',
     'Preserve the source name and link when sharing a notice. Confirm deadlines, amendments and eligibility on the official procurement platform. Coverage can be incomplete and data can be delayed; a missing result does not mean no tender exists.'),
    ('Let people make the decision', 'Human review',
     'Use matching and AI analysis to organize review, not to replace procurement, technical or legal judgment. Check evidence and missing data. No fit score guarantees eligibility, acceptance or a winning bid.'),
    ('Respect platform rules', 'Responsible access',
     'Respect procurement-platform terms, access restrictions, licensing and rate limits. Use credentials only with permission. Do not use the service to bypass restrictions, misrepresent your capabilities or coordinate unfair bidding.'),
    ('Protect accounts and shared work', 'Account security',
     'Use a unique strong password. Never share passwords, API keys or verification and reset links. Invite only authorized colleagues, grant the appropriate role and remove access when responsibilities change. Check the active organization and company before making changes.'),
    ('Review data before uploading', 'Privacy and processing',
     'Upload only material you are authorized to process. Avoid unnecessary personal data, trade secrets and confidential documents. Confirm approved retention and processing arrangements before sensitive use. This guide does not establish a retention policy or promise that data stays in a particular jurisdiction.'),
]


def help_html(page: str) -> str:
    guide = page == 'guide'
    title = 'How it works' if guide else 'Usage guidelines'
    intro = ('A practical route from account setup to an evidence-based procurement decision. Availability depends on workspace permissions and configured services.' if guide else 'Practical principles for careful, secure procurement research and teamwork.')
    cards = ''
    for item in GUIDE if guide else GUIDELINES:
        heading, badge, text = item[:3]
        link = f'<a href="{item[3]}">{item[4]} →</a>' if guide else ''
        # Separate arrow so exact copy bindings remain independent of decoration.
        if guide:
            link = f'<a href="{item[3]}"><span>{item[4]}</span> <span aria-hidden="true">→</span></a>'
        cards += f'<article class="guide-step"><span class="availability">{escape(badge)}</span><h2>{escape(heading)}</h2><p>{escape(text)}</p>{link}</article>'
    preview = '''<aside class="guide-preview" aria-label="Illustrative review checklist"><strong>Illustrative workflow — no actual search results</strong><ol><li>Company profile → country and source filters</li><li>Official notice → fit criteria → missing information</li><li>Original document → cited evidence → human decision</li></ol><p>Example: industrial suppliers and engineering firms can compare their capabilities with procurement requirements.</p></aside>''' if guide else ''
    delivery = '''<section class="public-tour"><span class="availability">Planned</span><h2>Future capabilities</h2><p>Commercial billing, automatic document acquisition and shared team notifications are not enabled. The current workflow remains search, evidence review and supported manual actions.</p></section><section class="public-tour"><h2>Email delivery in private preview</h2><p>Verification and password-reset links require configured email delivery. In private preview or development, an operator may use Mailpit to inspect test messages. Mailpit is not a public inbox and does not imply delivery to your email provider. If delivery is unavailable, request another link later or ask your preview operator.</p></section>''' if guide else ''
    return public_html(f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} · VALYQON AI</title><link rel="stylesheet" href="/assets/saas.css"><link rel="stylesheet" href="/assets/premium.css"></head><body class="landing premium" data-public-title="{title}"><a class="skip-link" href="#content">Skip to content</a><header class="landing-top"><a class="brand" href="/">VALYQON AI</a><button class="public-menu" id="publicMenu" type="button" aria-expanded="false" aria-controls="publicNav">Menu</button><nav id="publicNav" aria-label="Product navigation"><a href="/">Product</a><a href="/how-it-works">How it works</a><a href="/usage-guidelines">Usage guidelines</a>{language_selector()}</nav><div class="toolbar"><a href="/login">Sign in</a><a class="cta compact" href="/register">Create account</a></div><div class="mobile-public-locale">{language_selector()}</div></header><main id="content"><section class="content-section"><div class="guide-intro"><span class="eyebrow">VALYQON AI</span><h1>{title}</h1><p class="lede">{intro}</p></div>{preview}<div class="guide-grid">{cards}</div></section>{delivery}<section class="public-tour"><h2>Privacy in this public experience</h2><p>No third-party tracking or remote fonts are added by these pages. Your language preference is stored on this device when storage is available. Account services use their existing session and security mechanisms.</p></section></main><footer><a href="/">VALYQON AI</a><a href="/how-it-works">How it works</a><a href="/usage-guidelines">Usage guidelines</a><a href="/register">Create account</a></footer></body></html>''')
