---
title: "fix(land-plan-docs): survive pre-commit hooks in an un-bootstrapped worktree"
type: fix
date: 2026-07-20
github_issue: 207
---

# fix(land-plan-docs): survive pre-commit hooks in an un-bootstrapped worktree

## Overview

Issue #207 asks that `/workflows-groom` end with the plan doc committed and pushed as a docs-only
PR, auto-merged when CI is green. **Most of that already shipped** under epic #145: the
[`land-plan-docs`](../../plugins/agentic-engineering/skills/land-plan-docs/SKILL.md) skill commits
the join-keyed `docs/plans/**` paths, opens exactly one docs-only PR with `Refs`-style body (never
`Closes #N`), arms GitHub-native auto-merge at creation, falls back to watch-then-report when
auto-merge is disallowed, and reports one status line; `/workflows-groom`'s Completion section owns
invoking it and surfaces the result on the packet's `Plan PR:` line.

One item from #207 remains genuinely unhandled: **the commit itself can be impossible in a fresh
worktree.** The reporter hit this on `Life-With-Data/agent-leverage` — a harness-created worktree
has no `node_modules`, so every repo pre-commit hook (biome / tsc / markdownlint / tsx) fails with
"command not found", and `--no-verify` is correctly blocked by `block-no-verify.py`. The grooming
run stalls at the commit step and the human has to install dependencies by hand — the exact manual
toil #207 exists to remove.

This plan closes that residual gap only.

## Problem Statement / Motivation

`land-plan-docs` Step 5 runs a plain `git commit`. In the environment it is *designed* to run in —
a linked worktree created by the grooming harness — repo pre-commit hooks routinely fail for a
reason that has nothing to do with the change being landed:

- The change is markdown under `docs/plans/**`; the failing hooks are toolchain hooks.
- The failure mode is `command not found`, not a lint violation, so there is nothing to "fix
  mechanically" in the sense of the skill's decision tree.
- The two sanctioned escapes are both closed: `--no-verify` is blocked by policy
  (`plugins/agentic-engineering/scripts/block-no-verify.py`) and pushing to the default branch is
  forbidden.

The repo already owns the missing primitive:
`plugins/agentic-engineering/scripts/worktree-session.py:148` runs an opt-in
`$AGENTIC_WORKTREE_BOOTSTRAP_CMD` once per worktree (marker-guarded) and, when the variable is
unset, emits exactly the advisory this session started with — *"Fresh worktree: dependencies are
not installed."* `land-plan-docs` neither consults that signal nor recovers from it.

## Proposed Solution

Teach `land-plan-docs` a bounded **bootstrap-and-retry** recovery for a hook failure caused by a
missing toolchain, sitting between "commit" and "escalate":

1. On a failed `git commit`, classify the failure. A *toolchain* failure (`command not found`,
   `ENOENT`, a missing binary/module named by a hook) is distinct from a *content* failure (a lint
   or link error in the markdown being landed).
2. **Toolchain failure** → if `$AGENTIC_WORKTREE_BOOTSTRAP_CMD` is set, run it once (it is
   marker-guarded and idempotent), then retry the commit exactly once. If the variable is unset, or
   the bootstrap fails, or the retry still fails on the toolchain, **stop and report**
   `skipped: worktree not bootstrapped — set AGENTIC_WORKTREE_BOOTSTRAP_CMD or install deps` — a
   degraded packet line, never a silent skip and never `--no-verify`.
3. **Content failure** → unchanged: the existing mechanical-fix path (~2 bounded attempts) applies.

The recovery is bounded to a single bootstrap attempt and a single commit retry, matching the
skill's existing "~2 attempts that make measurable progress" discipline. Because the whole land
step is already best-effort for groom, every failure branch degrades the `Plan PR:` line rather
than aborting the groomed packet.

Alongside the fix, record in the parent issue and the skill that #207's other three asks (open a
docs-only PR, merge on green, surface the PR in the packet) are already satisfied — so the issue
closes against reality rather than being re-litigated.

## Scope

- **In scope:** a bootstrap-and-retry recovery step in `land-plan-docs/SKILL.md`; its status-line
  vocabulary; a guardrail test asserting the recovery contract and the never-`--no-verify`
  invariant; a short note reconciling #207 with what #145 already shipped.
- **Out of scope:** wiring `land-plan-docs` into `/workflows-plan` and `/deepen-plan` (already
  tracked as #149 and #150); changing `block-no-verify.py`; changing `worktree-session.py`'s
  bootstrap mechanism; any change to lifecycle stages or the groom hard-stop contract.

## System-Wide Impact

- **Interaction graph:** `/workflows-groom` Completion → Task(sub-agent) → `land-plan-docs` →
  `git commit` → repo pre-commit hooks → (new) `$AGENTIC_WORKTREE_BOOTSTRAP_CMD` → retry →
  `gh pr create` → `gh pr merge --auto`. The `block-no-verify.py` PreToolUse hook remains the
  backstop on the commit command itself.
- **Error propagation:** the new branch terminates in a `skipped:`/`needs approval` status line
  that groom already knows how to render; no new error class escapes to the caller.
- **State lifecycle risks:** none — the recovery runs before any branch is pushed or PR opened, so
  a failure leaves at most a local branch, which the existing idempotency check tolerates on re-run.
- **API surface parity:** [`land-docs`](../../plugins/agentic-engineering/skills/land-docs/SKILL.md)
  commits under the same conditions and has the same latent exposure. Fix `land-plan-docs` here;
  note the parallel explicitly so the sibling skill can follow if the failure is observed there.

## External System Wiring

No external wiring required. The change is markdown guidance plus a test; GitHub auto-merge is
already in use and unchanged.

## Task Breakdown (Sub-Issues)

- [ ] Task 1 — Add the bootstrap-and-retry recovery + status vocabulary to `land-plan-docs`.
- [ ] Task 2 — Guardrail test for the recovery contract and the never-`--no-verify` invariant
      (blocked by Task 1).

## Acceptance Criteria

- [ ] `land-plan-docs/SKILL.md` documents how to classify a failed commit as *toolchain* vs
      *content*, and gives the bootstrap-and-retry recipe for the toolchain case.
- [ ] The recovery is explicitly bounded: at most one bootstrap run and one commit retry.
- [ ] A missing/failed bootstrap produces a named `skipped: …` status line naming
      `AGENTIC_WORKTREE_BOOTSTRAP_CMD` as the fix — never a silent skip, never `--no-verify`.
- [ ] The skill's success criteria and status-line list include the new outcome.
- [ ] A test in `tests/` fails if the recovery guidance or the never-`--no-verify` invariant is
      removed from the skill, asserted **by category** (see
      [guardrail tests assert category, not literal](#sources--references)) rather than by a frozen
      sentence.
- [ ] The parent issue records that #207's PR / merge-on-green / packet-line asks were already
      delivered by #145, so its closure is auditable.
- [ ] `bun test` and `bun run docs:check` pass.

## Validation

```bash
bun test tests/land-plan-docs-bootstrap.test.ts   # the new guardrail test
bun test                                          # full gate CI runs
bun run docs:check                                # generated docs still in sync
```

- **Automated:** the new guardrail test, plus the existing `plugin-consistency` and
  `docs-generated` suites.
- **Manual:** in a fresh `.claude/worktrees/**` checkout with no `node_modules` and
  `AGENTIC_WORKTREE_BOOTSTRAP_CMD` unset, run `/workflows-groom` on a small item and confirm the
  groomed packet still emits with `Plan PR: skipped: worktree not bootstrapped — …`. Then export
  `AGENTIC_WORKTREE_BOOTSTRAP_CMD="bun install"`, re-run, and confirm the commit succeeds and the
  PR opens with auto-merge armed.
- **Rollback:** revert the docs + test commit. The change is guidance and a test; no runtime code
  path depends on it.

## Dependencies & Risks

- **No blocking work.** #149 / #150 (wiring into `/workflows-plan` and `/deepen-plan`) are
  independent and may land in any order.
- **Risk — over-broad classification.** Treating a genuine content failure as "toolchain" would
  run a pointless bootstrap and burn an attempt. Mitigation: classify on the failing hook's own
  output (missing-binary/module signatures only), and keep the retry budget at one.
- **Risk — bootstrap side effects.** `$AGENTIC_WORKTREE_BOOTSTRAP_CMD` is user-supplied and may
  write lockfiles. Mitigation: the scope check already stages only the join-keyed
  `docs/plans/**` paths, so any bootstrap-generated file is left unstaged; state this explicitly.
- **Risk — the ask is read as "re-do #145".** Mitigation: the Overview above and the parent-issue
  note make the delta explicit.

## Sources & References

- **Plan doc:** `docs/plans/2026-07-20-fix-land-plan-docs-unbootstrapped-worktree-plan.md`
- Skill under change: `plugins/agentic-engineering/skills/land-plan-docs/SKILL.md`
- Caller: `plugins/agentic-engineering/skills/workflows-groom/SKILL.md` (Completion section)
- Bootstrap primitive: `plugins/agentic-engineering/scripts/worktree-session.py:148`
- Policy backstop: `plugins/agentic-engineering/scripts/block-no-verify.py`
- Already-shipped predecessors: #145 (epic), #147 (create skill), #148 (wire into groom),
  #185 (worktree-safe cleanup)
- Related open work: #149, #150, #151
- Convention: guardrail tests assert a surface **by category**, not by a frozen literal string —
  a literal spelling silently false-passes once the wording drifts.
