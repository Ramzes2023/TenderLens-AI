# Deadline reminder parser: safely interpreted timezones

The 48-hour saved-tender reminders trigger only when a source deadline contains a precise datetime and an explicit timezone.

Supported formats:
- ISO 8601 with UTC offset or Z, such as `2026-10-19T10:00:00+00:00`.
- Russian official RSS datetimes that clearly say Moscow time, such as `19.10.2026 14:00 МСК` or `19.10.2026 14:00 (MSK)`. Modern Moscow Standard Time is UTC+03:00.

**No guesses:** date-only fields, local timestamps without an explicit timezone, vague texts and malformed dates do not trigger reminders. The user must verify the actual deadline on the official tender portal. Reminders remain opt-in and globally disabled until operational configuration and live delivery acceptance.

Test actual source formats and submission-deadline amendments before production rollout.
