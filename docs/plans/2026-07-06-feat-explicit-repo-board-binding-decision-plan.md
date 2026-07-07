---
title: "feat(setup): make the repo→board binding an explicit, recorded decision"
type: feat
status: active
date: 2026-07-06
github_issue: 64
---

# feat(setup): make the repo→board binding an explicit, recorded decision ✨

## Overview

The lifecycle bootstrap (`scripts/bootstrap_lifecycle_board.py`) creates a GitHub Projects v2 board, links it to the origin repo, and commits the board's identity to `agentic-engineering.md`. But it stops there: **how a repo's issues actually reach the board is left as an unexplained, orphaned manual checklist item** (`skills/setup/SKILL.md:164–170` — "configure the board's auto-add workflow in the GitHub UI") with a matching doctor non-check (`commands/lifecycle-doctor.md:63` — "never checked by the doctor … verify by hand").

This is a real gap because Projects v2 boards are **materialized collections, not live queries** over a repo. Creating an issue does *not* place it on any board, and the built-in auto-add workflow is **forward-only** — it never backfills. A new user finishes bootstrap with a board that *looks* ready but silently receives nothing.

This change converts that orphan into **two explicit, recorded, orthogonal decisions** made during bootstrap and verified concretely by `/lifecycle-doctor`:

- **(A) Forward binding** — how do *new* issues reach the board going forward?
- **(B) Backfill** — do you want the *existing* issues on the board *now*?

They are independent: backfill is relevant under **any** forward choice (someone on `workflow-only` may still have a pile of pre-existing issues to track), so (B) must **never** be gated behind the auto-add branch.

## Problem Statement / Motivation

Today the setup leaves three things unstated and unrecorded:

- **Which** board this repo's issues tie to and **how** new issues get there — recorded nowhere, so it cannot be re-run deterministically or verified.
- **Whether** existing issues are on the board — auto-add's forward-only nature means the board is *never* guaranteed to reflect the full repo, and there is no in-flow way to fix that.
- The decoupling itself (issue creation ≠ board membership; boards are collections, not queries) is never explained, so the user cannot reason about the gap.

Because the choice is unrecorded, `lifecycle-doctor` can only emit a generic "verify by hand" line it cannot actually check — it has no recorded intent to verify against.

## Proposed Solution

After board identity is committed (bootstrap **step 8**, `write_committed_config`, `bootstrap_lifecycle_board.py:516–530`), insert an explicit binding stage:

1. **Explain the decoupling** (skill prose, `skills/setup/SKILL.md` Step 3.6): issue creation ≠ board membership; boards are collections not live queries; auto-add is forward-only.
2. **(A) Record how new issues reach the board** — persist one of `workflow-only` (default) · `auto-add` · `none` to committed config.
3. **(B) Independently offer a one-time backfill** of existing issues — regardless of (A) — via a new idempotent `lifecycle_board.py --backfill` verb, and record a high-water marker.
4. **Record both decisions** in `agentic-engineering.md` (committed — this is shared board↔repo identity, not per-machine state), so they're deliberate and re-runnable, and so `lifecycle-doctor` can **verify the chosen forward binding concretely** (mirroring the existing `board_repo_link` check) rather than printing an uncheckable manual step.

### Design decisions (resolving the spec's implicit questions)

These were left implicit by the issue; resolved here with defaults grounded in the existing code. **The one genuine scope boundary — who scaffolds the auto-add YAML — is called out in Dependencies & Risks for approval.**

| # | Question | Decision |
|---|----------|----------|
| 1 | Config key names & value enum | Flat scalars (the only thing `parse_frontmatter` supports, `lifecycle_board.py:226–239`): `github_project_forward_binding: workflow-only\|auto-add\|none` and `github_project_backfilled_through: <highest issue# backfilled>`. |
| 2 | Backfill enumeration source | Paginated `gh issue list --state open --json number` — **NOT** `_item_list` (hard-capped at `READY_WORK_LIMIT = 50`, `lifecycle_board.py:919` — would silently drop issues 51+). |
| 3 | PRs on the board | Excluded for free: `gh issue list` returns issues only, never PRs (unlike `gh search issues`). |
| 4 | Closed issues | Skipped by default (open-only). Adding a long-closed issue at `stub` would contradict the "Item closed → shipped" automation. `--include-closed` is out of scope for this PR (noted as future work). |
| 5 | Idempotency mechanism | One paginated board-membership read (set of issue numbers already on the board) → set difference against repo issues. **Not** an N+1 per-issue `fetch_issue_state`. |
| 6 | Backfill marker semantics | High-water issue number, so Req 4's "re-offer when new un-added issues exist" is computable: re-offer iff `max(open issue#) > github_project_backfilled_through`. A bare boolean cannot answer that. |
| 7 | Partial failure | Adopt `verb_reconcile`'s pattern (`lifecycle_board.py:969`): collect failures, never abort the loop, report `{added, already_present, skipped_closed, failed}`; use `_run_gh_retry` (403/429 backoff, `lifecycle_board.py:151`). Persist the high-water mark only up to the last contiguous success. |
| 8 | Non-interactive contract | New flags `--forward-binding {workflow-only,auto-add,none}` and `--backfill/--no-backfill`, mirroring the existing `--probe/--no-probe`. Interactive prompts guard on `sys.stdin.isatty()`. CI/non-TTY defaults: forward-binding = `workflow-only`, backfill = **off** (never mutate the board unattended). |
| 9 | Atomicity with step 8 | Extend `write_committed_config`'s `keys` dict (`bootstrap_lifecycle_board.py:521`) so identity + both decisions land in a **single** `_upsert_frontmatter_keys` write — a crash can't leave identity-without-policy. |
| 10 | Ordering vs. probe (step 9) | Backfill runs **after** the probe's scratch-issue cleanup so the scratch issue can never be backfilled. |

### Where the code changes land

- **`scripts/lifecycle_board.py`** — new `verb_backfill(ctx, runner)` + `--backfill` dispatch (near `main` 1200–1235); a paginated repo-issue enumerator and a paginated board-membership reader (the existing `project_linked_repos` at 1061 is the shared-helper precedent); a new `github_project_forward_binding` / `github_project_backfilled_through` reader alongside `read_board_config` (258–300); a new doctor check `board_forward_binding` in `verb_doctor` (1090–1193) modeled exactly on `board_repo_link` (1158–1168).
- **`scripts/bootstrap_lifecycle_board.py`** — a new binding stage (step 8b) after `write_committed_config`; extend that function's `keys` dict to carry the two decisions; new `--forward-binding` / `--backfill` argparse flags with `isatty` guarding.
- **`skills/setup/SKILL.md`** — replace the orphaned manual bullet (164–170) with the decoupling explanation + the two recorded decisions; update the fork/clone re-bootstrap guidance (175–193).
- **`commands/lifecycle-doctor.md`** — replace the line-63 "never checked / verify by hand" caveat with the concrete per-branch check description; update the Board-schema check list (24–31).
- **Tests** — extend `ConfigWriteTest` and `LinkRepoTest` (`tests/bootstrap_lifecycle_board_test.py:402–537`) for the new keys/stage; add `BackfillTest` + doctor-check tests in `tests/lifecycle_board_test.py`; record any new `gh` fixture **live** into `tests/fixtures/gh/` with a `.meta` sidecar (see Dependencies & Risks — load-bearing-fixtures rule).

## Technical Considerations

- **GraphQL literal inlining (critical, from `docs/solutions/integration-issues/gh-api-graphql-list-object-variables.md`):** any new mutation that carries list-of-objects input must inline it as a GraphQL literal in the document — `gh api graphql -f/-F` only carries scalars. Backfill's `addProjectV2ItemById` path already goes through `gh project item-add` (via `verb_set_status`, `lifecycle_board.py:839–845`), which sidesteps this — prefer reusing that verb over hand-rolling the mutation.
- **Owner-agnostic queries (critical, from `docs/solutions/integration-issues/github-graphql-owner-resolution.md`):** any new GraphQL that resolves the owner must use `repositoryOwner(login:)` with both `... on User` and `... on Organization` inline fragments (the pattern at `bootstrap_lifecycle_board.py:405–420`) — `organization(login:)` on a user account is a hard error.
- **Fork-trap discipline:** every new `run_gh` call passes explicit `--repo`/`--owner` (asserted by the argv-recording fakes; `lifecycle_board.py:137–140`).
- **Error contract:** new verb honors the `{ok, error_code, error, fix}` stdlib-only contract (`lifecycle_board.py:109–124`).

## System-Wide Impact

- **Interaction graph:** bootstrap step 8b writes config → `/lifecycle-doctor` reads it back and asserts the forward binding → `/workflows:*` commands (workflow-only mode) continue to add their own items as they plan/work. Backfill is a one-shot side path that mutates the board via `gh project item-add`.
- **Error propagation:** backfill adopts `verb_reconcile`'s collect-and-continue contract; a single `addProjectV2ItemById` failure degrades to a `failed` count, never aborts. Bootstrap's binding stage is **non-fatal** (mirrors `link_repo`'s folded-warning pattern, `bootstrap_lifecycle_board.py:667–671`) — a binding-record failure must not fail the whole bootstrap.
- **State lifecycle risks:** the high-water marker is written only up to the last contiguous backfill success, so a re-run resumes rather than re-adds. Identity + decisions are one atomic write (decision #9). The (A)↔(B) contradiction (backfill masks a forward gap under `workflow-only`) is surfaced to the user in prose, not silently recorded as "complete".
- **API surface parity:** the decision is exercised by three surfaces — bootstrap (writes), doctor (verifies), and the setup skill (explains). All three must speak the same enum literals.

## External System Wiring

- **System:** GitHub Projects v2 (board owned by `github_project_owner`, number `github_project_number`) + GitHub Actions (only in the `auto-add` branch).
- **Config objects:**
  - `auto-add` branch needs `.github/workflows/add-to-project.yml` (the `actions/add-to-project` Action) **and** a PAT/App-token repo secret — the default `GITHUB_TOKEN` cannot write Projects v2 (from the parent plan's live-verified research and issue #63).
  - `workflow-only` / `none` need **no** external wiring and **no** standing token.
- **Where config lives:** the workflow file in-repo; the token secret in the repo's Actions secrets (provider UI — never readable back).
- **Verification step:** `/lifecycle-doctor` asserts, per branch — `workflow-only` → PASS + assert no orphaned auto-add workflow; `auto-add` → assert the workflow file exists, references the project, and the board is repo-linked (`project_linked_repos`), then **WARN that the token secret is unverifiable** (secrets are write-only — this limitation is an explicit acceptance criterion, not a silent gap); `none` → informational PASS. A recorded-(A)-vs-live mismatch (config says `auto-add`, file missing) → WARN with a copy-paste fix, mirroring `board_repo_link`.

## Acceptance Criteria

### Config schema & atomicity
- [x] Two flat frontmatter keys — `github_project_forward_binding` (enum `workflow-only|auto-add|none`) and `github_project_backfilled_through` (integer high-water issue #) — written to committed `agentic-engineering.md`.
- [x] Both written in the **same** `write_committed_config` call as board identity (extend its `keys` dict; one `_upsert_frontmatter_keys` write).
- [x] Reader validates the forward-binding value against the enum and rejects unknown values (mirror `verb_set_status`'s `STAGES` guard).
- [x] `ConfigWriteTest` extended to prove byte-preservation still holds with the new keys (append-absent, update-in-place, empty-frontmatter, survives `read_board_config`).

### Backfill correctness (new `--backfill` verb)
- [x] Enumerates repo issues via **paginated** `gh issue list --state open` — not the 50-capped `_item_list`.
- [x] Excludes PRs (free via `gh issue list`); skips closed issues by default.
- [x] Idempotent: skips issues already on the board via **one** paginated membership read, not N+1.
- [x] Uses `_run_gh_retry`; one failure never aborts the loop; reports `{added, already_present, skipped_closed, failed}`.
- [x] Persists `github_project_backfilled_through` to the last contiguous success so re-runs resume.
- [x] `BackfillTest` covers: nothing-to-add, some-already-present, pagination past 50, partial-failure-continues, resume-from-high-water.

### Doctor, per branch
- [x] `workflow-only` → PASS + assert no orphaned auto-add workflow file exists.
- [x] `auto-add` → assert workflow file present + references project + board repo-linked; WARN token secret unverifiable.
- [x] `none` → informational PASS.
- [x] Recorded-(A)-vs-live mismatch → WARN with copy-paste fix (mirror `board_repo_link`).
- [x] Line-63 "verify by hand" caveat removed from `lifecycle-doctor.md`; Board-schema check list updated.

### Non-interactive & re-run
- [x] `--forward-binding {workflow-only,auto-add,none}` and `--backfill/--no-backfill` flags exist; prompts guard on `sys.stdin.isatty()`; CI/non-TTY defaults = `workflow-only` + backfill off.
- [x] Re-run with an unchanged (A) is silent; backfill re-offered only when `max(open issue#) > github_project_backfilled_through`.
- [x] Changing (A) on re-run diffs old→new: downgrade (auto-add→workflow-only/none) WARNs about the now-orphaned workflow/secret; upgrade prompts to provision. (Warn-only if full remediation is deferred — state which.)

### Process
- [x] Backfill runs after the probe's scratch-issue cleanup (never backfills the scratch issue).
- [x] `bootstrap_lifecycle_board_test.py` + `lifecycle_board_test.py` green; any new `gh` fixture recorded live with a `.meta` sidecar and fed through its real parser (load-bearing).
- [x] Version bumped `3.1.0 → 3.2.0` in `plugin.json` **and** `marketplace.json`; `CHANGELOG.md` "Added" entry (style: the 3.1.0 `link_repo` bullet); `bun test` (plugin-consistency) green.
- [x] **Live-verify once** against the real board before shipping (see risk below).

## Success Metrics

- A fresh bootstrap ends with the forward binding recorded and doctor-verifiable — zero "verify by hand" lines for repo→board binding.
- Backfill on a repo with >50 pre-existing issues adds **all** of them (proves the 50-cap bug is avoided), idempotently.
- Re-running bootstrap on an unchanged repo makes no board mutations and prompts nothing.

## Dependencies & Risks

- **⚠️ Scope boundary needing sign-off — who scaffolds `add-to-project.yml`?** The issue frames #64 as the *wrapper* (record + verify the decision) and sibling **#63** as the *mechanism* (scaffold the `actions/add-to-project` workflow). Two options:
  - **(i) Defer to #63 (respects the issue's separation):** #64's `auto-add` branch records the choice and, if the workflow file is absent, doctor WARNs with a fix pointer. Auto-add is non-functional until #63 lands. Cleanest boundary; leaves a temporary dead-end.
  - **(ii) Fold a minimal scaffold into #64:** the `auto-add` branch writes a self-contained ~20-line `add-to-project.yml`, making #64 independently functional; #63 later enriches it.
  - **Plan's default = (i) defer to #63** (matches the issue's explicit framing). Flagged for the approval gate — if you want auto-add working now, switch to (ii).
- **`gh` ≥ 2.94.0** hard prerequisite (already established by the parent plan; local was 2.79.0). New calls use only stable subcommands.
- **Load-bearing fixtures (from `docs/solutions/testing-patterns/recorded-fixtures-must-be-load-bearing.md`):** every recorded `gh` fixture must be replayed through its real consumer, or a drifted shape stays green while prod breaks. Two prior P1s in this exact subsystem were caught only by live execution — so **live-execute the backfill verb once against the real board** before shipping; unit mocks are insufficient for a foundational loop.
- **Rate limits:** a large backfill is many mutations — `_run_gh_retry` handles 403/429, but a very large repo may warrant the deferred dry-run (count-only) mode noted below.
- **No new plugin components** (a verb + config keys are not agents/commands/skills), so component counts are unchanged — but `plugin.json`/`marketplace.json` version parity is enforced by `plugin-consistency.test.ts`, so bump both.

### Deferred (out of scope, noted for follow-up)
- `--include-closed` backfill mode and add-and-stamp-terminal for closed issues.
- Backfill dry-run (count what *would* be added) before mutating.
- Full auto-add downgrade remediation (deleting the orphaned workflow/secret) beyond a WARN.

## Sources & References

- **Origin issue:** [#64](https://github.com/aagnone3/agentic-engineering/issues/64) — repo→board binding as an explicit recorded decision.
- **Sibling:** [#63](https://github.com/aagnone3/agentic-engineering/issues/63) — `actions/add-to-project` scaffolding (the forward-binding mechanism).
- **Parent plan:** [docs/plans/2026-07-05-feat-unified-lifecycle-github-projects-plan.md](docs/plans/2026-07-05-feat-unified-lifecycle-github-projects-plan.md) — the shipped board machinery this builds on (parent issue #39).
- **Bootstrap flow / commit point:** `plugins/agentic-engineering/scripts/bootstrap_lifecycle_board.py:636–676` (orchestration), `:491–509` (`link_repo` mirror), `:516–573` (`write_committed_config` + `_upsert_frontmatter_keys`).
- **Config read/write + verbs:** `plugins/agentic-engineering/scripts/lifecycle_board.py:258–300` (`read_board_config`), `:226–239` (`parse_frontmatter`, flat-scalar limit), `:826–845` (`verb_set_status` item-add), `:919` (`_item_list` 50-cap), `:969` (`verb_reconcile` partial-failure template), `:1061–1077` (`project_linked_repos`), `:1090–1193` (`verb_doctor`, `board_repo_link` check at `:1158`), `:131–157` (`run_gh` seam + retry).
- **Setup skill orphaned step:** `plugins/agentic-engineering/skills/setup/SKILL.md:164–170`.
- **Doctor caveat:** `plugins/agentic-engineering/commands/lifecycle-doctor.md:63`.
- **Test templates:** `plugins/agentic-engineering/tests/bootstrap_lifecycle_board_test.py:402–537` (`LinkRepoTest`, `ConfigWriteTest`), `plugins/agentic-engineering/tests/lifecycle_board_test.py:529–573` (`FixtureReplayTest`), `tests/fixtures/gh/`.
- **Learnings:** `docs/solutions/integration-issues/gh-api-graphql-list-object-variables.md`, `docs/solutions/integration-issues/github-graphql-owner-resolution.md`, `docs/solutions/testing-patterns/recorded-fixtures-must-be-load-bearing.md`, `docs/solutions/plugin-versioning-requirements.md`.
