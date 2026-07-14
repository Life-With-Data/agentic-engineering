---
name: workflows-merge
description: Merge a PR — a thin entry point to the land-pr skill (CI wait, review-thread resolution, merge gate, branch cleanup, idempotent tracker-item close).
argument-hint: "[optional: PR number — defaults to the current branch's PR] [--auto]"
disable-model-invocation: true
---

# Merge a PR

A thin command entry point for landing an open PR. This command does **not** reimplement merge
logic — it delegates entirely to the [`land-pr`](../../skills/land-pr/SKILL.md) skill, which:

- waits for CI to go green,
- resolves every review thread and finding (delegating to `resolve-pr-parallel`),
- confirms the PR was independently reviewed and is mergeable,
- merges and cleans up (deletes the branch, fast-forwards the local default branch), and
- idempotently closes the corresponding tracker item — dispatching on the resolved issue tracker
  (the lifecycle board via the shared reconciler, or `github` / `none` legacy close).

`land-pr` verifies the `shipped` stamp via `lifecycle_board.py --reconcile` rather than writing status itself — the merge automation is the writer; the reconciler only repairs drift if the automation missed it.

## Run

Invoke the skill, passing `$ARGUMENTS` (PR number and/or `--auto`) straight through:

```
skill: land-pr
```

The **merge gate** is the skill's: pause-and-ask by default, auto-merge only in an autonomous
context (`--auto`, or when called from `/workflows-orchestrate` in an autonomous run) and only once
all landability conditions hold. See the skill for the full landability contract.
