---
title: "gh Projects v2 backfill: item-list/issue-list shapes, item-add idempotency, and --limit pagination"
category: integration-issues
tags: [gh-cli, projects-v2, item-list, issue-list, item-add, pagination, backfill]
module: lifecycle-board
symptom: "Building a board-backfill loop on gh: which JSON shapes are real, does item-add double-add, and does --limit silently cap?"
root_cause: "gh CLI output shapes and flag semantics are under-documented; guessing them (or reusing a 50-capped ready-work path) silently drops or mis-parses data"
---

# gh Projects v2 Backfill — Verified CLI Shapes & Semantics

Live-verified against `gh` 2.96.0 and board `aagnone3/projects/5` (2026-07), while building the one-time backfill verb (`lifecycle_board.py --backfill`, PR #66 / issue #64). These extend the lifecycle-board gh gotchas already recorded here — see [[gh-api-graphql-list-object-variables]] and [[github-graphql-owner-resolution]].

## The four things that matter

### 1. `gh project item-list --format json` → `content.repository` is a PLAIN STRING

```jsonc
{ "items": [ {
  "id": "PVTI_...", "status": "compounded",
  "content": { "type": "Issue", "number": 46,
               "repository": "owner/repo",              // <-- a string, NOT {nameWithOwner}
               "title": "...", "url": "https://..." } } ] }
```

The GraphQL API returns `repository { nameWithOwner }` (an object), but the **CLI** flattens it to a string. A repo-scoping predicate must handle the string form; the `isinstance(repo, dict)` branch is dead against CLI output but harmlessly defensive if the same helper also parses GraphQL. Draft items have `content.type == "DraftIssue"`; PRs are `"PullRequest"`.

### 2. `gh issue list --json number,url` excludes PRs for free

Unlike `gh search issues` (which conflates issues and PRs), `gh issue list` returns **issues only**. No PR-filtering needed in the backfill loop — a live run confirmed open PR #66 was absent while its 5 sibling issues were present. `number` is an int, `url` a string.

### 3. `gh project item-add <BOARD#> --url <issue-url>` is idempotent server-side

- The **positional arg is the project (board) number**, not the issue number — the issue is named by `--url`.
- Adding an already-present issue **twice** returns exit 0, empty stderr, and the **same** item id both times; the board item count does not change. So a stale membership pre-read at worst re-adds harmlessly — belt-and-suspenders on top of a set-difference.

### 4. `gh --limit N` is a TOTAL fetch cap that paginates internally — not a page size

Verified: `--limit 3` returned 3 of 8 items; `--limit 1000` walks API pages internally past the 100 (issues) / 50 (project-items) page boundaries. So a backfill that needs *all* issues must pass a high `--limit` (e.g. 1000) and flag truncation only at that ceiling (`len(results) >= LIMIT`).

## The trap this avoided

The ready-work path (`_item_list`) hard-caps at `READY_WORK_LIMIT = 50` — a UX bound, correct there. **Reusing it for backfill would have silently dropped every issue past 50.** A backfill must enumerate with its own high cap, not borrow a UX-scoped one. Two reviewers flagged the potential; a dedicated `BACKFILL_*_LIMIT = 1000` enumerator closed it.

## Prevention

- **Live-execute any new gh boundary once** before shipping — the mutating `item-add` was mock-only until a review agent ran it against the real board and confirmed idempotency + the positional-arg semantics. Mocks encode assumptions; only live output validates the shape (same doctrine as [[recorded-fixtures-must-be-load-bearing]]).
- **Record a non-empty fixture** of `item-list` output (structural fields verbatim, `content.body` may be stripped) and replay it through the real parser, so a future CLI shape drift breaks a test, not prod.
- **Never reuse a UX-capped enumerator for a completeness-critical loop.**

## References

- PR #66, issue #64 (backfill verb + recorded binding).
- Sibling design lessons: [[idempotent-backfill-and-recorded-config-design]].
