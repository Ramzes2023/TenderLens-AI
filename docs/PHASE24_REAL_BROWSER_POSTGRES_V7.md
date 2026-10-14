# Existing customer MVP acceptance — repair record

Date: 2026-10-13. Host verification pending. Production P3.9 BLOCKED.

## Successive correction: Saved reload workspace

Latest supplied Windows evidence: runtime exit 2, zero failed suites; authenticated API, PostgreSQL saved persistence and cleanup VERIFIED; authenticated browser FAIL with stage=browser_save_and_reload; TimeoutError. No completed browser proof is established. This supersedes the document-unknown failure described below.

Source tracing proves that loadOrganizations initializes a fresh page to defaultOrganization.id. The harness selected a shared synthetic organization before Save, then reloaded and waited for that shared organization's records without selecting it again. Saved correctly requires a shared active-company workspace. The corrected harness reselects the same organization with Playwright select_option after reload, waits for the genuine active company, then requires the fixture in Saved and exactly one rendered card plus the independent PostgreSQL row. It does not forge workspace state or change the application's default selection behavior. The old broad timeout does not establish which individual wait failed; the next host run must confirm this repair.

Save now observes the browser's actual POST response and requires the route's existing HTTP 200 contract, then requires the disabled Saved card control. Separate stages distinguish response, confirmation, navigation, reload workspace, reload records and database read. Condition timeouts include fixed expected/actual classifications and discard Playwright exception messages. Regression coverage checks reload ordering against the actual organization initialization and verifies redaction of browser timeout details.

Edited only the existing V7 harness, its Python/JS regression files and the two acceptance reports. Earlier TCP readiness, profile_version, document unknowns, role checks, cleanup, screenshot durability and environment protections remain intact. Scoped diff whitespace check passed; Python, Node, Docker and Chromium execution were not available in this sandbox. Fresh Windows host suites and runtime are pending. CUSTOMER_MVP_LOCAL_GATE=NOT_VERIFIED; P39_PRODUCTION_GATE=BLOCKED. No public calls or external TED reprobe were made.

## Latest V7 closeout repair: document unknowns

The latest supplied Windows host run passed database initialization and company creation, then failed at `document unknowns` (exit 2; all customer gates FAIL; cleanup VERIFIED; zero failed suites; no retained screenshot). This supersedes the historical 422 status below. The TCP readiness and required profile_version fixes remain intact.

The actual discovery route builds metadata_analysis with analysis_from_notice and preliminary_scoring with score_metadata_preview. ScoringResult.missing_information copies the extraction list, which is empty for metadata fixtures. Document uncertainty lives in preliminary_scoring.criteria: code=documents, status=not_scored, earned_points=0, with an explanation that no required-document list was found. There is no unknowns field; document_risks is a separate factual risk list. Requiring nonempty missing_information was the faulty assertion.

The harness now requires that document criterion, zero points, explanation, empty metadata requirements and full_ai_analyzed=false for both the positive and missing-value notices. Unrelated missing information cannot excuse a false document match. The UI includes not_scored criterion explanations alongside missing_information under Unknowns to verify. Scoring engine, extraction, adapters and auth remain untouched.

Real HTTP checks now include permitted member Save, downgrade to viewer, denied Save/Delete, permitted read and denied access after membership removal, using only disposable identities. Browser Save targets discoveryResults to avoid hidden dialog controls. Genuine Chromium Find, safe anchors, Save/reload, PostgreSQL reads and post-cleanup screenshot remain required.

Stage-labelled feedback exposes safe assertion classifications or exception types, never third-party exception messages. Regression checks exercise the real discovery serializer/scorer, reject falsely scored or invented documents, and execute the shipped unknown renderer with escaping checks; they do not award browser acceptance.

Source review and scoped whitespace checks were performed here. Python/Node suites and native Docker/Chromium runtime await Windows host execution. CUSTOMER_MVP_LOCAL_GATE=NOT_VERIFIED; P39_PRODUCTION_GATE=BLOCKED. No public source calls or external TED reprobe occurred. All runtime gates, suites and durable screenshot must pass before the host may report VERIFIED.

The earlier host run failed during isolated application database initialization with StorageError. The latest supplied host execution progressed to POST /api/v1/organizations/3/companies, which returned 422 instead of 201. Runtime exit was 2; authenticated API, browser and PostgreSQL saved persistence were FAIL; cleanup was VERIFIED. Host test suites reported zero failures. No completed customer-flow acceptance or retained browser screenshot was established.

## Corrective pass: company fixture contract

Both profiles() fixtures omitted profile_version. The existing OrganizationCompanyCreateRequest requires a CompanyProfile, whose profile_version field has no default. Thus the harness's company payload fails request validation before company creation; owner_user_id is not required by this organization-scoped endpoint. Both synthetic profiles now carry v7-synthetic-1, including the alternate-company payload that reuses the accounting profile. Production schemas and application behavior are unchanged.

A regression test validates both fixture payloads against the actual OrganizationCompanyCreateRequest model and checks that deleting profile_version reproduces the nested required-field validation error. This checks the endpoint contract without weakening validation or awarding HTTP/browser acceptance. The new test and corrected runtime still require host execution.

## Demonstrated harness defects and corrections

The old Docker probe used Unix-socket pg_isready. It could accept the official image's temporary initialization server before TCP service starts. It also treated container readiness as proof of Windows host access. The repaired probe explicitly uses container TCP port 5432, checks the inspected localhost-only published port, probes Windows loopback with a bounded retry, and authenticates with psycopg against the generated database/user/server identity before spawning the application.

An internal Docker bridge can prevent published-port forwarding. This is a candidate cause of the supplied failure, not a host-confirmed diagnosis. The harness first tests that exact configuration. Only a failed host TCP probe triggers replacement of its own uniquely named container/network with a private bridge with IP masquerading disabled. Publication stays on 127.0.0.1 at the same random high port. No host firewall or existing resources are changed. Disabling masquerading minimizes ordinary container internet egress; it is not a packet-level deny-all guarantee on every Docker configuration. Only PostgreSQL runs there. Application source factories remain offline MockTransport fixtures, Python socket connections are restricted to loopback, and browser page requests are restricted to the app origin. Native libpq sockets bypass Python monkeypatches: their protection is the validated explicit loopback URI. Browser background networking is disabled by launch flags; packet-level native-process isolation is not certified.

The application pool already consumed the explicit generated URI. No inherited-DATABASE_URL defect was demonstrated in that constructor. The child now also replaces DATABASE_URL with that validated URI, drops inherited PG settings, disables dotenv before application imports, and preserves isolated PYTHONPATH and PLAYWRIGHT_BROWSERS_PATH. Production configuration and .env are untouched.

## Evidence and acceptance

The JSON contains independent API, Chromium and PostgreSQL gates, cleanup, screenshot_path and outbound_public_calls. Sanitized database_stages distinguish container readiness, port binding, internal/fallback host TCP, host authentication, child authentication, application pool, migration and application setup. Raw exception messages, connection URLs, passwords and cookies are not emitted. Browser setup is recorded separately. Offline fixture request counts and blocked Python socket attempts are recorded; outbound_public_calls=0 describes the offline source design, not an unperformed packet capture.

Real HTTP verification/login and HttpOnly sessions create two synthetic tenants. Acceptance checks anonymous and tenant denial, hostile Origin, positive relevance, negative exclusion, currency stop, unknowns, partial-source failure, duplicate Save, independent PostgreSQL reads and company switching. Genuine Chromium fills login, selects organization, activates company, clicks Find opportunities and Save, checks score/unknown text and escaped markup, then reloads Saved and checks the PostgreSQL row. A PNG is written outside the temporary profile and checked for existence/signature after cleanup. A missing retained screenshot invalidates browser acceptance. No VM/mock browser awards acceptance.

Only unique owned app/container/network/profile resources are removed. No source adapters or application UI were changed. Missing prerequisites return BLOCKED; executed failures return FAIL; VERIFIED requires actual successful runtime assertions. Existing earlier-stage results are not relabeled.

## Validation state

This sandbox cannot discover python, python3, py, node or docker. Python/Node regression tests and real Docker/Chromium execution are NOT RUN here. No successful new runtime JSON or screenshot exists here. The host wrapper owns immediate execution and durable JSON output using the existing --run --report interface. No host PASS is claimed.

Contract tests cover the actual organization company request schema, inherited tripwire replacement, isolated Playwright path retention, rejected database identities, container readiness not replacing host TCP, sanitized assertions, real browser APIs and screenshot disappearance after temporary cleanup. Host execution must validate the repaired path and record any concrete failing stage before customer acceptance can be awarded.
