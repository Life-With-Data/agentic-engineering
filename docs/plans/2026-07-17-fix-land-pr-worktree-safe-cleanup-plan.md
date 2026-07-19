---
title: "fix: make land-pr post-merge cleanup worktree-aware"
type: fix
date: 2026-07-17
github_issue: 182
---

# fix: make land-pr post-merge cleanup worktree-aware

## Overview

`land-pr/SKILL.md` step 5 (merge) and step 6 (post-merge cleanup) assume the default branch can be
checked out in the current working tree. In the **worktree-first workflow this plugin actively
promotes** (the `git-worktree` skill and the worktree bootstrap/GC hooks from #167), the default
branch is held by the *primary* tree, so `git checkout <default>` from a linked worktree fails and
the documented "success criteria" become unreachable. The recommended workflow contradicts itself.

This plan makes land-pr's merge-verification + cleanup **branch on worktree context** — preserving
the classic single-tree path, adding a worktree-safe path, and pointing local worktree/branch
teardown at the existing worktree-aware primitive (`gc_worktrees`) — and applies the same fix to the
two sister skills (`land-docs`, `land-plan-docs`) that carry the identical hazard. It is a
**docs-only** change (SKILL.md prose + bash recipes); no product code.

Reported by a trusted MEMBER (issue [#182](https://github.com/Life-With-Data/agentic-engineering/issues/182)),
with reproduction evidence: `gh pr merge --squash --delete-branch` returned
`fatal: 'main' is already used by worktree` while `gh pr view --json state` showed `MERGED` — the
merge succeeded; only local cleanup failed.

## Problem Statement / Motivation

When land-pr runs from a **linked worktree** and the default branch is checked out in the primary
tree:

1. `gh pr merge --squash --delete-branch` **succeeds server-side** (PR merged, remote branch
   deleted) but its *local* housekeeping fails with
   `fatal: '<default>' is already used by worktree at '<primary-path>'`. The error reads like the
   merge failed and invites a wrong retry.
2. Step 6's `git checkout <default-branch>` fails for the same reason — a branch live in another
   worktree cannot be checked out.
3. `git branch -d <feature-branch>` fails when land-pr is standing *on* that branch in the current
   worktree.

Net effect: the Success criteria (`local default branch fast-forwarded`, `feature branch deleted
(local)`) are unreachable from a worktree via the documented commands, and the plugin's own two
recommended skills (`git-worktree` and `land-pr`) contradict each other on every merge.

Confirmed against the tree:
- `land-pr/SKILL.md:167` (step 5) and `land-pr/SKILL.md:174-181` (step 6) use exactly the
  non-worktree-safe primitives described.
- `git-worktree/scripts/worktree-manager.sh:289-366` — `gc_worktrees` already does the right thing
  (reaps a worktree only when merged via `git cherry`, from outside the tree, deleting the orphaned
  local branch) — but see the coverage caveat in **Risks** below.

## Proposed Solution

Rework land-pr's step 5 → step 7 so the agent follows a context-aware decision tree, and mirror the
change in the two sister lanes. Concretely:

1. **Treat server state as authoritative after `gh pr merge`.** After any non-clean merge return,
   unconditionally run `gh pr view "$PR_NUM" --repo "$ORIGIN" --json state,mergedAt`; branch on
   `state == MERGED`. **Never** decide "merge succeeded / do not retry" from the exit code or by
   matching the `fatal: ... already used by worktree` stderr string — that text is locale- and
   version-dependent. (Resolves SpecFlow Gap B.)

2. **Detect linked-worktree context with a canonical predicate** and reuse it verbatim across all
   three skills to prevent drift:
   ```bash
   # true (linked worktree) when the per-worktree git-dir differs from the shared common-dir
   is_linked_worktree() {
     [ "$(git rev-parse --path-format=absolute --git-common-dir)" \
       != "$(git rev-parse --path-format=absolute --git-dir)" ]
   }
   ```
   (Absolute path-format avoids the relative-vs-absolute false matches across git versions —
   verified in this repo: linked worktree git-dir `…/.git/worktrees/<n>` ≠ common-dir `…/.git`.
   Resolves SpecFlow Gap G.)

3. **Resolve the base from the PR, not the repo default.** Use
   `gh pr view "$PR_NUM" --repo "$ORIGIN" --json baseRefName --jq '.baseRefName'` so a PR merged into
   a release/maintenance branch cleans up the *right* base. Do **not** rely on
   `git rev-parse origin/HEAD` (unset in fresh worktrees). (Resolves SpecFlow Gap E and the
   fresh-worktree `origin/HEAD` gotcha from
   `docs/solutions/integration-issues/land-plan-docs-gh-git-boundary-gotchas.md`.)

4. **Step 6 becomes a three-leaf decision tree:**
   - **Classic single-tree** (`is_linked_worktree` false, and the feature branch is not checked out
     elsewhere): keep today's `git checkout "$BASE" && git pull --ff-only && git branch -d
     <feature>`. `gh pr merge --delete-branch` already prunes remote + local branch here, so this
     leaf is largely confirmation.
   - **Current worktree** (`is_linked_worktree` true): do **not** `git checkout "$BASE"`. Run
     `git fetch origin` so `origin/<base>` is current, and leave the primary tree to fast-forward on
     its next checkout/worktree-create. Defer worktree + branch teardown (see leaf 3 / gc).
   - **Feature branch checked out in another worktree** (guard before any `git branch -d`): detect
     via `git worktree list --porcelain`; skip the delete and defer to gc, rather than failing with
     `Cannot delete branch '<b>' checked out at '<path>'`. (Resolves SpecFlow Gap H.)

5. **Point teardown at `gc_worktrees` (with the coverage caveat), never hand-rolled deletes.**
   Reference `bash ${CLAUDE_PLUGIN_ROOT}/skills/git-worktree/scripts/worktree-manager.sh gc` as the
   worktree-safe reaper. Document the two hard limits so the agent does not report a false success:
   - gc **skips the worktree it is invoked from** and any worktree with activity in the last
     `WORKTREE_GC_GRACE_MIN` minutes (default 30) — so land-pr **cannot self-reap** the worktree it
     just merged from; teardown is inherently deferred to a later pass or must run from the primary
     tree.
   - gc only reaps worktrees under `$GIT_ROOT/.worktrees/` (`worktree-manager.sh:18`). Harness-created
     worktrees under `.claude/worktrees/` (this very run) are **not** covered — for those, teardown
     is a manual `git worktree remove` from the primary tree. (Resolves SpecFlow Gap A — the biggest
     hole in the issue's original recommendation #3.)

6. **Fork the Success criteria by mode** (SpecFlow Gap C):
   - classic → local default fast-forwarded + feature branch deleted;
   - worktree → remote branch deleted (by `gh`), `origin/<base>` fetched, and any deferred worktree/
     branch teardown **explicitly reported** (which worktree + branch were left for gc / manual
     removal), not silently implied.

7. **Sister skills** `land-docs` and `land-plan-docs` carry the same hazard in **both setup and
   cleanup** (they branch *from* a checked-out default and tear down the same way). Apply the same
   context-aware treatment, reuse the canonical `is_linked_worktree` predicate, and repair
   `land-plan-docs`'s half-converted state (it already resolves BASE via `gh … defaultBranchRef` at
   `land-plan-docs/SKILL.md:122` yet still `git checkout "$BASE"` at `:239`).

## Technical Considerations

- **`allowed-tools`.** land-pr declares `allowed-tools: Bash(gh *), Bash(git *), Read`
  (`land-pr/SKILL.md:5`). Keep the fix to inline `git`/`gh` and *point* readers at `gc` in prose —
  do **not** widen `allowed-tools` to add a `bash worktree-manager.sh` call in the recipe. (Note the
  step already invokes `python3 …/lifecycle_board.py` at `:189`, which is likewise outside the
  declared tools — evidence that the declared list is not treated as strictly authoritative here;
  calling that out is a minor doc-hygiene follow-up, out of scope for this fix.)
- **The classic path must keep working.** The whole change branches on `is_linked_worktree`; the
  single-tree common case is preserved unchanged.
- **Squash-merge detection.** Any merged-branch reasoning must use `git cherry <base> <branch>`
  (catches squash/rebase where SHAs differ), which is exactly what `gc_worktrees` already does — a
  reason to defer to it rather than reimplement `git branch -d`.

## System-Wide Impact

- **Interaction graph.** land-pr's step 6 is invoked directly by users landing a PR and indirectly
  by `/workflows-orchestrate` (which delegates merge/cleanup to land-pr). Fixing land-pr covers the
  orchestrated path. `workflows-work` only *creates* worktrees; it has no post-merge checkout and is
  unaffected.
- **Error propagation.** The core defect is a *false-failure* signal (local housekeeping error
  masquerading as merge failure). Making the merge check state-based stops the wrong-retry loop.
- **State lifecycle risks.** Under worktrees, teardown is legitimately *deferred*, not done. The risk
  is reporting cleanup "done" when a worktree/branch remains — mitigated by the forked, explicit
  Success criteria (item 6).
- **API surface parity.** Three skills expose the same merge→cleanup tail (`land-pr`, `land-docs`,
  `land-plan-docs`). All three need the same change; a shared `is_linked_worktree` snippet keeps
  them from drifting.
- **Integration scenarios worth exercising** (see Validation): merge from a `.worktrees/` worktree;
  merge from a `.claude/worktrees/` worktree (gc does not cover it); merge from the classic single
  tree; merge from the primary tree while the feature branch lives in a linked worktree.

## External System Wiring

No external wiring required. This change edits skill markdown (prose + bash recipes) only — no
third-party config, env vars, webhooks, or auth/middleware changes.

## Acceptance Criteria

- [ ] **land-pr step 5** verifies merge outcome via `gh pr view --json state,mergedAt` and documents
      that `fatal: '<b>' is already used by worktree` after a merge means *local cleanup* failed
      (not the merge) — do not retry the merge; branch on `state == MERGED`.
- [ ] **land-pr step 6** is a context-aware three-leaf decision tree (classic / current-worktree /
      branch-held-elsewhere) built on the canonical `is_linked_worktree` predicate, and never runs
      `git checkout <base>` or `git branch -d` in a context where they fail.
- [ ] Base branch is resolved from the **PR** (`baseRefName`), not the repo default or
      `git rev-parse origin/HEAD`.
- [ ] land-pr **points at `gc_worktrees`** for worktree/branch teardown and documents both coverage
      limits: (a) it cannot self-reap the current/just-active worktree (grace window), and (b) gc
      only reaps `$GIT_ROOT/.worktrees/` — `.claude/worktrees/` needs a manual `git worktree remove`
      from the primary tree.
- [ ] land-pr **Success criteria** are forked by mode; worktree mode reports deferred teardown
      explicitly (names the worktree + branch left behind) rather than claiming local FF + delete
      happened.
- [ ] **Companion note** added to `git-worktree/SKILL.md` cross-referencing that the land-* skills
      defer teardown to `gc`, including the `.worktrees/`-only coverage caveat.
- [ ] **`land-docs` and `land-plan-docs`** get the same worktree-safe treatment in setup **and**
      cleanup, reusing the canonical predicate; `land-plan-docs`'s half-converted BASE handling
      (`:122` vs `:239`) is repaired.
- [ ] `allowed-tools` is unchanged and the recipes stay within `Bash(gh *), Bash(git *)`.
- [ ] The classic single-tree flow is unchanged in behavior.
- [ ] No component-count / README / manifest edits (body-only edits to existing skills).

## Validation

**How a reviewer proves this behaves — not that it renders.** These are runnable git scenarios.

- **Automated:**
  - `bun test` — consistency + converter suites (the CI gate). Confirms no count/slug/frontmatter
    regressions from the edits.
  - `bun run typecheck`.
  - `grep -nE '`(references|assets|scripts)/[^`]+`' plugins/agentic-engineering/skills/land-pr/SKILL.md`
    returns nothing (no bare-backtick reference links introduced).
  - Frontmatter still has `name: land-pr` + a non-empty `description:`.
- **Integration (drive the real flow):** in a scratch clone, reproduce each leaf and confirm the
  documented commands succeed / degrade as written:
  1. **Classic single tree** — open a throwaway PR, run the step-6 recipe → local default FF'd,
     branch deleted.
  2. **`.worktrees/` linked worktree** — create one via `worktree-manager.sh`, land a PR from it →
     merge verified via `state`, `git checkout <base>` is *skipped*, `git fetch origin` succeeds,
     a later `worktree-manager.sh gc` reaps the worktree + branch.
  3. **`.claude/worktrees/` worktree** — land from here → the recipe reports teardown deferred to a
     manual `git worktree remove` from the primary tree (gc does not cover it). Reproduce the
     original error to confirm the state-based check treats it as success:
     `gh pr merge --squash --delete-branch` emits
     `fatal: 'main' is already used by worktree` while `gh pr view --json state` shows `MERGED`.
  4. **Branch held elsewhere** — from the primary tree, attempt teardown of a feature branch checked
     out in a linked worktree → `git branch -d` is guarded/skipped, not failed.
- **Manual:** read each edited SKILL.md end-to-end and confirm the classic path is unchanged and the
  worktree path is unambiguous at every branch point.
- **Rollback:** `git revert` the docs commit — pure markdown, no state to unwind.

## Success Metrics

- An agent following `git-worktree` + `land-pr` together lands a PR from a linked worktree with **no
  false-failure retry** and **no unreachable success criterion**.
- Zero occurrences of the plugin recommending `git checkout <default>` from a context where the
  default is held elsewhere.

## Dependencies & Risks

- **Risk — gc coverage gap (Gap A, confirmed).** `gc_worktrees` reaps only `$GIT_ROOT/.worktrees/`;
  harness worktrees under `.claude/worktrees/` are outside its scope, and gc never self-reaps the
  current worktree. Mitigation: the plan does **not** claim gc is a catch-all — it documents the
  manual `git worktree remove`-from-primary fallback and forks the Success criteria so deferred
  teardown is reported, never silently assumed. (A larger follow-up — extending gc to cover
  `.claude/worktrees/` — is explicitly out of scope and should be a separate issue if desired.)
- **Risk — three-skill drift.** Mitigated by a single canonical `is_linked_worktree` snippet reused
  verbatim.
- **Dependency.** Sub-issues 2 and 3 build on the canonical predicate + pattern established by
  sub-issue 1.

## Sub-Issue Decomposition

1. **land-pr worktree-safe merge-verify + cleanup (core).** Rework `land-pr/SKILL.md` steps 5–6 and
   the Success criteria per items 1–6 above. Establishes the canonical `is_linked_worktree` predicate.
2. **git-worktree companion cross-reference note.** Add a short note to `git-worktree/SKILL.md` that
   land-* skills defer teardown to `gc`, including the `.worktrees/`-only coverage caveat and the
   self-reap grace-window limit. *(blocked by #1)*
3. **Extend worktree-safe pattern to land-docs + land-plan-docs.** Apply the same setup+cleanup fix,
   reuse the canonical predicate, and repair `land-plan-docs`'s half-converted BASE handling
   (`:122` vs `:239`). *(blocked by #1)*

## Sources & References

- **Issue:** [#182](https://github.com/Life-With-Data/agentic-engineering/issues/182) — bug report +
  reproduction evidence + original recommendations.
- **Broken code:** `plugins/agentic-engineering/skills/land-pr/SKILL.md:167` (step 5),
  `:174-181` (step 6), `:211-218` (success criteria).
- **Worktree-safe primitive:** `plugins/agentic-engineering/skills/git-worktree/scripts/worktree-manager.sh:289-366`
  (`gc_worktrees`); `.worktrees/`-only filter at `:18` / `:319`; self-skip at `:320`.
  User-facing gc docs: `git-worktree/SKILL.md:145-179`.
- **Sister-skill hazards:** `land-docs/SKILL.md:170-173`, `land-plan-docs/SKILL.md:122,:239-240`.
- **Prior learning:** `docs/solutions/integration-issues/land-plan-docs-gh-git-boundary-gotchas.md`
  (fresh-worktree `origin/HEAD` unset; resolve base via `gh … defaultBranchRef`/`baseRefName`;
  `allowed-tools` matches by first pipeline token).
- **Convention:** root `CLAUDE.md` (Conventional Commit PR titles — use `fix:`; no hand-bump of
  version/CHANGELOG); `plugins/agentic-engineering/CLAUDE.md` (Skill Compliance Checklist).

