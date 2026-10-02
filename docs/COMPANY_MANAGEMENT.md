# Company Management UX (Phase 15)

Phase 15 extends the v1.2.0 multi-company onboarding with day-to-day profile management.

## Telegram commands

- `/companies` — list profiles and show one-tap inline buttons for switching the active company.
- `/company_use [id]` — switch by id; without an id it displays the same switch buttons.
- `/company_edit [id]` — edit the active company, or a specific company by id/name.
- `/company_delete [id]` — delete the active company, or a specific company by id/name, after explicit confirmation.
- `/company_cancel` — cancel any setup/edit/delete workflow.

## Safe editing

The editor walks through name, business mode, monitoring keywords, regions and maximum contract value. Send `=` to keep the current value. For region and budget fields, `-` removes the restriction.

The wizard updates only the fields it manages. Advanced profile fields such as industry, excluded keywords, country/currency rules, security limits and available-document requirements are preserved.

## Safe deletion

Deletion requires the exact confirmation word `УДАЛИТЬ`. If the deleted company was active, the existing repository logic automatically selects another company when one exists. If no company remains, the user returns to the configured fallback profile.

## Compatibility

Existing `/company_setup`, `/company_add`, `/company_show`, monitoring, scoring, PDF analysis and API behavior remain available.
