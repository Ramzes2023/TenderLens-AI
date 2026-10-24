# VALYQON AI vs Tenderplan and Kontur.Zakupki (October 2026)

## Verified competitor capabilities — reference, not copied product code

- Tenderplan publishes calendar, deadline reminders, procurement labels,
  assignment of work to colleagues, configurable alerts and supplier/customer
  research: https://tenderplan.ru/school/faq2/
- Kontur.Zakupki publishes a team kanban board, collaborative saved tenders,
  stages, comments, change tracking and alerts:
  https://zakupki.kontur.ru/site/features/komandnaya-rabota
  https://zakupki.kontur.ru/site/features/lk
- Kontur.Zakupki lists entity and market intelligence and approval flows:
  https://zakupki.kontur.ru/site/features
  https://zakupki.kontur.ru/site/articles/86820-ii_poisk_masshtabnye_izmeneniya_v_analitike_i_soglasovanie_uchastiya

## Verified implementation status of VALYQON

| Capability | Current status |
| --- | --- |
| Saved procurement shortlist | Existing authenticated company-scoped API |
| Team lifecycle stages & audit | Existing GET/PATCH with role check, revision concurrency and audit |
| Tender Planner board | Added in PR #264; renders real saved notices and fetched server stages |
| Tender Planner calendar | Added in PR #264; strict civil-date / timezone validation |
| Calendar export | Added in PR #264; user-initiated .ics, date-only all-day markers and exact UTC events |
| Changing stage on board | Added in PR #264 via PATCH, preserving existing private note and revision |
| Search templates | Existing saved-search filter service, must verify live acceptance |
| Deadline reminders | Existing explicit preference flow; needs operational delivery validation |
| Customer/supplier registry and market risk analytics | Not implemented or independently verified |
| Enterprise approvals and per-tender assignment | Not implemented |
| Automatic change tracking of upstream tender documentation | Not fully validated |
| CRM sync & external calendars | Not implemented |

## Acceptance and limits

1. Preview at http://127.0.0.1:18865/dashboard#tender-planner uses
   isolated accounts, DB and sources. To test populated states, save a real
   opportunity from an authorized existing company (no synthetic insertion).
2. The authenticated Planner reads the same company-scoped shortlist API
   and per-saved workflow endpoints as the Saved screen. No public release
   of private source/buyer fields or bypass of tenant roles.
3. It fetches statuses for up to 30 cards at a time with maximum 4
   in-flight reads, Load more explicitly, and a 300-record per-browser-view
   ceiling. UI accurately discloses the incomplete view.
4. Only valid dates with an explicit timezone, or literal YYYY-MM-DD dates,
   appear on the calendar. Date-only entries lack a verified hour; no
   timezone is guessed. ICS is downloaded only on a user click and contains
   private titles from the authorized list, so users should keep files safe.
5. Drag-and-drop is a convenience and the stage select remains accessible.
   Viewer roles cannot write. PATCH submits the current optimistic revision
   and existing note; conflicts re-read instead of silently overwriting.
6. Stages 'submitted', 'won', 'lost' are internal team notes; not verified
   official notices, contract results, bid submissions or auction actions.
7. This release does NOT provide automatic tender participation,
   customer litigation analytics, FAS data, official contract outcomes,
   source availability proof, or bank guarantees.

## Prioritized next independently acceptable milestones

1. Batch workflow-summary endpoint with strict membership checks and
   pagination to remove N-per-card requests at scale.
2. Tenant-scoped assignee, team comments and approval records with
   optimistic concurrency, audit, access-control tests and rollback.
3. Tender/source change diffs with original evidence, source versions
   and verified notifications to opted-in recipients.
4. Verified customer/supplier identity resolution and protocol/contract
   analytics using only authentic EIS/protocol evidence.
5. External calendar subscription and CRM integration requiring explicit
   permissions, tenant isolation and secure token revocation.

Never advertise these next milestones as implemented; never merge PR #264
without all final checks and real browser/source-to-user acceptance.
