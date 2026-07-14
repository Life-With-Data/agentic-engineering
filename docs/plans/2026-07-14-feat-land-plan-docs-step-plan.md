---
title: Codify a "land the groomed plan docs" step
type: feat
date: 2026-07-14
github_issue: 145
---

# Codify a "land the groomed plan docs" step

## Overview

`/workflows:groom` and `/workflows:plan` write plan documents to `docs/plans/*.md` with a
`github_issue: N` frontmatter join key — the sole bridge between docs-as-content and the
GitHub Projects board-as-state (per the `lifecycle` skill: "Docs are content; the board is
state. The join key is the only bridge"). Today nothing commits, pushes, or PRs those files:
they are left untracked in the worktree. This plan adds a defined, reusable landing step —
a new skill, **`land-plan-docs`** — that commits and PRs those plan docs, and wires it into
every command that writes them.

## Problem Statement / Motivation

- `/workflows:plan` Step 7 (github-project mode) does the tracker-side work — parent issue
  body, sub-issues, dependencies, board stamp to `planned` — but never commits the plan file
  it wrote in the preceding "Write Plan File" step.
- `/workflows:groom`'s Hard-Stop Contract explicitly forbids opening PRs: *"Groom never
  invokes `--claim`, never writes `in_progress`/`in_review`... never creates a branch or
  worktree, never edits product code, and never opens a PR."*
- `/deepen-plan` has the identical gap — it rewrites the plan file in place and even hedges
  in its own text, "(if tracked by git)," acknowledging the file may not be tracked at all.
- Net effect: the board says `planned`, but the plan doc — the artifact the lifecycle gate
  scans for by join key — can be lost to a `git clean`, a worktree prune, or simply grooming
  in one worktree and implementing in a different one. The gate can misfire (`repair_needed`)
  even though the board correctly reads `planned`, because the doc isn't where the join key
  expects it.

**Key discovery that reshapes scope:** a skill named `land-docs` already exists
(`plugins/agentic-engineering/skills/land-docs/SKILL.md`, added in #96/v3.8.0). It is **not**
a generic docs-landing utility — it is purpose-built for the **compound** step: shipping
post-merge knowledge docs (`docs/solutions/**`) as a single-issue, docs-only PR with
GitHub-native auto-merge armed at creation and no in-agent review (CI is the sole reviewer).
It is referenced only from `/workflows:compound` (confirmed by grep — zero references from
`groom.md`, `plan.md`, or `deepen-plan.md`). Its model doesn't fit the new use case as-is:
it assumes one source issue, post-merge timing, and no batching. Reusing its **name** for a
differently-shaped mechanism would be confusing, so this plan introduces a **distinct**
skill, `land-plan-docs`, that borrows `land-docs`'s proven conventions (scope check,
auto-merge-armed-at-creation, checks-decision-tree) but adapts them for pre-work, possibly
multi-doc, plan artifacts.

## Proposed Solution

Add a new skill, `land-plan-docs`, and wire it into the three commands that write plan docs:

1. **`land-plan-docs` skill** — given a list of `{issue_number, plan_doc_path}` pairs from
   one run, verifies scope, commits, branches, opens one PR covering all of them, arms
   auto-merge where allowed, and follows checks to close-out (mirroring `land-docs`'s
   decision tree for hook/CI failures).
2. **Wire into `/workflows:groom`** — after Step 7 (tracker creation) completes and before
   the groomed packet is emitted, invoke `land-plan-docs` with every plan doc written this
   run (1 for a simple item, N+1 for an epic + N children). Add a narrow carve-out to the
   Hard-Stop Contract and a PR-status line to the groomed packet template.
3. **Wire into `/workflows:plan`** — when invoked standalone (not nested under groom's
   pipeline mode), invoke `land-plan-docs` itself for the single doc it just wrote. When
   nested under groom, defer entirely to groom's batched invocation (never land twice).
4. **Wire into `/deepen-plan`** — after rewriting the plan file in place, either push an
   amend commit to an already-open `land-plan-docs` PR for that join key, or invoke
   `land-plan-docs` fresh if none exists yet.

## Technical Considerations

- **Architecture impacts:** new skill file; three command files gain a wiring step each;
  `groom.md`'s Hard-Stop Contract gains an explicit, narrowly-worded carve-out; the groomed
  packet template gains a PR-status line.
- **Performance implications:** the land step is delegated to a Sonnet sub-agent (Task
  tool) so it never consumes the primary loop's context/budget — matching groom's existing
  "Suppressed... Never auto-pick `/workflows:work`" pattern of keeping mechanical work off
  the main loop.
- **Security considerations:** never direct-pushes to the default branch, never uses
  `--no-verify`, never self-merges without either an armed auto-merge or explicit human
  approval — identical guardrails to `land-docs` and `land-pr`.

## System-Wide Impact

- **Interaction graph:** `/workflows:groom` → (Step 7 tracker creation) → `land-plan-docs`
  (Sonnet sub-agent) → GitHub (branch, commit, PR, auto-merge arm) → groomed packet. In
  parallel, `/workflows:plan` (standalone) and `/deepen-plan` each call the same skill at
  their own completion points, gated by a nested-vs-standalone check so a plan run nested
  under groom is never landed twice.
- **Error propagation:** a scope-check failure (stray non-doc file in the intended commit)
  aborts the land step and surfaces to the user — it never silently drops the doc or
  half-commits. A push-rejection race (two concurrent grooming runs) retries with a fresh
  branch-name suffix (bounded ~2 attempts) rather than failing the whole groom/plan run. A
  hook/CI failure is fixed (bounded ~2 mechanical attempts) or surfaced — never bypassed.
- **State lifecycle risks:** there is an inherent window where the board reads `planned`
  before the doc is committed/merged (the land step runs *after* Step 7's board stamp,
  since Step 7 must not be blocked on a PR merging). This is a bounded, visible gap — the
  packet must never claim `planned` without at least attempting the land step in the same
  run, and must state the resulting PR status explicitly (`landed` / `pending` / `needs
  approval` / `skipped: <reason>`), never silently. This formalizes (but does not remove)
  a gap the `lifecycle` skill already documents as an assumption: "a plan doc requires a
  merged PR to exist... a security invariant, not hygiene."
- **API surface parity:** `land-docs` (compound/post-merge/single-issue/auto-merge-only) and
  `land-plan-docs` (groom-plan/pre-work/batched/approval-or-auto-merge) are parallel but
  distinct surfaces — this plan does not unify them, since their trigger timing, scope
  allowlist, and batching needs differ enough that a forced merge would add conditionals to
  a skill that is otherwise a clean single-purpose script.
- **Integration test scenarios:**
  1. Groom a single crisp bug → one plan doc → one PR opens, auto-merge arms, packet shows
     `landed` or `pending`.
  2. Groom an epic with 3 children in one run → 4 plan docs → exactly one PR, one branch,
     one commit covering all 4.
  3. Re-run groom on an already-`planned` item → land step detects an existing open/merged
     PR for the join key and no-ops (reports the existing PR link), never re-branches.
  4. Run `/workfows:plan` standalone with unrelated dirty product-code files already present
     in the worktree → land step commits only its own join-keyed doc path(s) and succeeds;
     it does not abort merely because unrelated files are dirty elsewhere.
  5. Two concurrent groom runs (different worktrees, different issues) push at nearly the
     same time → the second push is rejected, retries with a fresh branch suffix, and still
     succeeds without failing the run.

## External System Wiring

- **System:** GitHub repository settings (not a third-party SaaS, but genuine external
  config this feature depends on).
- **Configuration object:** "Allow auto-merge" — repo Settings → General → Pull Requests →
  "Allow auto-merge" checkbox.
- **Where it lives:** GitHub repo settings UI (or `gh api repos/{owner}/{repo} -f
  allow_auto_merge=true`); not managed by this repo's IaC today.
- **Verification step:** open a test docs-only PR via `land-plan-docs` and confirm `gh pr
  merge <N> --auto` succeeds without error. If it errors, that's a repo-settings blocker —
  the skill must report it plainly (matching `land-docs`'s existing fallback text) and fall
  back to watch-then-report, never silently skip arming auto-merge.

## Acceptance Criteria

### Functional

- [ ] A new `land-plan-docs` skill exists at
      `plugins/agentic-engineering/skills/land-plan-docs/SKILL.md`, distinct from
      `land-docs`, modeled on its proven scope-check + auto-merge-arm + checks-decision-tree
      conventions but adapted for batched, pre-work plan-doc artifacts.
- [ ] `/workflows:groom`'s Hard-Stop Contract carries an explicit, narrow carve-out: grooming
      may open a docs-only PR to persist its own plan artifact(s) via `land-plan-docs`; this
      is not a lifecycle transition and is not license to branch/PR for implementation.
- [ ] After a groom run reaches `planned`, the join-keyed plan doc(s) are committed to the
      default branch or have an open PR — never left as untracked worktree files.
- [ ] Batch runs (an epic + N children groomed in one invocation) land all N+1 plan docs in
      a single PR, one branch, one commit.
- [ ] `/workflows:plan` invoked standalone (not nested under groom's pipeline mode) invokes
      `land-plan-docs` itself for its own single doc after Step 7 completes. When nested
      under groom, it defers to groom's batched invocation and never double-lands.
- [ ] `/deepen-plan` pushes an amend commit to an already-open `land-plan-docs` PR if one
      exists for the doc's join key, otherwise invokes `land-plan-docs` fresh.
- [ ] The land step runs as a delegated Sonnet sub-agent (Task tool), never inline in the
      primary orchestrating loop.
- [ ] The groomed packet template gains an explicit PR-status line (`landed` / `pending` /
      `needs approval` / `skipped: <reason>`) — never silent about doc-landing state.

### Non-Functional Requirements

- [ ] The land step scopes commits to exactly this run's join-keyed plan-doc path(s) via
      explicit `git add <paths>`; it tolerates unrelated dirty files elsewhere in the
      worktree rather than aborting on their mere presence — it aborts only when a
      `docs/plans/**` file *outside* this run's join keys is also dirty (ambiguous
      ownership).
- [ ] Before branching, the step checks for an existing open or merged PR tied to the join
      key(s) (recognizable branch-name prefix and/or label) and no-ops — reporting the
      existing PR link — instead of re-branching. Re-running groom on an already-landed item
      stays a cheap no-op, consistent with groom's own idempotency contract.
- [ ] On push rejection from a concurrent run, retry with a fresh branch-name suffix
      (bounded ~2 attempts) rather than failing the whole groom/plan run.
- [ ] Hook/CI failures are fixed (bounded ~2 mechanical attempts) or surfaced to the user —
      never bypassed with `--no-verify`; direct push to the default branch and self-merge
      without human approval/an armed auto-merge are never performed.
- [ ] The land step never blocks groomed-packet emission — it runs best-effort within the
      same turn, and the packet always states the resulting PR status explicitly.

### Quality Gates

- [ ] `plugin.json` / `marketplace.json` versions bumped (MINOR — new skill) and kept equal;
      `CHANGELOG.md` updated; both READMEs' component counts/tables updated per this repo's
      CLAUDE.md versioning requirements.
- [ ] `bun test` passes (plugin-consistency + converter suites) and `bun run typecheck`
      passes.
- [ ] The new skill's frontmatter passes the skill-creator compliance checklist (name
      matches directory, description states what + when, `allowed-tools` scoped, no
      unlinked `references/`/`scripts/`/`assets/` mentions).

## Validation

- **Automated:** `bun test`; `bun run typecheck`; `cat .claude-plugin/marketplace.json | jq .`
  and the same for `plugin.json`.
- **Integration:** run the five scenarios listed under "Integration test scenarios" above
  against a scratch/test repo or dry-run mode; confirm each produces the described PR/no-op
  outcome.
- **Manual:** run `/workflows:groom` end-to-end on a fresh crisp test issue, observe the
  board reach `planned`, the plan doc committed, a PR opened with auto-merge armed (or a
  clear approval prompt if the repo disallows it), and the groomed packet's PR-status line
  populated. Re-run `/workflows:groom` on the same now-planned issue and confirm it reports
  "already groomed" without re-branching or re-opening a PR.
- **External wiring check:** open a test docs-only PR via `land-plan-docs` and confirm `gh pr
  merge --auto` succeeds, or that the graceful "repo doesn't allow auto-merge" fallback
  message appears instead of a silent skip.
- **Rollback:** this is a purely additive change — no board/lifecycle writer semantics are
  altered. Revert the new skill file and the `groom.md`/`plan.md`/`deepen-plan.md` wiring
  edits; no data migration is needed.

## Success Metrics

- Zero groom/plan runs leave an untracked plan doc in the worktree after this ships (spot-
  checked over the next 10 groom runs).
- No incident of a downstream `/workflows:work` or `/workflows:orchestrate` run hitting
  `repair_needed` because a plan doc existed only in a different worktree.

## Dependencies & Risks

- **Risk — naming confusion with `land-docs`:** mitigated by choosing a visibly distinct
  name (`land-plan-docs`) and cross-linking both skills' descriptions to each other, the
  same way `land-docs` already cross-links `land-pr`.
- **Risk — auto-merge repo permission:** if the repo doesn't allow auto-merge, the land step
  must degrade to "open PR, ask for approval," never silently skip landing.
- **Risk — race with the board-planned stamp:** accepted as a bounded, visible gap (see
  State Lifecycle Risks above); not eliminated by this plan, only made visible via the
  packet's PR-status line.
- **Dependency:** none on other in-flight plans; this is additive to existing skill/command
  files.

## Documentation Plan

- New `plugins/agentic-engineering/skills/land-plan-docs/SKILL.md`.
- Updates to `plugins/agentic-engineering/commands/workflows/groom.md` (Hard-Stop Contract
  carve-out, new landing step, packet template),
  `plugins/agentic-engineering/commands/workflows/plan.md` (standalone-vs-nested landing
  step), and `plugins/agentic-engineering/commands/deepen-plan.md` (amend-or-create landing
  step).
- `CHANGELOG.md` entry; README component-count/table updates in both the plugin README and
  root docs per the versioning checklist in CLAUDE.md.

## Sources & References

### Origin

- Filed at the request of the user after a live groom cycle where plan docs had to be landed
  by hand via an ad-hoc Sonnet sub-agent PR cycle (issue #145 body, "What we did by hand"
  section) — that manual flow is the reference implementation this plan codifies.

### Internal References

- Existing analog: `plugins/agentic-engineering/skills/land-docs/SKILL.md` (added in
  #96/v3.8.0, git `f5015ae`, `cc8713e`) — scope-check pattern (line 39), auto-merge-armed-
  at-creation (line 152), checks decision tree (lines 55–67).
- `plugins/agentic-engineering/skills/land-pr/SKILL.md` — code-PR landing counterpart;
  frontmatter/template conventions to mirror.
- `plugins/agentic-engineering/commands/workflows/groom.md` — Hard-Stop Contract (line ~45,
  "never opens a PR... nothing else"), groomed packet template.
- `plugins/agentic-engineering/commands/workflows/plan.md` — "Write Plan File" (mandatory,
  never commits) and Step 7 "Create Tracker Issue" (tracker-only, never commits the file).
- `plugins/agentic-engineering/commands/deepen-plan.md` — rewrites the plan file in place
  with the same untracked-file gap (hedges "if tracked by git").
- `plugins/agentic-engineering/skills/lifecycle/SKILL.md` — "Docs (`docs/brainstorms/`,
  `docs/plans/`) are **content**; the board is **state**. The join key is the only bridge"
  and "a plan doc requires a merged PR to exist... a security invariant, not hygiene."
- Confirmed via repo scan: no `.lychee.toml` and no lychee usage in
  `.github/workflows/*.yml`; lychee only appears inside the optional
  `documentation-health` skill's script (gracefully skipped if uninstalled). Hook/CI-failure
  handling in this plan is worded generically rather than lychee-specific for this reason.

### Related Work

- Related issue: #145 (this plan's origin).
