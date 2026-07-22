---
title: "worktree-manager merge detection misses multi-commit squash merges — `git cherry` compares per-commit patch-ids, not the branch's combined diff"
category: integration-issues
tags: [git, worktree, worktree-manager, patch-id, git-cherry, squash-merge, merge-detection, post-merge-cleanup, sync, finish, gc]
module: skills
symptom: "After GitHub squash-merges a PR whose branch had more than one commit, `bun run worktrees:sync` skips that worktree as \"not fully merged into origin/main\" and `bun run worktrees:finish <name>` refuses without `--force` — even though the PR is merged. Single-commit PRs on the same run reap cleanly. Observed live: squash-merging PR #255 (2 commits) reaped 11 single-commit-equivalent worktrees but skipped `legacy-flows-duplicates-cleanup-375de8`."
root_cause: "`branch_merge_tier`'s `patch` tier used `git cherry <base> <branch>`, which compares each branch commit's patch-id individually against the base. A GitHub squash of an N>1-commit branch lands as ONE commit whose patch-id equals the branch's COMBINED diff, matching no individual commit's patch-id — so `git cherry` marks every commit '+' (unmerged). The squash also discards branch history, so `git merge-base --is-ancestor <branch> <base>` is false too. Both the per-commit-patch tier and the ancestor/merge-commit tiers therefore miss it, and detection fell through to `none` (conservative: not merged) — for the single most common GitHub merge strategy on multi-commit PRs."
---

# `worktree-manager` misses multi-commit squash merges

From PR [#258](https://github.com/Life-With-Data/agentic-engineering/pull/258) (issue
[#257](https://github.com/Life-With-Data/agentic-engineering/issues/257)). The gap surfaced on merge
day for PR #255 itself: `worktrees:sync` left one worktree behind with "not fully merged into
origin/main", and `worktrees:finish` demanded `--force`, for a branch that had squash-merged cleanly.

Companion docs: [[land-star-worktree-safe-cleanup-and-recipe-function-scope]] (worktree-safe teardown —
whose §3 line "`gc` uses `git cherry` to catch squash/rebase merges" is exactly the incomplete claim
this fix repairs for the multi-commit case).

## Symptom

A multi-commit PR is squash-merged in the browser. Locally:

```
$ bun run worktrees:sync
(skip) legacy-flows-…-375de8 — not fully merged into origin/main
$ bun run worktrees:finish legacy-flows-…-375de8
Error: branch … is not fully merged into origin/main — merge it first or pass --force to discard
```

Single-commit PRs merged the same way reap immediately. The difference is entirely the branch's
commit count, which is invisible in the "not fully merged" message.

## Investigation

`git cherry origin/main <branch>` on the squash-merged multi-commit branch marks **every** commit `+`:

```
+ b1876da…   # commit 1 of 2 — reported "not in base"
+ 942098c…   # commit 2 of 2 — reported "not in base"
```

The misleading signal: `git cherry` *does* detect single-commit squashes (that one commit's patch-id
survives into the squash), so the `patch` tier looked correct and every existing squash test passed.
The gap is strictly N>1 commits.

## Root cause

`git cherry` / `git patch-id` operate **per commit**. A squash collapses the branch into one commit
whose patch-id equals the branch's *combined* diff — never any individual commit's. And squashing
rewrites history, so the branch tip is not an ancestor of the base either. In `branch_merge_tier`:

- `patch` tier (`git cherry`) — no per-commit match → skipped.
- `merge-commit` / `ancestor-only` tiers — both gated on `--is-ancestor`, which is false → skipped.
- Fell through to `none` → treated as unmerged.

## Solution

Add a fourth evidence tier, `squash`, in the **not-an-ancestor** branch of `branch_merge_tier` (the
only path a squash reaches). Compute the branch's whole-diff patch-id and match it against the base's
recent non-merge commits, bounded to 500, in a single two-process pipe:

```bash
mb=$(git merge-base "$base" "$br")
branch_pid=$(git diff "$mb".."$br" | git patch-id --stable | awk '{print $1}')
# match against base's recent non-merge commits — `git log -p | git patch-id` emits one
# "<patch-id> <commit-id>" line per commit, so this is 2 processes, not 1 per commit:
git log -p --no-merges -n 500 "$base" | git patch-id --stable | grep -q "^$branch_pid "
```

A match is unambiguous merge evidence: `sync` reaps it with zero grace and `finish` accepts it without
`--force`, exactly like the `patch`/`merge-commit` tiers. No match preserves the conservative `none`
fallthrough. The restructure is purely additive — the `is-ancestor`-true path (`merge-commit`,
`ancestor-only`) is byte-for-byte unchanged.

Why it is safe (no data loss): a whole-branch patch-id can only match a base commit when the branch's
combined change already exists in the base — which *is* merge evidence, the same guarantee the
existing `git cherry` tier provides. An adversarial probe confirms a genuinely-unmerged multi-commit
branch stays tier `none` and is kept.

## Reusable principle

**`git cherry` and `git patch-id` compare patch-equivalence PER COMMIT. To detect that a
multi-commit branch landed as one squashed commit, compute the patch-id of the branch's *combined*
diff (`git diff $(git merge-base base br)..br | git patch-id --stable`) and match it against the
base's commits — never rely on per-commit `git cherry` for squash detection when the branch has more
than one commit.** Batch the base scan through a single `git log -p | git patch-id` pipe rather than a
`git show | git patch-id` per commit (two processes vs. ~1000).

## Verification

- `python3 -m unittest discover -s plugins/agentic-engineering/tests -p 'worktree_manager_test.py'`
  — 25 pass; the three multi-commit-squash fixtures (`finish`, `sync`, and the base-advanced variant)
  each **fail on the pre-fix script**, so they guard the regression.
- `bun run skills:check` — the vendored `wf-delivery` copy of `worktree-manager.sh` stays byte-identical.
- Canonical script: [`worktree-manager.sh`](../../../plugins/agentic-engineering/skills/wf-development/scripts/worktree-manager.sh)
  (`branch_merge_tier`).
