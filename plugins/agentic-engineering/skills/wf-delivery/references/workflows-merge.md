# Merge a PR

A thin route for landing an open PR. It does **not** reimplement merge
logic — it delegates entirely to the [`land-pr`](land-pr.md) reference, which:

- waits for CI to go green,
- resolves every review thread and finding through the `wf-review`
  PR-comment-resolution route,
- confirms the PR was independently reviewed and is mergeable,
- performs the mandatory final compounding check against the current PR head and records its
  `captured` or `not needed` audit evidence,
- merges and cleans up (deletes the branch, fast-forwards the local default branch), and
- dispatches on the resolved issue tracker: with a configured board (`github-project`) it verifies
  `done` and deletes its exact packet through the lifecycle engine; in an unconfigured repository
  (no board yet) it performs no tracker or packet write.

`land-pr` verifies the `done` stamp via `lifecycle_board.py --reconcile` rather than writing Status
itself — the merge automation is the writer; the reconciler only repairs drift if the automation
missed it. Compounding is not a Status value, and deployment/publication remains native delivery
evidence outside the ticket lifecycle.

## Run

Continue directly with the [landing reference](land-pr.md), passing the PR
number and optional `--auto` context through.

The **merge gate** is the reference's: pause-and-ask by default, auto-merge only in an autonomous
context (`--auto`, or when called from the `wf-development` orchestration route in an autonomous run) and only once
all landability conditions hold, including the current-head final compounding disposition. See the
reference for the full landability contract.
