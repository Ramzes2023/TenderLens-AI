# Guided company onboarding

Phase 14 adds a conversational Telegram wizard for creating a company workspace without the technical one-line command.

## User flow

Start with:

```text
/company_setup
```

TenderLens asks five questions:

1. Company name.
2. Business mode (`sell`, `buy`, `both`).
3. Products/services/search keywords.
4. Regions (or `-` for no region restriction).
5. Maximum contract value in RUB (or `-` for no limit).

The bot then shows a summary and creates the company only after the user confirms with `ДА`/`YES`.

Use `/company_cancel` at any point to cancel the wizard.

The existing `/company_add ...` command remains available for advanced users and automation.

## Important source limitation

The live tender source remains EIS RSS. `sell` mode can use it immediately to discover buyer demand. `buy` and `both` are stored in the company profile, but dedicated supplier-intelligence sources are a later module.
