# VALYQON AI branding compatibility

Official product name: **VALYQON AI**. Positioning: **AI Procurement Intelligence Platform**.
Slogan: **Find. Analyze. Score. Win.** The slogan is not a guarantee of winning a tender.

This is a presentation change. No release/version bump, deployment, schema migration,
repository rename, domain change or volume migration is included.

## Preserved identifiers

| Category | Kept exactly | Reason |
|---|---|---|
| Configuration (D) | All `TENDERLENS_*` keys | Canonical existing configuration; no aliases or precedence changes |
| Infrastructure (E/H) | `tenderlens-vps`, `tenderlens_data`, image names, container user, network settings | Existing deployment compatibility |
| Storage (F) | `tenderlens.db`, Qdrant collection and point-ID namespace, cache paths | Existing data remains readable without reindexing |
| Identity/API (C/H) | `tenderlens_session`, module paths, all routes | Preserve sessions, imports and API contracts |
| Health (H) | `service: TenderLens AI` | Stable machine-readable identity; OpenAPI display title uses the new brand |
| External addresses (H) | `Ramzes2023/TenderLens-AI`, `TenderLensAI_bot` | Existing repository links and Telegram deep links must continue working |
| Source transport (H) | `TenderLensAI/0.9` RSS User-Agent | Avoid changing source integration behavior in a branding release |
| Tests (G) | Legacy names in compatibility assertions and synthetic bot usernames | Verify existing behavior; fixtures are not product branding |
| Historical records (B) | Phase 18 notes and v1.6.0 release notes | Released history must not be rewritten as a new release |
| Asset path (B/H) | `docs/assets/tenderlens-hero.svg` | Keep existing documentation links; image content uses VALYQON AI |

Current interface copy, Telegram messages, current documentation and display metadata
use VALYQON AI (categories A/B). Internal explanatory docstrings are updated where
appropriate; persisted identifiers and executable behavior remain unchanged.
The example hostname in `.env.public.example` remains a placeholder, not a domain change.

The pre-edit inventory is saved locally outside the repository as
`PHASE20_BRAND_AUDIT_BEFORE.json`; no credentials or untracked runtime files were read.
