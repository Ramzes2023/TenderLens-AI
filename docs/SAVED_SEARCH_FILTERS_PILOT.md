# Saved Discovery filter presets (pilot)

- API: `GET/POST /api/v1/organizations/{organization_id}/saved-searches`,
  `DELETE /api/v1/organizations/{organization_id}/saved-searches/{preset_id}`.
- Per-account, per-organization, per-active-company named filter views, at most 20,
  max 80-character name and eight allowlisted filter keys.
- Only members of a company’s organization can read their own names; viewer cannot
  create/delete. Every DB operation rechecks membership/company scope **inside**
  the transaction. No cross-tenant filter disclosure and no raw tender content.
- UI uses the same eight real Discovery controls. **Run Find opportunities first**
  before applying a saved source/currency option, because options come from the
  fetched data. Presets **only filter fetched results**. They do not modify the
  source search, schedule a scan, send a digest, or imply new-tender coverage.
- Automatic daily e-mail/Telegram digests require a separately tested source polling
  and dedup worker, explicit per-channel consent, per-tenant rate limits, actual
  SMTP/Telegram credentials and production delivery acceptance. Intentionally not
  implemented or enabled in this first safe increment.
- Schema migration 18 is immutable and included in strict offline SQLite→PG importer
  verification; production deployment and browser smoke tests remain separate.
