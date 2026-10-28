# South Ural → existing isolated public site — third-source candidate

Status: **not deployed**. The existing live `valyqon-public-sources`
two-source Docker stack, Caddy routes and production data remain unchanged.

Official source: https://www.vendorportal.ru/Market/OfferInvitationOpen .
This is a genuine South Ural regional small-purchase portal and is distinct
from STAN and MikroTon. The source adapter exists in main and has earlier
live Worker→SQLite and independent buyer/price/deadline verification. A
historically successful test is NOT evidence of a currently open tender.

This proposal changes **only** an opt-in Docker Compose overlay and the
separate scheduler's exact RU allowlist. Old two-source installations
continue working as before without the overlay. No changes to source URLs,
official TLS, Caddy, production API, production SQLite, guest AI or billing.

## Acceptance gates, in order

1. Every exact-head CI check, including the new workflow, must be green.
   The live acceptance **fails** if the official portal has no current open
   future-deadline original. No archival substitutes, no synthetic offers.
2. At the VPS only, prepare a rollback/backup and stage a fresh exact
   reviewed commit. Do not change the existing project or Caddy.
3. Build new image in an independent trial and resolve configuration:

   ```sh
   docker compose -p valyqon-public-sources \
      -f ops/public_sources/compose.yaml \
      -f ops/public_sources/compose.south-ural.yaml config
   ```

4. Test original list→distinct detail URLs→actual leased Worker→isolated
   SQLite→search and exact original URLs. Verify `source_id=south_ural_public`,
   no duplicates, actual future deadline and metadata only if displayed by
   official original. Execute `python -m scripts.verify_south_ural_public_site_candidate`
   against the **isolated** live database and enabled overlay after Worker
   completion.
5. If zero current open tenders, **STOP without redeployment**, retain
   working two-source live site. If green, perform a safe isolated-sidecar
   blue-green swap, preserve the production API and SQLite, keep public
   source route and guest AI route unchanged. Restore the previous sidecar
   on any regression. Observe continuous Worker/scheduler logs.
6. Confirm independent public HTTPS search for a true **future** South
   Ural opportunity with redacted guest fields only. Confirm STAN's
   already-working original remains visible, guest AI answers correctly,
   and no expired offers are shown.

No customer Telegram, email, entitlement or payments are activated.
This source cannot be announced as live merely because PR tests are green.
