# Merge a PR

A thin route for landing an open PR. It does **not** reimplement merge
logic — it delegates entirely to the [`land-pr`](land-pr.md) reference, which:

- waits for CI to go green,
- resolves every review thread and finding through the `wf-review`
  PR-comment-resolution route,
- confirms the PR was independently reviewed and is mergeable,
- merges and cleans up (deletes the branch, fast-forwards the local default branch), and
- idempotently closes the corresponding tracker item — dispatching on the resolved issue tracker
  (the lifecycle board via the shared reconciler, or `github` / `none` legacy close).

`land-pr` verifies the `shipped` stamp via `lifecycle_board.py --reconcile` rather than writing status itself — the merge automation is the writer; the reconciler only repairs drift if the automation missed it.

## Run

Continue directly with the [landing reference](land-pr.md), passing the PR
number and optional `--auto` context through.

The **merge gate** is the reference's: pause-and-ask by default, auto-merge only in an autonomous
context (`--auto`, or when called from the `wf-development` orchestration route in an autonomous run) and only once
all landability conditions hold. See the reference for the full landability contract.
