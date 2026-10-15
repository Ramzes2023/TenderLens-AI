# VALYQON Phase 24S.2A Stability

Starting point: branch `phase24-professional-saas-core`, SHA
`62e518b064e22308cee8556e810efee6f853fa91`; working tree was clean.

## Audit and fixes

Monitoring used a symmetric, Unicode token/phrase matcher with conservative
Russian suffix removal. It did not remove the nominative soft sign: `профиль`
normalized to `профиль`, while `профиля` normalized to `профил`. Consequently
`алюминиевый профиль` failed against `Поставка алюминиевого профиля` (confirmed
directly against the original implementation). Added `ь` to the existing suffix
list, retaining the four-character minimum stem, case folding, ё/е normalization,
exact Latin tokens, contiguous ordered phrases and inclusion/exclusion symmetry.
No dictionary, downloads, fuzzy prefix matching or scoring changes were added.
Search keywords still take precedence in Monitoring; product keywords remain
scoring truth.

Embedded Qdrant already had an advisory OS lock around construction, operations
and close. However, lock-file byte initialization occurred before OS acquisition.
Independent creators could inspect/write the initial byte while another handle
already owned it; Windows byte-range locking makes that ordering unsafe. The
existing concurrency test exercised fresh initialization without coordinating
the start, so success was timing dependent. Qdrant itself reads/creates metadata
before acquiring its own internal lock, reinforcing the need for our outer lock.

Added a canonical-path, process-local mutex covering lock-file handling and the
entire client lifetime. The mutex uses normalized resolved paths and a guarded
weak-reference registry, so aliases share a lock and unused paths do not
accumulate indefinitely. The OS lock remains required across processes. The
initial byte is now written only after OS acquisition; Windows permits locking
beyond EOF. Both layers share the existing 30-second contention deadline. Client
close precedes unlocking; constructor and operation failures release the locks.
No retries of arbitrary Qdrant errors, lock disabling, file deletion, collection
reset, persistent client cache or SQLite thread-check bypass was introduced.

## Regression coverage

`tests/test_phase24s2a_stability.py` adds:

- Bidirectional Russian inflections, soft signs, case and ё/е normalization.
- Latin exactness, Russian derivative negatives, phrase order/adjacency, empty
  terms and short-stem boundaries.
- Real Monitoring prefilter search vocabulary, reasons and exclusions.
- Eight barrier-started threads using independent stores, path aliases and
  different collections; assertions enforce mutex coverage during construction.
- Three barrier-started spawned processes initializing fresh real local Qdrant,
  writing/reopening/searching distinct owner payloads and verifying isolation.
- Deterministic OS-lock-before-write assertion on the real platform lock API.
- Constructor and operation failure cleanup followed by successful reopening.

All existing tests and assertions are retained. New tests have no skip conditions.

`scripts/validate_phase24s2a.py` runs focused or full pytest with external TCP/DNS
blocked, loopback allowed for Windows asyncio/multiprocessing, real project
dotenv files ignored, email disabled and AI fallback disabled. Explicit synthetic
temporary configuration fixtures still execute their original assertions.
Inherited application environment settings are removed while OS/runtime settings
are retained; credential values are not inspected.
No actual credentials or project `.env` files were read. No external provider,
deployment, commit, push or Phase 24S.2B work was performed.

## Validation

Python from PATH: Python 3.12.14.

Final focused command:

```powershell
python scripts/validate_phase24s2a.py tests/test_phase24s2a_stability.py tests/test_monitoring.py tests/test_keyword_boundaries.py tests/test_rag.py tests/test_rag_ingestion.py
```

Result: **93 passed, 1 existing skip, 1 existing Starlette deprecation warning**;
exit 0. The skip is the Windows symlink privilege test.

Initial full regression: **1173 passed, 5 existing skips, 1 existing warning,
50 subtests passed**, exit 0, 356.69 seconds. This run preceded the final
shared-deadline and environment-isolation refinements.

Final full regression command: `python scripts/validate_phase24s2a.py tests -rs`.
Final full regression: **1173 passed, 5 existing skips, 1 existing Starlette
deprecation warning, 50 subtests passed**, exit 0, 325.56 seconds.
Existing skips: four Node-dependent browser/JavaScript checks (Node unavailable
on PATH) and one Windows symlink privilege check. No skip was added or changed
to obtain these results. The skipped browser checks remain unverified here.

`python -m compileall -q app tests scripts`: PASS, exit 0.
`git diff --check`: PASS, exit 0 (Git emits only CRLF conversion notices).

## Remaining risks and scope

- Validation runs on Windows; the retained POSIX flock branch needs confirmation
  on Linux CI. Spawned-process coverage uses real embedded storage, no server.
- The suffix matcher remains deliberately heuristic: irregular Russian forms
  and stems shorter than four characters are outside its coverage. Adding the
  soft sign can merge lexical ambiguities sharing a stem, just as the existing
  suffix rules can; no semantic lemmatizer is claimed.
- Cooperating local-storage callers must use this wrapper. Direct external
  Qdrant clients bypass its advisory lock. Embedded storage still serializes
  operations; this phase does not replace it with a server.
- The fix does not introduce crash-atomic document replacement or recovery from
  existing corrupt metadata. Those remain separate storage concerns.
- Scoring, tenant filters, quotas, AI, RAG contracts and Observability were not
  changed. Full regression covers their existing behavior.
