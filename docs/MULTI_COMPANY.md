# Multi-company workspaces (Phase 13)

TenderLens can now keep several company profiles for one Telegram/API owner and switch the active company without changing `.env` or restarting the application.

The active company controls:

- EIS discovery keywords;
- RSS pre-filtering;
- deterministic PDF scoring;
- monitoring deduplication scope;
- score rendering for repeated PDFs and history.

## Telegram quick start

Create a profile:

```text
/company_add AluTrade | sell | алюминий, алюминиевый профиль, алюминиевый лист | - | 50000000
```

List profiles and switch active company:

```text
/companies
/company_use 2
/company_show
```

Then run `/tenders` or `/monitor_on`. When `EIS_PROFILE_FEEDS_ENABLED=true`, EIS search RSS URLs are generated from the active profile's `search_keywords` (falling back to `product_keywords`). `EIS_PROFILE_FEED_LIMIT` limits the number of generated searches per company.

## Profile fields added in Phase 13

- `business_mode`: `sell`, `buy`, or `both`;
- `industry`;
- `search_keywords` for source discovery;
- `excluded_keywords` for discovery pre-filtering;
- `allowed_countries` for future international sources;
- `min_contract_value` and `max_contract_value`.

`product_keywords` remain the deterministic scoring vocabulary. Discovery and scoring are deliberately separate so source-specific synonyms can grow without silently changing scoring rules.

## Current source boundary

EIS is a **buyer-demand / tender opportunity** source. It directly serves companies that sell goods or services into procurement. A profile may already be marked `buy`, but supplier-intelligence sources for companies looking to purchase from suppliers are a separate next-stage adapter family and are not represented as an EIS capability.

## API

Protected API routes now include:

- `GET /api/v1/companies?owner_user_id=...`
- `POST /api/v1/companies`
- `POST /api/v1/companies/{company_id}/activate`

`owner_user_id` is still an application scope key protected only by the optional global API key. Production SaaS requires real user authentication and tenant membership authorization before public exposure.

## Data model

Company workspaces are stored in the same SQLite database as tender history:

- `company_workspaces` stores the validated `CompanyProfile` JSON;
- `company_active` stores one active company per owner;
- existing monitoring subscriptions remain owner-scoped;
- monitoring deduplication is namespaced by active company so switching companies does not incorrectly suppress opportunities already seen under another profile.

For a production multi-user service, the planned migration is PostgreSQL + explicit organizations/memberships + Qdrant server/Cloud.
