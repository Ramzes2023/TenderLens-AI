# Phase24 live international Discovery — corrected evidence

Updated 2026-10-13. This report supersedes the earlier sandbox-only conclusion.
The founder supplied host evidence: PUBLIC_LIVE_SOURCE_GATE=VERIFIED, two HTTPS
calls, five real TED notices, including 704344-2026 (Latvia medical devices),
704142-2026 (Germany SaaS), and 704352-2026 (Romania cable). Canonical links are
https://ted.europa.eu/en/notice/<notice-id>/html. These are supplied prior host
facts, not newly witnessed responses in this run. No outbound requests were made.

UK Find a Tender: UNAVAILABLE, ConnectorTransportError, HTTP status unknown.
SAM.gov: AUTH_REQUIRED; no keys read or requests attempted. UK live verification
is not established. The bounded policy sanitizes URL rejection, rejected proxy,
DNS/public-IP/TLS/transport failure, non-2xx response and size-limit errors into
ConnectorTransportError. Current adapter uses the official HTTPS release-package
endpoint, stages=tender, limit<=5, publishedFrom seven-day window, no pagination,
no redirects and trust_env=False. No concrete adapter defect was established by
local code inspection. Provider blocking, policy rejection or endpoint change
remain undetermined; no speculative repair or security relaxation was made.

Prior host tests: six live Discovery Python contract tests passed; previous PDF
Discovery and Geography/i18n JS suites passed (founder supplied evidence).
Prior offline integration gate failed because main_live_discovery_contract.test.cjs
was absent. That substantive test now exists, exercising real discovery.js;
execution of the revised gate is HOST PENDING, not claimed passed.

The existing probe now evaluates fetched notices using an explicitly SYNTHETIC
industrial cable supplier and production prefilter_notice, analysis_from_notice
and score_tender. Failed/empty sources have zero evaluated notices. Unknown
money/deadlines remain null. Filtered-out notices may be scored but are explicitly
FILTERED_OUT, never called matches. Max three examples per source and aggregate;
every fetched successful-source notice is evaluated. No LLM or full PDF analysis.
See PHASE24_LIVE_TO_SCORING_REPORT.md for exact changes and host validation.

No customer profile, database, PDF, secret, production API or deployment was used.
Existing worktree changes were preserved. Backend/security/UI templates, source
adapters, monitoring and scoring engine were not edited in this run. P3.9 remains
BLOCKED. This is bounded metadata discovery, not complete lifecycle reconciliation,
procurement coverage, bid eligibility, win probability or full RAG/LLM analysis.
