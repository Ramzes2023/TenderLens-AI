# North Caucasus first-party and regional store small purchases — research only

Date: 2026-10-18. **Not registered, not enabled, not ingesting, not included in source_count.**

## Why this track is separate

Existing branches already contain unfinished first-party Dagestan research (PR #177)
and Stavropol RTS-Market originals research (PR #195). Do not edit or merge those
from this track. Do not mistake five storefront addresses for five independent
publishers: regional SberB2B frontends may all share one underlying operator/data
feed, so tender-ID/origin-based deduplication is required before any source count.

## Official legal basis and candidates

| Locality | Candidate storefront (pinned) | Provenance | Status |
|---|---|---|---|
| North Ossetia–Alania | https://15.portalregion.ru/ | RSO Government Resolution No. 151 of 2023-04-25 explicitly designates this site as the public/closed procurement portal | Research: original live list-to-detail proof required |
| Kabardino-Balkaria | https://kbr.sberb2b.ru/ | Public regional SberB2B storefront directory listing, not an official government declaration | Research: public notices and independent original detail unknown |
| Nalchik (municipal) | https://nalchik.sberb2b.ru/ | Public storefront directory listing | Research: possible overlap with KBR, no distinct notice proof |
| Karachay-Cherkessia | https://kchr.sberb2b.ru/ | Public storefront directory listing | Research: original notices and buyer coverage unproved |
| Dagestan (operator view) | https://dagestan.sberb2b.ru/ | Public storefront directory listing | Research: do not count as replacement for first-party official Dagestan PR #177 |

Primary governmental legal source: https://ossetia-gov.ru/doc/20749

Directory discovery only (not tender-level evidence):
https://litender.ru/malye-zakupki/

*Ingushetia and Chechnya*: no independently validated local original public
small-purchase portal was confirmed in this round. Do **not** invent a domain or
use third-party index aggregators as equivalent to first-party procurement
notices. Continue discovery of local public & private owners separately.

## Acceptance rules

Run `python -m pytest -q tests/test_ru_north_caucasus_small.py` for **offline
parser/security** checks. Synthetic fixture PASS does not prove feed viability.

Run `python -B -m scripts.research_ru_north_caucasus_small --region north_ossetia`
(or another fixed allowed `--region`) for **real live procurement evidence**.

The live gate requires the following all at the **same fixed public host**:

1. Original current public table with two distinct procurement notice IDs,
   corresponding genuine human-readable subject names and original links.
2. Two separate public HTTPS GET detail documents, independently confirming
   their exact numbers and subjects, identifiable buyer, and native money/price.
3. No login, redirect, cross-domain, arbitrary API, credentials, proxy,
   environment transport settings, fake responses or TLS downgrade.
4. Only after legitimate real list/detail access is verified: implement normal
   project adapter -> fenced leased worker -> disposable SQLite -> user keyword
   search -> tenant-safe scoring. Run full PR CI on exact head before merge.

Current site-specific route structures are *not* guessed as facts. The
conservative parser is deliberately allowed to report BLOCKED until the genuine
public read-only route is documented. A 200 homepage or a green offline parser
alone must not turn into an "integrated" source.

No production DB, source catalog, AWS deployment, or operator settings changed.
