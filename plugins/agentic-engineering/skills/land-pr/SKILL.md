---
name: land-pr
description: Drive an open PR through its review cycle to completion and merge it. Use after a PR is opened to wait on CI, resolve review threads and findings, confirm it has been independently reviewed and is mergeable, then merge and clean up. Triggers on "land this PR", "get this PR merged", "merge when green", "take this PR to completion".
argument-hint: "[optional: PR number — defaults to the current branch's PR] [--auto]"
disable-model-invocation: true
allowed-tools: Bash(gh *), Bash(git *), Read
---

# Land a PR

Take an **already-open** PR from "review in progress" to **merged**: wait for CI to go green,
resolve every review thread and review finding, confirm it has been independently reviewed and is
mergeable, then
merge it and clean up. This is the completion-and-merge tail that picks up where `/workflows:work`
Phase 4 (PR creation) and `/workflows:review` (findings) leave off.

This skill does **not** write the feature or open the PR — point it at a PR that already exists.

## When to use

- After `/workflows:work` opens a PR and `/workflows:review` has produced findings — to drive the
  PR the rest of the way to merged.
- Any time a PR needs to be shepherded to completion: CI red, unresolved review threads, waiting on
  approval, or simply "merge it once it's green."

For the comment-resolution step this skill delegates to the [`resolve-pr-parallel`](../resolve-pr-parallel/SKILL.md)
skill rather than reimplementing it.

## The merge gate (read first)

Merging is outward-facing and effectively irreversible. The default is to **pause and ask the user
before merging**. Merge automatically **only** when invoked in an autonomous context — `--auto` in
the arguments, or when called from `/lfg`, `/slfg`, or `/workflows:orchestrate --auto` — **and** all
landability conditions below hold. Never auto-merge a PR that touches the default branch directly,
force-pushes, or has any unresolved blocker.

**What counts as "the review" for an autonomous merge.** In a solo or autonomous run there is usually
no human reviewer, so GitHub's `reviewDecision` stays empty or `REVIEW_REQUIRED` and never reaches
`APPROVED`. Do **not** wait for a human GitHub approval — that would stall every autonomous merge.
The review gate is instead the pipeline's **own independent review**: an `/workflows:review` pass
(delegated to fresh reviewer sub-agents, not the implementer) ran this cycle and all P1/blocking
findings are resolved. A human approval only matters when **branch protection physically requires
it** — which shows up as `mergeStateStatus: BLOCKED`, a genuine blocker the agent cannot self-satisfy
(escalate; don't loop).

## Landability conditions

A PR is **landable** when all of these are true:

1. **CI green** — every required check has concluded successfully (no `FAILURE`, `PENDING`, or
   `IN_PROGRESS` required checks).
2. **Threads resolved** — `get-pr-comments` returns `[]` (no unresolved, non-outdated review threads).
3. **Independently reviewed** — an `/workflows:review` pass ran this cycle and its P1/blocking findings
   are resolved (when landing inside the orchestrate/`lfg` pipeline this already happened upstream; if
   landing a PR standalone that was never reviewed, run `/workflows:review` first). No reviewer has an
   open `CHANGES_REQUESTED`.
4. **Mergeable** — `mergeStateStatus` is not `DIRTY` (conflicts), `BLOCKED` (branch protection), or
   `BEHIND` (needs update) for a reason you haven't cleared. A human GitHub `APPROVED` is **not**
   required unless branch protection enforces it.

The `pr-landable-status` script computes 1, 2, and 4 mechanically and lists any `blockers`; condition
3 (the independent review having run) is the caller's responsibility — verify it before an autonomous
merge rather than relying on the script alone.

## Workflow

### 1. Identify the PR

```bash
# Default to the current branch's PR; or pass a number as the first argument.
PR_NUM=${PR_NUM:-$(gh pr view --json number --jq '.number')}
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

Repeat until all landability conditions hold, or you hit a blocker you cannot clear in ~2 attempts
(then escalate to the user with the specific failure from `blockers`):

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

- **Independent review not yet run** → if no `/workflows:review` pass has reviewed this PR this cycle,
  run it now (it delegates to fresh reviewer sub-agents) and resolve any P1/blocking findings before
  merging. Inside the orchestrate/`lfg` pipeline this already happened upstream — don't re-run it.

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

- **Autonomous (`--auto`, or called from `/lfg` / `/slfg` / `/workflows:orchestrate --auto`)** —
  merge without asking **once and only once** all conditions hold. This is the point of autonomous
  mode: do not bounce a "say the word and I'll merge" back to the user when the PR is already green,
  reviewed, and mergeable — just merge. If a condition is genuinely unmet (CI stuck red after retries,
  `CHANGES_REQUESTED` unresolved, or `mergeStateStatus: BLOCKED` by branch protection), do not merge;
  escalate that specific gap as a blocker.

### 5. Merge

```bash
gh pr merge "$PR_NUM" --squash --delete-branch
```

Use `--squash` by default (clean, single-commit history). Honor a different method if the repo
convention or the user calls for `--merge` or `--rebase`. If required checks are configured but you
want GitHub to merge the instant they pass, `--auto --squash` enables auto-merge instead of blocking.

### 6. Post-merge cleanup

```bash
# Sync the local default branch and prune the merged feature branch.
git checkout <default-branch>
git pull --ff-only
git branch -d <feature-branch>   # safe-delete; already merged
```

**Close the tracker item — idempotently.** `/workflows:work` Phase 4 closes the plan/work item at
**PR creation**, so in the normal pipeline the item is already closed and this is a no-op. Only act
if it is still open:

- **beads** — `bd show "$PLAN_BEAD"`; if still open, `bd close "$PLAN_BEAD" --reason="merged PR #${PR_NUM}"` then `bd dolt push`.
- **Linear** — `agentic-plugin linear push --file <plan-or-todo-path>` (silently skips without `LINEAR_API_KEY`).
- **GitHub issues** — `gh issue close <n> --comment "merged PR #${PR_NUM}"` if still open.
- **file-todos** — ensure the plan's checkboxes are checked and its frontmatter `status:` is `completed`.

### 7. Report

Summarize: the merged PR (number + URL), the merge method, that the branch was deleted and the local
default branch synced, and the tracker state. Note any follow-on work discovered while landing.

## Scripts

- [scripts/pr-landable-status](scripts/pr-landable-status) — print CI, review-decision, merge-state, and unresolved-thread count as JSON

## Success criteria

- PR shows `MERGED`.
- Feature branch deleted (remote and local); local default branch fast-forwarded.
- Tracker item closed (or confirmed already closed by Phase 4).
- In autonomous mode, the merge happened only because CI was green, an independent `/workflows:review`
  pass had run with P1s resolved, threads were resolved, and the PR was mergeable — never on an unmet
  condition, and never blocked waiting on a human GitHub approval the run was never going to receive.
