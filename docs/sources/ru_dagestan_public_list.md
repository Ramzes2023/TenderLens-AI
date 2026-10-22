# Dagestan official small-purchase public listing (RU)

**Source ID:** `ru_dagestan_public_list`  
**Canonical listing:** https://goszakaz.e-dag.ru/smallpurchases/GzwSP/NoticesGrid  
**Default state:** DISABLED; operator must explicitly set `RU_DAGESTAN_PUBLIC_LIST_ENABLED=true` and deploy.

## Evidence and scope

GitHub Actions research run [39151966900](https://github.com/Ramzes2023/TenderLens-AI/actions/runs/39151966900) verified a direct first-party HTTPS GET of the public grid followed by anonymous, same-session, anti-CSRF HTTPS POST to the exact `NoticesJson` route, returning ten genuine JSON list records and at least two distinct official list identities. An independent isolated leased/fenced Worker → disposable SQLite → snapshot query test [39161319107](https://github.com/Ramzes2023/TenderLens-AI/actions/runs/39161319107) verified two genuine records were fetched, inserted, searched by both native ID and natural-language title terms, negative unmatched query returned no records, and replay was idempotent. Synthetic hostile-fixture tests also passed (18 tests).

These are **native original public register listings** and not independent verified detail pages. The two observed list deep links to `/smallpurchases/GzwSP/<ID>` returned HTTP 404. The alternate published `Notice?noticeLink=<ID>` route redirected to the site's `/smallpurchases/Login/Form`. Individual original detail pages and attached documents are **not accessible anonymously** and have **not** passed original-detail verification. No login bypass is attempted, and no paid/vendor credentials, cookies, or tenant search terms are sent to the upstream site. The source deliberately offers the publicly accessible official `NoticesGrid` URL for each notice and the original `tender_number` so users can locate it in the public register. The UI must not call it an independently verified clickable detail link.

The source exposes only fields from the anonymous native original **public list**: native ID, published procurement number, title, original buyer, region, and provenance summary. The 22 October 2026 draft separately adds **optional** price (`summa`), public-list posting date (`pub_date`) and submission deadline (`collecting_enddate` / `collecting_endDate`), but only if each actual JSON value passes strict amount/calendar validation. Date-only values remain date-only; absent or malformed fields stay `None`. RUB is assigned only to a validated price under the native `НМЦК` heading. None of these fields is claimed to come from a verified individual detail. Documents, legal classification, guaranteed open bidding status, and the exact time zone remain unverified. A fresh live Worker/SQLite acceptance at the exact PR head is required before claiming these optional enriched values were observed on the real current registry. The public source is not an EIS mirror and must not be counted as an independent municipality feed for each buyer.

## Activation

After the complete PR CI and release checks are green, merge the opt-in code. The default remains disabled. Deployment operators may enable `RU_DAGESTAN_PUBLIC_LIST_ENABLED=true` only after reviewing the limitations above. The connector worker's HTTPS allowlist contains only `goszakaz.e-dag.ru`, with a two-request per-job budget, bounded response size, verified TLS, no redirects and no proxies. Search terms are applied to saved local database records through the existing snapshot path; user keywords are never transferred to this regional site.

**Do not claim successful activation in the running VALYQON deployment merely from passing GitHub Actions.** The CI operates on a disposable database. Production activation requires updating deployment config and verifying an actual production worker run; neither is done here.

## 22 Oct 2026 isolated metadata acceptance gate

The draft's source-specific `ru-dagestan-public-list-optin.yml` additionally runs `scripts.ci_ru_dagestan_public_grid_metadata_live`. This is a **genuine current first-party grid → leased Worker → disposable SQLite** check requiring at least one actual parseable price and one actual deadline in the two current stored public-list records. If the upstream feed omits or changes those fields, the job must remain red; offline synthetic values and old observation cannot substitute. Regardless of its result, inaccessible detail cards, documents and external Telegram delivery remain unproved. Do not enable the production source on this change alone.
