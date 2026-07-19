---
title: "Making land-* skills worktree-safe — plus the shell-function-scope trap that hides inside prompt-recipe bash blocks"
category: integration-issues
tags: [skills, git, worktree, gh-cli, allowed-tools, bash-recipes, land-pr, land-docs, land-plan-docs, unattended, post-merge-cleanup]
module: skills
symptom: "The plugin's own worktree-first workflow contradicted its land-* skills: from a linked worktree, land-pr step 5's `gh pr merge --delete-branch` prints `fatal: 'main' is already used by worktree` (while the PR is actually MERGED) and step 6's `git checkout <default>` is unreachable because the default branch is held by the primary tree. A first fix then introduced a subtler bug — a green-path cleanup that called a shell function defined in a *different* fenced code block, so it failed with exit 127 and silently took the wrong branch."
root_cause: "Two independent boundary assumptions. (1) The land-* cleanup recipes assumed the default branch can be checked out in the current working tree; in a linked worktree it is held by the primary tree, so `git checkout <default>` fails and `gh pr merge --delete-branch`'s *local* housekeeping fails after a successful server-side merge. (2) A prompt-recipe fix used `if is_linked_worktree; then …` where `is_linked_worktree` was defined in an earlier fenced block — but each fenced bash block runs as its own shell invocation, so a function does not survive across blocks (exit 127 → condition false → wrong `else` branch), and a leading `if` also escapes the skill's first-token `allowed-tools` allow-list."
---

# Making `land-*` skills worktree-safe — and the recipe-function-scope trap

From PR [#206](https://github.com/Life-With-Data/agentic-engineering/pull/206) (issue #182). The plugin
actively promotes a **worktree-first** workflow (the [`git-worktree`](../../../plugins/agentic-engineering/skills/git-worktree/SKILL.md)
skill + worktree bootstrap/GC hooks), yet its [`land-pr`](../../../plugins/agentic-engineering/skills/land-pr/SKILL.md)
/ [`land-docs`](../../../plugins/agentic-engineering/skills/land-docs/SKILL.md) /
[`land-plan-docs`](../../../plugins/agentic-engineering/skills/land-plan-docs/SKILL.md) skills assumed a
single working tree. From a linked worktree the two recommended skills contradicted each other on
**every merge**. Fixing that surfaced a second, sneakier bug in the fix itself — caught only by the
independent `/workflows-review` pass, not by `bun test` (these are prompt files, not executed code).

Companion docs: [[land-plan-docs-gh-git-boundary-gotchas]] (the `head:`/`origin/HEAD`/`allowed-tools`
trio), [[skills-mutating-user-repos-git-gotchas]].

## 1. A linked worktree cannot check out the default branch — treat the merge as server-state, not exit code

**Trap.** `land-pr` step 5 merged and step 6 cleaned up with:

```bash
gh pr merge "$PR_NUM" --squash --delete-branch
git checkout <default-branch> && git pull --ff-only && git branch -d <feature-branch>
```

In a linked worktree the default branch is checked out in the **primary** tree. So:
- `gh pr merge --delete-branch` **succeeds server-side** (PR merged, remote branch deleted) but its
  *local* housekeeping fails with `fatal: '<default>' is already used by worktree at '<primary-path>'`.
  The error reads like the merge failed and invites a wrong retry.
- `git checkout <default-branch>` fails for the same reason — a branch live in another worktree cannot
  be checked out — so the documented "success criteria" (local default fast-forwarded, feature branch
  deleted) are **unreachable** via the documented commands.

**Fix — branch cleanup on worktree context, and verify the merge from GitHub, never from the exit code:**

```bash
# Verify the merge outcome from the server; the stderr string is locale/version-fragile.
gh pr view "$PR_NUM" --repo "$ORIGIN" --json state,mergedAt --jq '.state'   # == MERGED → merge is done

# Detect a linked worktree: per-worktree git-dir differs from the shared common-dir.
# Absolute path-format avoids relative-vs-absolute false matches across git versions.
is_linked_worktree() {
  [ "$(git rev-parse --path-format=absolute --git-common-dir)" \
    != "$(git rev-parse --path-format=absolute --git-dir)" ]
}
```

If `state == MERGED`, the merge succeeded and the `fatal: … already used by worktree` message was
*local cleanup only* — do not retry the merge. Then pick a cleanup path:

- **Classic single tree** → today's `git checkout "$BASE" && git pull --ff-only && git branch -d …`.
- **Linked worktree** → **do not** `git checkout "$BASE"`; run `git fetch origin "$BASE"` so the primary
  tree fast-forwards on its next checkout, and **defer** worktree/branch teardown (see §3).

Resolve `$BASE` from the **PR** (`gh pr view … --json baseRefName --jq '.baseRefName'`), not the repo
default and not `git rev-parse origin/HEAD` (unset in fresh worktrees — see [[land-plan-docs-gh-git-boundary-gotchas]] §2).

## 2. A shell function defined in one fenced block does NOT survive into another — the trap that hid inside the fix

**Trap (the subtle one).** The first cut at the sister skills wrote the green-path cleanup as:

```bash
# ... in a SEPARATE fenced block, far from where is_linked_worktree() was defined ...
if is_linked_worktree; then
  git fetch origin "$BASE"
else
  git checkout "$BASE" && git pull --ff-only
  git branch -D "$BRANCH" 2>/dev/null || true
fi
```

`is_linked_worktree()` was defined in the skill's **step-1** fenced block. This cleanup is a **different**
fenced block — and an agent runs each ```bash block as its own shell invocation. **Bash functions do not
persist across invocations.** So at runtime `is_linked_worktree` is `command not found` (exit 127) → the
`if` condition is false → the recipe takes the **`else` branch's `git checkout "$BASE"`**, which is
exactly the command that **fails in a linked worktree** — reintroducing the very bug §1 removed, in the
skill whose whole job is the worktree case.

Compounding it, the block's **first token is `if`** (its condition invokes a non-builtin), so it also
trips the `allowed-tools` first-token rule ([[land-plan-docs-gh-git-boundary-gotchas]] §3): under
`allowed-tools: Bash(gh *), Bash(git *), Read`, a leading `if` is not covered and an **unattended
auto-merge lane stalls on a permission prompt.** `land-docs`/`land-plan-docs` are precisely those lanes.

**Fix — never call a recipe-local function across blocks; make the predicate an agent decision, and keep
every executable block self-contained and git/gh-led:**

```markdown
Pick the path by evaluating `is_linked_worktree` — a linked worktree cannot check out `$BASE`:

**Classic single tree:**
​```bash
git checkout "$BASE" && git pull --ff-only
git branch -D "$BRANCH" 2>/dev/null || true
​```

**Linked worktree** — do not check out `$BASE`:
​```bash
git fetch origin "$BASE"
​```
```

`land-pr` was authored this way from the start (predicate defined for the agent to *read*, each leaf a
separate `git`-led block; the snippets never call the function), which is why the bug lived only in the
sister skills that deviated. **The meta-lesson: in a skill, a bash function is documentation the agent
reads to choose a branch — it is not a callable that survives from one code block to the next.**

## 3. Teardown under worktrees is *deferred*, not done — and `gc` does not cover every worktree

Local worktree + branch teardown is handed to the worktree-safe reaper
`git-worktree/scripts/worktree-manager.sh gc` (it uses `git cherry` to catch squash/rebase merges,
removes the worktree from *outside* it, and deletes the orphaned branch). Two coverage limits mean the
land-* skills must **report teardown as deferred, never claim it done**:

- **`gc` cannot self-reap the active worktree.** It skips the worktree it runs from and any worktree
  active within `WORKTREE_GC_GRACE_MIN` (default 30m) — so a skill landing *from* a worktree can never
  reap that same worktree in the same pass.
- **`gc` only reaps `$GIT_ROOT/.worktrees/`.** A worktree under `.claude/worktrees/` (harness-created —
  e.g. the pipeline's own runs) is out of scope and needs a manual `git worktree remove <path>` from the
  primary tree. (This very PR merged from a `.claude/worktrees/` worktree, so its own teardown was
  manual — a live confirmation of the caveat.)

Keep the `allowed-tools` allow-list untouched: **reference `gc` in prose**, do not put a
`bash worktree-manager.sh` call in the recipe (it would need a wider allow-list).

## Prevention

- **Read gh/git recipe snippets as if hostile, and budget review on the *deltas*.** When a skill is
  authored by mirroring a working sibling, the copied scaffolding is proven; the changed behaviors are
  where boundary semantics bite. Both bugs here lived in the deltas from `land-pr`'s pattern.
- **One fenced block = one shell.** Never define a function in one block and call it in another. Either
  inline the test, or (better for skills) make the predicate a decision the agent evaluates in prose and
  keep each executable block self-contained.
- **Every executable block must be runnable under the skill's own `allowed-tools`.** First token must be
  `git`/`gh` (or another allow-listed command). A leading `if`, `comm`, `sed`, or a bare function name is
  not covered and stalls unattended runs.
- **Verify irreversible outcomes from authoritative state, not from a command's exit code or stderr**
  (`gh pr view --json state`), because local housekeeping can fail *after* the server-side action
  succeeded.
- **`bun test` cannot catch any of this.** It validates counts and frontmatter, not the runtime behavior
  of illustrative bash. The **independent `/workflows-review` pass is the gate that does** — keep it
  non-skippable for skill changes. Here it caught a P1 the implementer's own in-session pre-check missed.

## Resources

- PR [#206](https://github.com/Life-With-Data/agentic-engineering/pull/206) · issue #182 (sub-issues #183/#184/#185)
- Fixed skills: [`land-pr`](../../../plugins/agentic-engineering/skills/land-pr/SKILL.md) (step 5–6 +
  success criteria), [`land-docs`](../../../plugins/agentic-engineering/skills/land-docs/SKILL.md),
  [`land-plan-docs`](../../../plugins/agentic-engineering/skills/land-plan-docs/SKILL.md);
  companion note in [`git-worktree`](../../../plugins/agentic-engineering/skills/git-worktree/SKILL.md)
- Worktree-safe reaper: `plugins/agentic-engineering/skills/git-worktree/scripts/worktree-manager.sh`
  (`gc_worktrees`; `.worktrees/`-only filter; self-skip; grace window)
- Companion learnings: [[land-plan-docs-gh-git-boundary-gotchas]], [[skills-mutating-user-repos-git-gotchas]]
