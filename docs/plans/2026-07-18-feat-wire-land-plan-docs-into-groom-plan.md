---
title: Wire land-plan-docs into /workflows-groom
type: feat
date: 2026-07-18
origin: docs/plans/2026-07-14-feat-land-plan-docs-step-plan.md  # parent epic #145 (closed)
github_issue: 148
---

# ✨ Wire `land-plan-docs` into `/workflows-groom`

## Overview

The `land-plan-docs` skill exists and is model-invocable (issues #147, #175 landed). It commits and
opens a docs-only, auto-merge-armed PR for the join-keyed plan doc(s) a groom/plan run just wrote
under `docs/plans/**`. What remains is to **wire it into `/workflows-groom`** so that once a groom run
reaches `planned`, its plan artifact(s) are actually persisted to a PR instead of being left dirty in
the worktree — where a `git clean`, a worktree prune, or grooming-in-one-worktree-implementing-in-
another silently loses them.

This is the groom half of the parent epic (see origin: `docs/plans/2026-07-14-feat-land-plan-docs-step-plan.md`,
issue #145, closed). The sibling wiring lives in #149 (`/workflows-plan` standalone) and #150
(`/deepen-plan`); this item touches **only** the groom skill.

**Path note (issue body is stale):** #148's body references
`plugins/agentic-engineering/commands/workflows/groom.md` and a "Step 7". Commands have since migrated
to skills (`2026-07-14-refactor-migrate-commands-to-skills-plan`). The current target is
[`plugins/agentic-engineering/skills/workflows-groom/SKILL.md`](../../plugins/agentic-engineering/skills/workflows-groom/SKILL.md).
Groom has no numbered "Step 7" — tracker creation happens inside the `/workflows-plan` sub-command groom
invokes; the "after Step 7 → before packet" seam maps onto groom's **`## Completion: Verify, Then Report`**
section, after the postcondition state-read and before/as-part-of emitting the groomed packet.

## Problem Statement / Motivation

- `workflows-groom/SKILL.md`'s **Hard-Stop Contract** currently reads (paraphrased) "Groom … never
  creates a branch or worktree, never edits product code, and never opens a PR." Taken literally that
  forbids the very docs-only PR `land-plan-docs` opens. The contract needs a narrow, explicit carve-out
  so persisting the plan artifact is licensed — without becoming a loophole for implementation branching.
- Plan docs written during grooming are untracked content joined to the board only by `github_issue:`
  frontmatter. If they never reach a PR, the join key points at a doc that no longer exists after the
  worktree is cleaned. The groomed packet claims "ready to implement" while the plan is one `git clean`
  from gone.
- The groomed packet reports Stage/Plan/Sub-issues but says nothing about whether the plan was
  persisted. Silent persistence is exactly the failure this epic exists to close.

## Proposed Solution

Edit `plugins/agentic-engineering/skills/workflows-groom/SKILL.md` in three coordinated places:

1. **Hard-Stop Contract carve-out.** Add one narrowly-worded sentence: grooming *may* open a **docs-only**
   PR to persist its own `docs/plans/**` plan artifact(s) via `land-plan-docs`; this is **not** a
   lifecycle transition and is **not** license to branch or open a PR for implementation. Word it so it
   cannot be read as permission for anything beyond persisting the plan markdown.

2. **Land step in `## Completion`.** After the postcondition verifies `stage ≥ planned` **and** a
   non-null `plan_doc`, and before the groomed packet is emitted, invoke `land-plan-docs` with **every**
   plan doc written this run (1 pair for a simple crisp item; N+1 pairs for an epic + N children groomed
   in the same run — batched into one PR). Constraints, all carried from the parent plan:
   - **Delegated Sonnet sub-agent (Task tool), never inline** — matches groom's existing pattern of
     keeping heavy sub-steps out of the primary loop's context/budget.
   - **Best-effort; never blocks packet emission** — a land failure degrades the PR-status line to
     `needs approval` / `skipped: <reason>`, it does not abort the run or withhold the groomed packet.
   - **Idempotent** — `land-plan-docs` detects an existing open/merged PR by branch-name prefix and
     no-ops, so re-running groom on an already-`planned` item stays a cheap no-op (consistent with
     groom's own idempotency contract).

3. **PR-status line in the groomed packet.** Add an explicit line to the packet template — never silent —
   with one of: `landed` / `pending` (auto-merge armed, waiting on a check) / `needs approval` (auto-merge
   unavailable — names the blocker) / `skipped: <reason>`.

## Technical Considerations

- **Where "Step 7" maps.** The land invocation belongs in groom's `## Completion: Verify, Then Report`
  section, gated on the same postcondition read already there (`--gate orchestrate --issue <N>` →
  `stage ≥ planned` + non-null `plan_doc`). Do not invent a numbered step; extend the existing section.
- **Batch scope = this run's join keys.** Pass `land-plan-docs` exactly the `{issue_number, plan_doc_path}`
  pairs written in *this* groom invocation. `land-plan-docs`'s scope check aborts only if a *different*
  `docs/plans/**` file (outside this batch) is dirty — that behavior is the skill's, not groom's to
  reimplement.
- **`no_board` mode.** The packet's PR-status line applies in board and `no_board` modes alike (the land
  step is board-independent — it only persists docs and reports). Keep the existing `no_board` Stage-line
  substitution untouched; just add the PR-status line alongside it.

## System-Wide Impact

- **Interaction graph:** `/workflows-groom` → (`/workflows-plan` sub-command writes plan doc + creates
  tracker + stamps `planned`) → **new:** `land-plan-docs` (Sonnet sub-agent) → GitHub (branch, commit,
  docs-only PR, auto-merge arm) → groomed packet with PR-status line.
- **Double-land avoidance (cross-item seam with #149).** The parent plan's decision: when `/workflows-plan`
  runs **nested under groom** (pipeline mode), plan defers to groom's batched land invocation and never
  lands itself; groom owns the land step for grooming runs. #148 implements groom's ownership; #149
  implements plan's stand-down when nested. Even if both fire, `land-plan-docs` idempotency makes the
  second a no-op — but the intended design is single-ownership, so the plan text here should state that
  groom is the lander during a groom pipeline.
- **Error propagation:** the land step is best-effort — its failure surfaces in the PR-status line, never
  as a groom abort. No partial-state risk: `land-plan-docs` stages only join-keyed paths and half-commits
  nothing.
- **API surface parity:** siblings #149 (`/workflows-plan`), #150 (`/deepen-plan`) apply the analogous
  wiring at their own completion boundaries; each is a separate item and out of scope here.

## External System Wiring

**No external wiring required.** The change is markdown edits to one skill file. `land-plan-docs` uses
`gh`/`git` against the existing origin repo; the only repo-side dependency (GitHub "Allow auto-merge")
is the skill's own concern and already handled by its graceful fallback, not something groom configures.

## Acceptance Criteria

- [ ] `workflows-groom/SKILL.md`'s Hard-Stop Contract carries a narrow docs-only-PR carve-out, worded so
      it cannot be read as license for implementation branching or PRs.
- [ ] Groom invokes `land-plan-docs` in `## Completion`, after the `stage ≥ planned` + non-null `plan_doc`
      postcondition and before packet emission, batching **all** plan docs written this run.
- [ ] The land step is documented as a delegated Sonnet sub-agent (Task tool), never inline in the
      primary loop.
- [ ] The land step is best-effort and explicitly **never blocks** groomed-packet emission.
- [ ] The groomed packet template always states PR status explicitly
      (`landed` / `pending` / `needs approval` / `skipped: <reason>`), in both board and `no_board` modes.
- [ ] The plan text notes groom owns the land step during a groom pipeline (plan defers when nested — the
      #149 seam), and relies on `land-plan-docs` idempotency for re-runs.

## Validation

**How a reviewer proves this behaves — not merely that it renders.**

- **Automated:** `bun test` (the plugin-consistency + converter suites still pass after the skill edit —
  no test asserts the Hard-Stop wording today, so this guards against unrelated regressions) and
  `bun run docs:check` if the skill's docs surface is regenerated.
- **Manual:** run `/workflows-groom` end-to-end on a fresh crisp test issue; confirm exactly one docs-only
  PR opens for the plan doc, auto-merge is armed (or a clear approval prompt appears if the repo disallows
  it), and the groomed packet's PR-status line is populated (not silent). Groom an epic + 2 children in one
  run; confirm exactly one PR covers all 3 docs. Re-run groom on the now-`planned` issue; confirm it reports
  "already groomed" and the land step no-ops against the existing PR (no re-branch, no second PR).
- **Rollback:** revert the `workflows-groom/SKILL.md` edit; grooming returns to leaving plan docs
  uncommitted (the pre-change behavior). No data migration, no board state touched.

## Dependencies & Risks

- **Blocked by:** #147 (the `land-plan-docs` skill) — **already closed/landed**; this item is unblocked.
- **Related (not blocking):** #149 (`/workflows-plan` nested stand-down), #150 (`/deepen-plan`), #151
  (version/changelog/README consistency pass for the land-plan-docs work).
- **Risk — carve-out too broad:** a loosely worded exception could be read as license to open
  implementation PRs during grooming. Mitigation: word it as *docs-only, plan-artifact-only, not a
  lifecycle transition*, and keep the "NEVER CODE" guardrail intact.
- **Risk — double-land with #149:** mitigated by `land-plan-docs` idempotency and by documenting
  single-ownership (groom lands during a groom pipeline).

## Sources & References

### Origin
- **Parent epic plan:** [docs/plans/2026-07-14-feat-land-plan-docs-step-plan.md](2026-07-14-feat-land-plan-docs-step-plan.md)
  (issue #145, closed). Decisions carried forward: groom owns the batched land step after tracker
  creation and before the packet; delegated Sonnet sub-agent; best-effort/never-blocks; explicit
  PR-status line; nested-plan defers to avoid double-land.

### Internal References
- Target skill: [plugins/agentic-engineering/skills/workflows-groom/SKILL.md](../../plugins/agentic-engineering/skills/workflows-groom/SKILL.md)
  (`## Hard-Stop Contract`, `## Completion: Verify, Then Report`, groomed-packet template).
- Skill wired in: [plugins/agentic-engineering/skills/land-plan-docs/SKILL.md](../../plugins/agentic-engineering/skills/land-plan-docs/SKILL.md)
  (invocation input: a batch of `{issue_number, plan_doc_path}` pairs; reports one status line).
- Command→skill migration: `docs/plans/2026-07-14-refactor-migrate-commands-to-skills-plan.md` (explains
  the stale `commands/workflows/groom.md` path in the issue body).

### Related Work
- Related issues: #145 (parent, closed), #147 (blocker, closed), #149, #150, #151.
- Related PRs: #175 (`feat: let agents invoke the land-pr, land-docs, and land-plan-docs skills`).
