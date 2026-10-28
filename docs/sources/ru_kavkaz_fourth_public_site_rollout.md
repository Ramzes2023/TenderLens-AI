# Kavkaz.RF fourth Russian source: public-site release gates

**Status:** GitHub release candidate only. No live-site deployment or
modification of production `tenderlens-vps` SQLite, Caddy, API, GigaChat,
billing, accounts, Telegram or email has been performed by this branch.

Official first-party procurement list:
https://xn--80aafvlc.xn--p1ai/purchases_sales/zakupki/tekushchie-/

The official site's *current* section may include expired same-day or older
procedure dates. The real adapter verifies an original listing row against
a separately fetched native detail, published price, native number and
public date; the website's `Прием заявок до DD.MM.YYYY` often lacks a
clock time and timezone. New public-only logic accepts the source's
unchanged `YYYY-MM-DD` deadline **only when the date is strictly after
the current calendar day at UTC+14**. This is deliberately conservative;
do not display same-day/ambiguous deadlines as open or invent 23:59 Moscow
time. All other sources continue requiring timezone-aware ISO timestamps.

This publisher's native procurement records may be cross-posted to EIS.
The present gate proves separate official URLs, not unique economic
opportunities across platforms. The public preview does not claim otherwise.

## Acceptance before deployment

- Exact-head PR CI, including a real official list → two independent
  native originals → leased Worker → ephemeral SQLite → search ID and
  dedup test, must be green.
- New current-live original gate must find at least one *future calendar
  date* among the originals, separate from the durable Worker test.
- Confirm no account/production data read or write, no fixture fallback,
  no TLS bypass, no emailed/Telegram notices or Caddy modifications.
- Use an exact-commit isolated trial Compose project with **three** files,
  in order: `compose.yaml`, `compose.south-ural.yaml`,
  `compose.kavkaz-rf.yaml`. Existing three-source production release
  stays alive until all real gate checks pass.
- Verify the actual isolated `valyqon-public-sources` Worker receipt,
  own SQL rows and nonduplication, public original canonical URLs,
  publication date, price, and the conservative deadline filter by running
  `python -m scripts.verify_kavkaz_public_site_candidate` with
  the opt-in environment. That only produces CANDIDATE_ONLY and is not
  independent source acquisition proof.
- Before promoting any sidecar, preserve and restore-test a separate
  source-volume backup with SQLite online backup and integrity_check.
  Preserve old image/containers; blue-green if safe. Do not run a
  production `docker compose up` using incomplete manifests.
- Caddy already routes guest opportunities and market aggregates to
  `guest-sources`; existing exact paths must remain byte-identical.
  The guest AI upstream remains untouched.
- Only call WORKING after a genuine **public HTTPS** query matches
  the title and unchanged date-only deadline on an actual first-party
  original. Confirm STAN and South Ural continue returning valid results,
  no expired records leak, guest AI works, main API container unchanged,
  all production SQLite volume-file SHA256 hashes unchanged and scheduler
  enqueues four sources hourly with no mail/Telegram. Observe worker
  errors over a full cycle where practical.

If the source returns no safely current original, a network gate fails,
or upstream EIS crossposting creates unhandled duplicate identities,
**STOP / STAGED_ONLY** and keep the working three-source site. Do not
change or erase source data to manufacture a green result.

**Known limitation:** date-only display is not an exact submission clock
time. The guest response retains `YYYY-MM-DD`; the user must follow
the official original for the actual submission time.
