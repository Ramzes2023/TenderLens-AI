# Candidate fifth source: Lenobl regional small purchases

**Status: DISABLED; do not deploy until all exact-head LIVE checks pass.**

Source: `https://zakupki.lenreg.ru/Search/NewRequests`.
The official list and its distinct native `ProductRequestGroup/Index/ID`
details are verifiable without credentials. The existing source formerly
returned `deadline=None` and therefore the real VALYQON public guest search
correctly concealed all such records as unverified.

The official detail now has a visible field `Срок окончания подачи оферт`
with text `DD <Russian month> YYYY г. HH:MM:SS`. It does **not**
independently establish a timezone. The new source parser validates the
calendar/time syntax and saves the publisher's actual **local date plus clock time**
(`YYYY-MM-DDTHH:MM:SS`, no timezone), never guesses Moscow or UTC. The
source-specific active-only rule accepts a date only only when the published local clock is strictly later
than the current clock at UTC+14 (conservative worldwide bound). The
public guest response still supplies **only** title, publisher local date and clock
without a claimed timezone, price=null and currency=null, no buyer, originals or tenant data.

## Release proof

1. Confirm new date parser's adversarial tests and regression suite green.
2. Confirm official **current** native list+details are actually fetched.
   The source's real dates must include at least one verified still-open
   future day, not simply a successfully parsed expired date.
3. Verify leased Worker→**disposable** SQLite→stored ID/title/keyword query,
   idempotent same-source dedup, source allowlist and exact public-original
   HTTPS host.
4. Run separate isolated SQL release verifier
   `python -m scripts.verify_lenobl_public_site_candidate`; it must
   return `CANDIDATE_ONLY`. It can never replace first-party LIVE proof.
5. Preserve existing four working sources and isolated source SQLite
   volume with an online integrity-checked backup before any VPS deployment.
   Stage *fifth overlay last*, in this exact order:
   `compose.yaml` → `compose.south-ural.yaml` →
   `compose.kavkaz-rf.yaml` → `compose.lenobl.yaml`.
   Never use these in the production `tenderlens-vps` stack.
6. Only a verified real canonical active Lenobl notice passing the public
   HTTPS guest endpoint, after new fenced Worker receipt, with previous
   STAN/Kavkaz/South Ural and separate GigaChat still working, may justify
   `RESULT=WORKING`. Test exact API/SQLite hashes and rollback.
7. If the new official list shows only expired local closing times, **STOP/STAGED_ONLY**:
   no fifth source is activated and the four-source site stays working.

No email, Telegram, account/billing, Caddy or main production database change
is authorized by this PR. An official date-only deadline does not establish
an exact cut-off hour; users must consult the original official platform.
