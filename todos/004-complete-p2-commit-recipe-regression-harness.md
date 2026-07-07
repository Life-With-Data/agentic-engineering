---
status: complete
priority: p2
issue_id: "004"
tags: [code-review, testing, follow-up]
dependencies: []
pr: 72
---

# Commit the recipe verification harness as a regression test (follow-up PR)

## Problem Statement

The 21-case live-verification harness that validated the Step 4.5 recipe (and caught the `--no-index` bug research missed) lives in the session scratchpad, uncommitted. The recipe's load-bearing details — `--no-index`, append-before-untrack ordering, the `tail -c1` newline guard — live in markdown where `bun test` checks only counts/frontmatter. A future "simplification" that drops `--no-index` or reorders steps regresses with zero automated signal.

This mirrors the repo's own learning (docs/solutions/testing-patterns/recorded-fixtures-must-be-load-bearing.md): unloaded verification reads as coverage it isn't. Explicitly NOT a blocker for PR #72 (nothing false is committed; the CHANGELOG scopes its claim honestly) — this is the durability follow-up.

## Findings

- Reviewer-suggested shape: a bun test that extracts the first fenced bash block after `## Step 4.5` from the SKILL.md **verbatim** (extraction-by-construction keeps test and doc synced) and runs the core scenarios in temp dirs: fresh repo, legacy-tracked re-run idempotence, broader `*.local.md` pattern, no trailing newline, non-git dir, symlinked `.gitignore`.
- The session harness at scratchpad `verify-62.sh` is a working starting point (same extraction approach).

## Proposed Solutions

1. **(Recommended)** New `tests/setup-recipe.test.ts` with verbatim extraction + 6 scenarios; separate PR. Effort: Medium. Risk: none.
2. Commit the bash harness as a script invoked from bun test (less idiomatic here). Effort: Small.

## Acceptance Criteria

- [x] Test extracts the recipe verbatim from SKILL.md (fails if the block moves/renames)
- [x] Covers the 6 core scenarios including symlink refusal
- [x] Runs in CI via `bun test`

## Work Log

- 2026-07-07: Created from PR #72 review synthesis (integration-boundary reviewer).
- 2026-07-07: Implemented Option 1 as `tests/setup-recipe.test.ts` (v3.5.4) — re-derived from the SKILL.md rather than adapting `verify-62.sh`, since the doc is truth. Verbatim extraction fails if the `## Step 4.5` heading or its bash block disappears; six scenarios run the extracted block via `bash` in hermetic temp git repos (pinned `GIT_CONFIG_GLOBAL`/`GIT_CONFIG_NOSYSTEM`/`GIT_CEILING_DIRECTORIES`), asserting the echoed `root=/gitignore=/tracked=` status line exactly (it is the recipe's declared observable, consumed by the untrack consent gate and Step 5). Mutation-verified: dropping `--no-index` fails the legacy-tracked scenario, disabling the `-L` guard fails the symlink scenario, renaming the heading fails extraction. Marked complete.

## Resources

- PR: https://github.com/aagnone3/agentic-engineering/pull/72
- docs/solutions/testing-patterns/recorded-fixtures-must-be-load-bearing.md
