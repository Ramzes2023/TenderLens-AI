"""Public methodology guide backed by the actual deterministic scoring policy."""
from __future__ import annotations

from html import escape

from app.scoring.engine import WEIGHTS
from app.analytics.fit import FIT_POLICY_VERSION


_CRITERIA = {
    "category": ("Relevance of goods and services", "The company product keywords are compared with the tender subject. Search keywords may broaden discovery; they are not automatic proof of fit."),
    "region": ("Delivery region", "Matches location evidence to the regions configured in the company profile. If no reliable region is present, this criterion may be unscored."),
    "budget": ("Contract budget", "Compares price against the company minimum/maximum and accepted currencies. No automatic foreign-exchange conversion is performed."),
    "bid_security": ("Bid security", "Reviews required bid-security conditions when both the notice and the company profile supply relevant facts."),
    "contract_security": ("Contract security", "Reviews performance security requirements when supported by the notice and configured company limitations."),
    "documents": ("Document readiness", "Checks available company documents against requirements found in the supplied tender material, not an actual authorization to participate."),
}
assert set(_CRITERIA) == set(WEIGHTS)


def methodology_html():
    criteria = "".join(
        '<tr><th scope="row">' + escape(_CRITERIA[key][0]) + '</th>'
        '<td>' + str(weight) + '%</td><td>' + escape(_CRITERIA[key][1]) + '</td></tr>'
        for key, weight in WEIGHTS.items()
    )
    faq = (
        ("Does a high score mean we will win?", "No. This is a compatibility estimate, not a probability of winning. The official tender document and eligibility rules decide."),
        ("What does 'Not scored' mean?", "Evidence or a company constraint is missing. Unknown is not the same as passed or failed; unscored factors are excluded from the known-evidence denominator."),
        ("Why can the Discovery score differ from PDF analysis?", "Discovery uses partial published metadata, while full-document evaluation can use additional extracted evidence. Their stages and completeness differ."),
        ("Why did my score change?", "A tender notice, evidence, company profile or scoring policy may have changed. Always inspect stage, criteria and original notice again."),
        ("Why are some sources or tenders missing?", "An unavailable source, credentials, rate limits or incomplete official records can limit coverage. Absence from search does not prove absence from public procurement."),
        ("Does VALYQON check bidder exclusion or court history?", "Do not infer legal eligibility, RNP status, lawsuit risk or contract performance from the fit score. Verified official-registry checks are separate functionality and may be unavailable."),
        ("How can I challenge a score?", "Compare the notice against the company profile, inspect criteria and explanations, confirm official source facts, then use support to report incorrect or incomplete evidence."),
    )
    questions = "".join(
        '<details><summary>' + escape(q) + '</summary><p>' + escape(a) + '</p></details>'
        for q, a in faq
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Scoring methodology and FAQ · VALYQON AI</title><style>'
        'body{font-family:system-ui,sans-serif;line-height:1.65;background:#0b1526;color:#ecf3fc;'
        'padding:clamp(16px,4vw,50px)}main{max-width:1050px;margin:auto}a{color:#a6d9ff}'
        'p{color:#bfd0e3}h1{font-size:clamp(26px,4vw,40px)}h2{margin-top:32px}'
        'table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:12px;'
        'border-bottom:1px solid #344258}th{color:#cce4ff}'
        'details{background:#172a43;margin:10px 0;padding:14px;border-radius:10px}'
        'summary{cursor:pointer;font-weight:700}small{color:#9fb1cb}</style></head>'
        '<body><main><a href="/how-it-works">← How VALYQON works</a>'
        '<h1>How matching and scoring works</h1>'
        '<p>Scores are explainable, rule-based compatibility indicators. They are not'
        ' an AI estimate of bid success, a legal review, or a certified financial risk rating.</p>'
        '<h2>Full-document criteria</h2><table><thead><tr><th>Criterion</th>'
        '<th>Weight</th><th>What evidence is considered</th></tr></thead><tbody>'
        + criteria + '</tbody></table>'
        '<p>The weighted scorer measures only the criteria for which enough facts are available.'
        ' Its separate <strong>completeness</strong> indicator shows how much of the available'
        ' policy could be assessed. Missing facts may reduce confidence and must be inspected.'
        ' Hard-stop conditions can rule out fit despite positive factors.</p>'
        '<h2>Preliminary vs full evaluation</h2>'
        '<p>Discovery uses published metadata to rank potentially relevant opportunities.'
        ' The preliminary scoring stage is deliberately not identical to an actual tender'
        ' PDF/document assessment. It has its own stricter score range, provenance and'
        ' search-time profile context. Historical preliminary fits can become stale;'
        ' no score should be read as an award prediction.</p>'
        '<p>Price comparisons require compatible currencies. Without verifiable currency'
        ' or exchange-rate evidence, do not treat a budget criterion as verified.</p>'
        '<h2>Frequently asked questions</h2>' + questions +
        '<p><small>Policy version: ' + escape(FIT_POLICY_VERSION) +
        '. Check the original official tender source before deciding to participate.</small></p>'
        '<p><a href="/dashboard#discover">Open Discover</a> · '
        '<a href="/dashboard#source-health">Source Health</a> · '
        '<a href="/dashboard#support">Support</a></p>'
        '</main></body></html>'
    )
