---
name: land-pr
description: Drive an open PR through its review cycle to completion and merge it. Use after a PR is opened to wait on CI, resolve review threads and findings, confirm it has been independently reviewed and is mergeable, then merge and clean up. Triggers on "land this PR", "get this PR merged", "merge when green", "take this PR to completion".
argument-hint: "[optional: PR number — defaults to the current branch's PR] [--auto]"
allowed-tools: Bash(gh *), Bash(git *), Read
---

# Land a PR

Take an **already-open** PR from "review in progress" to **merged**: wait for CI to go green,
resolve every review thread and review finding, confirm it has been independently reviewed and is
mergeable, then
merge it and clean up. This is the completion-and-merge tail that picks up where `/workflows-work`
Phase 4 (PR creation) and `/workflows-review` (findings) leave off.

This skill does **not** write the feature or open the PR — point it at a PR that already exists.

## When to use

- After `/workflows-work` opens a PR and `/workflows-review` has produced findings — to drive the
  PR the rest of the way to merged.
- Any time a PR needs to be shepherded to completion: CI red, unresolved review threads, waiting on
  approval, or simply "merge it once it's green."

For the comment-resolution step this skill delegates to the [`resolve-pr-parallel`](../resolve-pr-parallel/SKILL.md)
skill rather than reimplementing it.

**Code PR vs. knowledge PR.** This skill lands the **code** PR through the full independent-review
gate. The **compound** step that follows a merge produces docs-only markdown, which ships as its own
separate PR through the [`land-docs`](../land-docs/SKILL.md) skill — a lighter lane with no in-agent
review (GitHub Actions own review there; the agent only follows the checks and merges on green). When
you finish landing a code PR and the pipeline moves to compound, that docs PR is `land-docs`'s job,
not this skill's.

## The merge gate (read first)

Merging is outward-facing and effectively irreversible. Called on its own, land-pr **pauses and asks
the user before merging**. Merge automatically **only** when invoked in an autonomous context —
`--auto` in the arguments, or when called from `/workflows-orchestrate` in an autonomous run (its
fully-autonomous default, or after its `--final-review` gate has been approved) — **and** all
landability conditions below hold. Never auto-merge a PR that touches the default branch directly,
force-pushes, or has any unresolved blocker.

**What counts as "the review" for an autonomous merge.** In a solo or autonomous run there is usually
no human reviewer, so GitHub's `reviewDecision` stays empty or `REVIEW_REQUIRED` and never reaches
`APPROVED`. Do **not** wait for a human GitHub approval — that would stall every autonomous merge.
The review gate is instead the pipeline's **own independent review**: an `/workflows-review` pass
(delegated to fresh reviewer sub-agents, not the implementer) ran this cycle and all P1/blocking
findings are resolved. A human approval only matters when **branch protection physically requires
it** — which shows up as `mergeStateStatus: BLOCKED`, a genuine blocker the agent cannot self-satisfy
(escalate; don't loop).

## Landability conditions

A PR is **landable** when all of these are true:

1. **CI green** — every required check has concluded successfully (no `FAILURE`, `PENDING`, or
   `IN_PROGRESS` required checks).
2. **Threads resolved** — `get-pr-comments` returns `[]` (no unresolved, non-outdated review threads).
3. **Independently reviewed** — an `/workflows-review` pass ran this cycle and its P1/blocking findings
   are resolved. This is a **hard, non-skippable gate in every mode.** When landing inside the
   orchestrate pipeline it already happened upstream; when landing a PR standalone, land-pr itself
   confirms a review ran this cycle and, if it cannot, **runs `/workflows-review` before merging** and
   resolves any P1s — a merge never happens on an unreviewed PR. No reviewer has an open
   `CHANGES_REQUESTED`.
4. **Mergeable** — `mergeStateStatus` is not `DIRTY` (conflicts), `BLOCKED` (branch protection), or
   `BEHIND` (needs update) for a reason you haven't cleared. A human GitHub `APPROVED` is **not**
   required unless branch protection enforces it.

The `pr-landable-status` script computes 1, 2, and 4 mechanically and lists any `blockers`; condition
3 (the independent review having run) is verified here before any merge — never assumed from the
script alone, and never skipped because the run looks autonomous. If it cannot be confirmed, run
`/workflows-review` and resolve its P1s first.

## Workflow

### 1. Identify the PR

```bash
# Default to the current branch's PR; or pass a number as the first argument.
PR_NUM=${PR_NUM:-$(gh pr view --json number --jq '.number')}
ORIGIN=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')   # owner/repo of origin — every gh write carries it (fork-trap)
```

Confirm it is open. If `gh pr view` reports the PR is already `MERGED` or `CLOSED`, stop and report —
there is nothing to land.

### 2. Assess landability

Print the current gating signals in one shot:

```bash
bash ${CLAUDE_PLUGIN_ROOT}/skills/land-pr/scripts/pr-landable-status "$PR_NUM"
```

This emits JSON with `ci`, `review_decision`, `merge_state`, `unresolved_threads`, a `blockers` list,
and a `landable` boolean. Read it and decide which conditions are unmet. (Remember `landable` covers
the mechanical conditions only — also confirm the independent review ran, per condition 3.)

### 3. Drive to green (loop until landable)

Repeat until all landability conditions hold, or a blocker resists ~2 attempts that make **no
strictly-measurable progress** — a fix that does not reduce the failing-check count, the unresolved-
thread count, or the open-P1 count counts as a dry attempt (the uniform no-progress rule in
`/workflows-orchestrate`). After two dry attempts, stop and escalate to the user with the specific
failure from `blockers`:

- **CI red or a required check failing** → inspect the failure, fix it, push, and re-check:
  ```bash
  gh pr checks "$PR_NUM"                       # which checks failed
  gh run view <run-id> --log-failed            # failing job logs
  # fix the code, commit, push
  git push
  ```
  A flaky check that is genuinely unrelated may be re-run (`gh run rerun <run-id> --failed`) — but
  only after confirming it is flaky, not a real failure your change introduced.

- **CI still running** → wait for it rather than polling tightly:
  ```bash
  gh pr checks "$PR_NUM" --watch
  ```

- **Unresolved review threads** → run the [`resolve-pr-parallel`](../resolve-pr-parallel/SKILL.md)
  skill for this PR (it resolves every thread in parallel, commits, pushes, and re-verifies empty),
  then return here.

- **Independent review not yet run** → if no `/workflows-review` pass has reviewed this PR this cycle,
  run it now (it delegates to fresh reviewer sub-agents) and resolve any P1/blocking findings before
  merging. Inside the orchestrate pipeline this already happened upstream — don't re-run it.

- **Changes requested** (`reviewDecision: CHANGES_REQUESTED`) → resolve the reviewer's threads (above);
  the decision clears once they're addressed. Do **not** wait for a human `APPROVED` in autonomous mode
  — the independent review pass is the gate, not a human approval.

- **Merge blocked by branch protection** (`mergeStateStatus: BLOCKED`) → the repo physically requires
  something the agent can't supply (e.g. a human approval, a CODEOWNERS sign-off, an external check).
  This is a genuine blocker: stop and surface it to the user with the specific reason. Do not loop on
  it and do not attempt an admin override unless the user explicitly authorizes one.

- **Branch behind base** (`mergeStateStatus: BEHIND`) → update it:
  ```bash
  gh pr update-branch "$PR_NUM" || git fetch origin && git rebase origin/<base> && git push --force-with-lease
  ```

After each fix, re-run `pr-landable-status` (step 2). Do not proceed while any required check is
`PENDING`/`IN_PROGRESS` — a green merge requires concluded checks.

### 4. Merge gate

Re-confirm all landability conditions hold (CI green, threads resolved, independent review ran with
P1s clear, mergeable), then decide how to merge:

- **Default (interactive)** — stop and ask the user before merging. Present the PR number, the merge
  method, and that the branch will be deleted. Example: *"PR #123 is green, independently reviewed
  (P1s resolved), and all threads resolved. Merge with squash and delete the branch? [y/N]"* Merge
  only on explicit yes.

- **Autonomous (`--auto`, or called from `/workflows-orchestrate` in an autonomous run)** — merge
  without asking **once and only once** all conditions hold. This is the point of autonomous mode: do not bounce a
  "say the word and I'll merge" back to the user when the PR is already green, reviewed, and
  mergeable — just merge. If a condition is genuinely unmet (CI stuck red after retries,
  `CHANGES_REQUESTED` unresolved, or `mergeStateStatus: BLOCKED` by branch protection), do not merge;
  escalate that specific gap as a blocker.

### 5. Merge

```bash
gh pr merge "$PR_NUM" --repo "$ORIGIN" --squash --delete-branch
```

Use `--squash` by default (clean, single-commit history). Honor a different method if the repo
convention or the user calls for `--merge` or `--rebase`. If required checks are configured but you
want GitHub to merge the instant they pass, `--auto --squash` enables auto-merge instead of blocking.

**Verify the merge from server state, never from the exit code.** When land-pr runs from a linked
worktree, `--delete-branch`'s *local* housekeeping can fail with
`fatal: '<base>' is already used by worktree at '<primary-path>'` **even though the PR merged and the
remote branch was deleted server-side**. That error reads like the merge failed and invites a wrong
retry. So after any non-clean return, confirm the outcome from GitHub — do **not** parse stderr or the
exit code (the message is locale- and version-dependent):

```bash
gh pr view "$PR_NUM" --repo "$ORIGIN" --json state,mergedAt --jq '.state'
```

If `state == MERGED`, the merge **succeeded** — the failure was local cleanup only. Do **not** re-run
`gh pr merge`; proceed to step 6, which performs the worktree-safe teardown. Only a `state` other than
`MERGED` means the merge itself did not happen and may be retried.

### 6. Post-merge cleanup (context-aware)

Cleanup **branches on worktree context**. The classic single-tree path is unchanged; a linked
worktree cannot check out a base branch that the primary tree already holds, so it takes a deferred
path instead. Resolve two facts first — the PR's **base branch** (from the PR, not the repo default: a
PR merged into a release/maintenance branch must clean up *that* base, and `git rev-parse origin/HEAD`
is often unset in a fresh worktree) and whether this is a **linked worktree**:

```bash
BASE=$(gh pr view "$PR_NUM" --repo "$ORIGIN" --json baseRefName --jq '.baseRefName')

# true (linked worktree) when the per-worktree git-dir differs from the shared common-dir.
# Absolute path-format avoids relative-vs-absolute false matches across git versions.
is_linked_worktree() {
  [ "$(git rev-parse --path-format=absolute --git-common-dir)" \
    != "$(git rev-parse --path-format=absolute --git-dir)" ]
}
```

Then take exactly one leaf:

**Leaf A — classic single tree** (`is_linked_worktree` false). Today's path, unchanged.
`gh pr merge --delete-branch` already pruned the remote and local branch, so this is mostly
confirmation:

```bash
git checkout "$BASE"
git pull --ff-only
git branch -d <feature-branch>   # safe-delete; already merged (no-op if gh already pruned it)
```

**Leaf B — current linked worktree** (`is_linked_worktree` true). Do **not** `git checkout "$BASE"` —
the base is checked out in the primary tree and the checkout would fail. Just refresh the
remote-tracking ref so the primary tree fast-forwards on its next checkout; defer worktree + branch
teardown to gc (below):

```bash
git fetch origin "$BASE"    # origin/<base> now current; primary tree FFs on its next checkout
```

**Leaf C — feature branch checked out in another worktree** (guard before any `git branch -d`, in
either tree). Deleting a branch that is live in another worktree fails with
`Cannot delete branch '<b>' checked out at '<path>'`; detect it and skip the delete, deferring to gc:

```bash
git worktree list --porcelain | grep -qF "branch refs/heads/<feature-branch>" \
  && echo "branch held in another worktree — skip delete, defer to gc" \
  || git branch -d <feature-branch>
```

**Teardown of a linked worktree + its orphaned branch is deferred to `gc_worktrees`**, the
worktree-safe reaper (it uses `git cherry` to catch squash/rebase merges, removes the worktree from
*outside* it, and deletes the orphaned local branch). Point at it in prose — do not add it to the
recipe or widen `allowed-tools`:

```
bash ${CLAUDE_PLUGIN_ROOT}/skills/git-worktree/scripts/worktree-manager.sh gc
```

Two coverage limits make this teardown **inherently deferred** — land-pr must not report it done:
- gc **skips the worktree it runs from** and any worktree active within `WORKTREE_GC_GRACE_MIN`
  (default 30 minutes) — so land-pr **cannot self-reap** the worktree it just merged from. That
  worktree is reaped by a later gc pass, or by running gc from the primary tree.
- gc only reaps worktrees under `$GIT_ROOT/.worktrees/`. A worktree under `.claude/worktrees/`
  (harness-created — including this pipeline's own runs) is **not** covered; for those, teardown is a
  manual `git worktree remove <path>` from the primary tree.

**Verify the lifecycle stamp.** The merge closes the issue via `Closes #N` in the PR body;
GitHub's built-in "Item closed" board automation then stamps the tracked item `shipped` —
this step confirms that stamp landed, it does not perform the close itself. `<N>` is the
issue number the PR closes (from the PR body's `Closes #N`, or the plan doc's `github_issue:`):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lifecycle_board.py" --reconcile --issue <N>
```

This invokes the **shared reconciler** — the only writer besides the transition owners — which
repairs a missed stamp (e.g. the automation was disabled or lagged) by setting Status to `shipped`
and posting a one-line audit comment. Never hand-roll a second reconcile check here; this is the
one implementation every command uses.

- **`github-project` / `github`-adjacent repos** — the command above is sufficient.
- **plain `github` mode (legacy, no board)** — `gh issue close <n> --repo <origin> --comment "merged PR #${PR_NUM}"` if still open.
- **`none` / file-todos** — ensure the plan's checkboxes are all checked; there is no frontmatter
  status field to update (the `status:` key no longer exists on plan docs).

### 7. Report

Summarize: the merged PR (number + URL), the merge method, and the tracker state. Report cleanup **by
mode** — classic single tree: feature branch deleted and local base synced; **linked worktree: name
the worktree + feature branch left for gc or a manual `git worktree remove` from the primary tree**
(teardown is deferred, not done — never claim a local fast-forward + delete that did not happen). Note
any follow-on work discovered while landing.

## Scripts

- [scripts/pr-landable-status](scripts/pr-landable-status) — print CI, review-decision, merge-state, and unresolved-thread count as JSON

## Success criteria

- PR shows `MERGED` (confirmed from `gh pr view --json state`, not from the merge command's exit code).
- Lifecycle stamp verified (reconciler) / legacy close done.
- **Cleanup, by mode:**
  - **Classic single tree** — remote **and** local feature branch deleted; local base branch
    fast-forwarded.
  - **Linked worktree** — remote branch deleted (by `gh`) and `origin/<base>` fetched; local base
    fast-forward and worktree/branch teardown are **deferred**, and the report **names the worktree +
    branch left behind** for gc or a manual `git worktree remove` — never claiming a local FF + delete
    that did not happen.
- In autonomous mode, the merge happened only because CI was green, an independent `/workflows-review`
  pass had run with P1s resolved, threads were resolved, and the PR was mergeable — never on an unmet
  condition, and never blocked waiting on a human GitHub approval the run was never going to receive.
