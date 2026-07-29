# Merge a PR

A thin route for landing an open PR. It does **not** reimplement merge logic —
it delegates entirely to the [`land-pr`](land-pr.md) reference, which owns the
landability contract, the merge gate (pause-and-ask by default, auto-merge
only in an autonomous context with all conditions held), the final compounding
disposition, and context-aware cleanup and tracker verification.

## Run

Continue directly with the [landing reference](land-pr.md), passing the PR
number and optional `--auto` context through.
