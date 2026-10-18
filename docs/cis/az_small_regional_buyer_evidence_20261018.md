# CIS regional buyer audit — 2026-10-18

Scope: Azerbaijani **small municipal / district public buyers** for VALYQON AI.
These findings help prioritize *buyer-level coverage* without counting mirror
sites, generic government pages, or press releases as new procurement platforms.

## Confirmed public first-party independent small-quotation source

- `adif.gov.az/az/sale/` — Azerbaijan Deposit Insurance Fund (Baku):
  First-party live GitHub-hosted HTTPS on 2026-10-18 returned 66 public
  procurement article blocks; four notices posted 2026-10-02 for **printing,
  stationery, household products and 29 Windows 11 Pro licences**, proposals
  accepted until 2026-10-19 12:00 local. Different dated first-party tender
  DOCX specifications under `adif.gov.az/media/2026/10/09/`, not generic bidder
  templates. This is small-value *procedure type* coverage, **not** a separate
  regional procurement platform; contract estimates are unpublished.
  References: https://adif.gov.az/az/sale/
  Live DOM gate: https://github.com/Ramzes2023/TenderLens-AI/actions/runs/39115771034
  Adapter and full live worker proof are gated by PR #165.

## Grounded district / small buyer examples (secondary publication, not official
native API acceptance)

- **Qax Rayon Mərkəzi Xəstəxanası**, 2026-10-14: small quotation for stationery,
  household and assorted supplies.
  https://ru.dgmarket.com/tenders/np-notice.do?keywords=&noticeId=116179636
- **Qax Rayon Mərkəzi Xəstəxanası**, 2026-10-13: fire extinguishers, maintenance
  and alarm systems serving rural medical stations (Alibeyli, Kipchak, Gulluk).
  https://licitaciones.dgmarket.com/tenders/np-notice.do?keywords=&noticeId=116112808
- **Qax Rayon Mərkəzi Xəstəxanası**, 2026-10-10: printing, administrative and
  medical forms. https://licitaciones.dgmarket.com/tenders/np-notice.do?keywords=&noticeId=115996421
- **Zaqatala Rayon Mərkəzi Xəstəxanası**, 2026-10-08: modest fixed-inventory
  items. https://ru.dgmarket.com/tenders/np-notice.do?keywords=&noticeId=115858520
- **Zaqatala Rayon İcra Hakimiyyəti**, 2026-10-06: preparation of project
  cost/estimate papers relating to repair of the district administration.
  https://ru.dgmarket.com/tenders/np-notice.do?keywords=&noticeId=115734456

These examples reproduce national e-procurement notices, and the secondary
service does not establish an independent origin. Canonical procurement source
is Azerbaijan's national `etender.gov.az` (also cited by public institutions).
Its anonymous public search/list/detail integration requires independent
official HTTPS access, schema observation and full real leased-worker SQLite
keyword/buyer queries; **it is not certified here**, and these five mirror
records are NOT counted as integrated VALYQON sources or fresh live inventory.

## De-duplication / product safety rules

1. Prefer one official native procedure identifier + jurisdiction as canonical
   identity; link secondary district announcements as *evidence*, never as
   additional tender identities.
2. Search terms should match buyer AND works title, including Azerbaijani
   diacritics, with exact buyer provenance (Qax, Zaqatala).
3. Keep date of public posting, submission deadline and bid status separate.
   **Expired** procurement requests must not be shown as accepting offers.
4. Do not confuse *participation fee* with contract value. Unknown budget is
   null, not an invented AZN estimate.
5. Before enabling alerts: signed-off independent live HTTPS -> normalized
   notices -> fenced worker -> temporary SQLite -> real buyer-keyword search
   and all mandatory CI GREEN. Proxy/TLS bypass or HTML mocks are forbidden.
