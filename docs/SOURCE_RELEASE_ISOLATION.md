# Independent procurement source release gates

VALYQON integrates original publishers one by one. A working Samara adapter
must not require the Japan JETRO site or a Kazakhstan portal to be online.
This is a release-policy separation, **not** a claim that the runtime services
do not share code or resources.

## Source-level contract

1. Use a source-owned adapter, source ID, explicit activation flag, provenance,
   request budget, tests, and live first-party acceptance. Fail closed when a
   publisher is unavailable; never replace live tenders with fixtures.
2. Source-specific **live** workflows on pull requests are triggered by files
   belonging to that source: its adapter, scripts, hostile tests or workflow.
   Do not trigger other publishers' live endpoints merely because a generic
   `app/sources/ingestion.py`, `catalog.py`, `opportunities.py`, or
   `app/sources/**` path changed.
3. Every change to shared Worker, catalog, HTTP policy, SQL, search, or scoring
   must still pass the main offline/regression CI, `Russian source contracts`,
   and any relevant cross-source security/integration tests. A demonstrated
   regression caused by the change **blocks the PR**, even if the affected
   publisher is not the one being added.
4. If a PR modifies **only** central catalog registration, shared routing or
   flags for a specific publisher (without touching that publisher's adapter,
   tests or live scripts), the reviewer must manually dispatch that publisher's
   existing live workflow via Actions before merging. Do not interpret
   path-filtered non-execution as acceptance. A source is only production-ready
   when its own current real Worker → durable storage → tenant query gate passes.
5. Independent failures of external sites remain visible and red in their own
   workflows, investigations and PRs. Never mark them skipped-success, use
   `continue-on-error` for a mandatory gate, weaken TLS, or fake a live PASS.
6. Release decisions are made from the **specific source's** current HEAD
   evidence plus shared regression/security checks; the raw total of all
   independently-triggered GitHub workflows is not a release gate. GitHub
   currently exposes no branch-required check policy; reviewers must apply
   the release criteria explicitly until a ruleset is configured.
7. Merging source code into `main` is distinct from production activation.
   Operator enables one source, performs an isolated runtime smoke test, verifies
   a user-matching genuine tender and real delivery to a consented test chat,
   and only then enables wider customer notifications.

## Workflow-file-only changes are not live-source evidence

Changing a source workflow YAML file alone runs the repository-wide
`Independent procurement source release contracts` verification and shared
`CI`, but does **not** automatically call that publisher's external live API.
Its `pull_request.paths` must list actual source-owned adapter/test/probe
files rather than the workflow file itself.

The strict workflow is still executable via `workflow_dispatch`, and
existing source-specific push triggers are retained. If the workflow edit
alters parsing, network access, commands, job dependencies, or acceptance
semantics, reviewers MUST explicitly dispatch the affected strict live
workflow on the candidate branch before merging that change. In particular,
a green trigger-contract test never means a real supplier was verified.
Where only path triggers changed, no new supplier availability claim is made.
Real upstream failures remain red in previously executed history and in
their own source PRs.

## Stage 1 — workflow path isolation

This PR isolates an initial set of fifteen observed false dependencies:

- Kazakhstan native HTML; JETRO official RSS;
- Asia six-feed and seven-feed **composite** workflows;
- B2B root/fallback and B2B real-worker;
- Dagestan public list;
- NMCK, South Ural depth/integration/metadata/research, Kavkaz.RF and STAN live/research pipelines where pull_request had no file filters.

These workflows keep their original genuine-live assertions. All that changes
is the set of pull-request file paths that automatically launch them. Explicit
`workflow_dispatch` is supported so shared-only publisher fixes can still
be individually verified. The seven-feed composite remains strict for all
seven feeds when *that aggregate* changes; it cannot be cited as Samara's
individual release gate.

This stage **does not** isolate every existing source workflow automatically.
Apply the same contract progressively to the other regional/CIS/world feeds,
including Samara's proposed workflows in PR #218 when that branch is updated.
Keep their own source acceptance mandatory. Do not combine unrelated source
failures into the Samara release gate.
