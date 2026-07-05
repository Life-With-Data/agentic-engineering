---
date: 2026-07-05
topic: unified-lifecycle-github-projects
---

# Unified Work-Item Lifecycle on GitHub Projects

## What We're Building

A single, faithful lifecycle for every work item flowing through the workflow commands (`/workflows:brainstorm` → `plan` → `work` → `review` → land → `compound`), tracked on a **GitHub Projects v2 board as the single source of truth and single pane of glass** — readable and writable by both humans (browser) and agents (`gh` CLI / GraphQL).

Today, grooming maturity is invisible: a hand-written stub plan and a fully brainstormed/spec-flow-analyzed plan both say `status: active`; brainstorm docs carry no completion state; orchestrate infers pipeline stage from artifact-existence heuristics (filename matching + 14-day windows); and post-merge/deployment state lives nowhere. Commands can't tell whether an item was groomed, so they re-groom or skip grooming incorrectly.

The fix:

1. **One lifecycle enum**, `stub → brainstormed → planned → in_progress → in_review → shipped → deployed → compounded` (+ `abandoned` off-ramp from any stage), stored as a custom single-select **Stage** field on the Project board.
2. **One writer per fact**: each stage transition is written by exactly one actor (the workflow command that completes the stage, or a GitHub automation for post-merge stages). Absence of advancement = ungroomed. Stamps can never over-report.
3. **Idempotent command entry gates**: every workflow command reads Stage on entry and refuses to redo completed grooming (brainstorm on a `brainstormed`+ item routes to plan; work on a sub-`planned` item routes back to grooming).
4. **Linear support removed entirely.** Beads demoted to an opt-in, non-authoritative implementer scratchpad.

## Why This Approach

Three architectures were considered:

- **Two-dimension frontmatter (grooming state × lifecycle status):** rejected — every gate would consult two fields, most combinations are nonsensical, and it splits the read surface.
- **Option A — beads as the pane, GitHub → beads one-way sync:** strong for agents (offline, in-repo, rich dependency graph), but fails the stated requirement that humans in browsers are first-class consumers. Also requires custom sync machinery (Action + reconciler) to import GitHub facts.
- **Option B — GitHub Projects as the pane (chosen):** both audiences read and write one surface. Built-in Projects automations handle the hardest faithfulness problem (out-of-band merges → `shipped`) with zero custom code. Deployment state is written by the deploy workflow already living in GitHub Actions. Native sub-issues and **native issue dependencies (blocked-by/blocks)** cover the multi-agent work queue — no brittle label conventions. State detection collapses from nine artifact heuristics to a field read + PR cross-check.

The prior frontmatter-stamping design and the `max(stamped, derived)` resolution rule dissolve: docs become pure *content*; the board holds all *state*; frontmatter keeps only the join key (`github_issue: N`).

## Key Decisions

- **Single lifecycle enum, coarse-grained**: `stub, brainstormed, planned, in_progress, in_review, shipped, deployed, compounded, abandoned`. Review/triage/test-browser/video sub-steps stay internal to `in_review` — no gate needs finer granularity (YAGNI).
- **Object model — three layers, one board**:
  - *Work item* = GitHub Issue on the Project board (Stage field, assignee, doc links).
  - *Task decomposition* = native **sub-issues** (replaces plan-checkbox children / child beads); native **issue dependencies** express blocking order.
  - *Implementer working state* = TodoWrite by default, beads opt-in — never a GitHub object.
- **One writer per stage transition**:
  | Transition | Writer |
  |---|---|
  | `stub` | triage / humans (issue creation) |
  | `brainstormed` | `/workflows:brainstorm` (only after open questions resolved) |
  | `planned` | `/workflows:plan` Step 7 (issue + sub-issues + deps created) |
  | `in_progress` | `/workflows:work` Phase 1 (claim) |
  | `in_review` | `/workflows:work` Phase 4 (PR opened, `Closes #N`) |
  | `shipped` | Projects built-in automation on PR merge (self-heals out-of-band merges) |
  | `deployed` | deploy workflow in GitHub Actions (one `gh` call) |
  | `compounded` | `/workflows:compound` |
- **Faithfulness rule**: only the owning actor advances Stage; commands never advance past the stage they complete. A stage value is proof the stage's command ran to completion.
- **Idempotency gates**: each command's entry check is a one-line Stage comparison. Orchestrate's State Detection reads Stage + `gh pr view` instead of filename/recency heuristics. Issue number = work-item identity from triage through compound.
- **Docs are content, board is state**: `docs/brainstorms/` and `docs/plans/` remain in-repo; frontmatter carries `github_issue: N` as join key; no `status:`/`stage:` in frontmatter (removes the plan-tracker-guard `status` semantics, replaces with issue-link requirement).
- **Multi-agent claim protocol**: check assignee empty → assign → re-read to confirm (optimistic check-then-set); branch naming `feat/<issue>-…` as secondary signal. Ready-work query (replaces `bd ready`): `Stage=planned`, unassigned, no open blocking dependencies — encoded once in `workflow-repo-preflight.py`, mirrored as a saved board view for humans.
- **Native dependencies, no conventions**: GitHub's blocked-by/blocks relationships are the dependency mechanism. No `blocked-by: #N` labels or body conventions — conventions are brittle.
- **Beads demoted, constitutionally non-authoritative**: opt-in private scratchpad for a single implementer on a single long-running item (multi-session/worktree). No pipeline gate ever reads a bead; nothing syncs; disposable when the sub-issue closes. If beads content matters to anyone else, it should have been a sub-issue.
- **Linear ripped out** (not extracted): 4 commands (`linear-import`, `linear-pull`, `linear-status`, `linear-sync`), the `linear-sync` skill, `agentic-plugin linear` CLI paths, and all dispatch branches in workflow commands/scripts. Git history is the archive; a companion plugin can be resurrected from history if ever requested.
- **PR body carries a display-only lifecycle projection** (issue link, stage history, plan link) — regenerated, never read back.
- **Preflight reconciler as backstop**: on entry to any workflow command, cross-check board Stage against `gh pr view` for items with PRs and repair drift, so no command acts on stale state even if automations fail.

## Resolved Questions

- **Grooming state separate from lifecycle status?** No — one ordered enum; grooming is part of the lifecycle.
- **Keep Linear?** No. Cost multiplies with the richer lifecycle (per-workspace state mapping), and it's unused; untested dispatch branches are where faithfulness dies.
- **Beads vs GitHub as pane?** GitHub Projects, because humans/browsers are first-class. Beads-as-pane remains documented above as the rejected alternative.
- **Dependency semantics on GitHub?** Native issue dependencies exist — use them; no convention layer.
- **Where do stubs live?** As Issues with `Stage=stub` on the board (not draft items) — uniform API handling, convertible provenance from triage/upstream-scan.
- **Repos without a configured Project?** Fallback is plain GitHub Issues mode (Stage as labels) — degraded but functional; preflight reports which mode is active. `none` remains for repos without GitHub.

## Open Questions

- **Migration of in-flight artifacts**: existing plans with `status:`/`bead_id:` frontmatter and open beads — migrate via a one-shot script, or grandfather them until touched? (Lean: grandfather; migrate on next command touch.)
- **Project bootstrap**: should preflight auto-create the Project + Stage field + automations via GraphQL when missing, or is setup a documented manual step? (Lean: an idempotent `setup` script/skill step; auto-create needs org-level permissions that may not exist.)
- **Review findings** (`todos/*.md`): fold into sub-issues now or keep the existing file-todo flow initially? (Lean: keep initially; scope creep otherwise.)

## Next Steps

→ `/workflows:plan` for implementation details (command edits, preflight changes, hook updates, Linear removal, docs/tests per plugin consistency checklist).
