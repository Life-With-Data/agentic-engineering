---
title: "fix(lifecycle): count only OPEN blocked-by deps in --claim/--ready-work"
type: fix
date: 2026-07-19
github_issue: 204
---

# fix(lifecycle): `--claim`/`--ready-work` count CLOSED blocked-by deps as open

`lifecycle_board.py` counts **all** `blockedBy` edges — including CLOSED
blockers — when deciding whether an item is claimable or ready. It queries
`blockedBy(first: 1) { totalCount }`, and GitHub's `totalCount` is
state-agnostic, so an item whose only blocker is already **closed** (its
dependency satisfied) is treated as still-blocked. Such an item becomes
permanently un-claimable via `--claim` and invisible to `--ready-work`,
silently stranding genuinely-unblocked work. The lifecycle spec gates on an
**open** blocked-by dependency, so counting closed blockers is a defect.

## Confirmed problem (grooming: problem → fix scope → regression test)

**Repro confirmed read-only** (no state mutation performed):

- The defect is present in source: `blockedBy(first: 1) { totalCount }` appears
  at `scripts/lifecycle_board.py:614` (top-level issue, drives claim),
  `:619` (sub-issues), and `:1514` (`_batched_blocked_counts`, drives
  ready-work). All three feed a `totalCount` that includes CLOSED blockers
  (parsed at `:679`, `:683`, `:1525`).
- `decide_claim` (`:915`) blocks whenever `blocked_by_count > 0`;
  `merge_ready_legs` (`:1043`) excludes whenever `blocked_counts[n] > 0`.
- **Note on the original repro fixture:** the issue cited #148 (blocked only by
  the closed #147) as the live example. #148 has since been **shipped/closed**,
  so it is no longer a live stranded item — but the underlying code defect
  persists for *any* future satisfied-dependency item. The regression test must
  therefore use a **synthetic** all-closed-blocker fixture (the #147→#148
  *shape*), not the live #148.

## Fix scope

Count only **OPEN** blockers. GitHub's `blockedBy` connection has no `states:`
filter, so fetch blocker states and count opens.

1. **Queries** — change every `blockedBy(first: 1) { totalCount }` to fetch
   states, e.g. `blockedBy(first: N) { nodes { state } }`, at all three sites:
   `ISSUE_QUERY` top-level (`:614`), `ISSUE_QUERY` sub-issues (`:619`, for
   consistency — same defect, same query), and `_batched_blocked_counts`
   (`:1514`).
2. **Parsers** — compute `sum(1 for n in nodes if n.get("state") == "OPEN")` at
   the three extraction sites (`:679` `blocked_by_count`, `:683` sub-issue
   `blocked_by`, `:1525` batched return dict) so claim and ready-work stay
   consistent.
3. **`first:` bound** — `first: 1` truncates the node list; pick a sane cap
   (e.g. 50). If a real item ever exceeds it, treat as blocked conservatively
   (or page) rather than under-counting — document the choice inline.

## Regression test (guard)

Add a unit test in `plugins/agentic-engineering/tests/lifecycle_board_test.py`
(hermetic tier-1, injected-runner/no-network convention) pinning **both**
directions off the same shape:

- all blockers CLOSED → `blocked_by_count == 0` → `--claim` proceeds and the
  item appears in `--ready-work`;
- ≥ 1 blocker OPEN → still counted → `--claim` returns `blocked` and
  `--ready-work` excludes it.

Drive it through the parser (`parse_issue_state`) and `_batched_blocked_counts`
so both the single-issue and batched paths are covered, then let the existing
`decide_claim` / `merge_ready_legs` tests confirm the threshold behavior.

## Acceptance Criteria

- [ ] `--claim <N>` proceeds when every `blockedBy` edge is CLOSED (no open blocker).
- [ ] `--claim <N>` still returns `blocked` when ≥ 1 blocker is OPEN.
- [ ] `--ready-work` includes items whose blockers are all closed; still excludes
      items with ≥ 1 open blocker.
- [ ] The sub-issue `blockedBy` count (`ISSUE_QUERY:619` / parse `:683`) is fixed
      the same way, for consistency across the single query.
- [ ] A unit test pins both directions (all-closed → claimable; ≥ 1 open →
      blocked), using a synthetic #147→#148-shaped fixture (NOT live #148).
- [ ] The `first:` node cap is chosen deliberately and its overflow behavior is
      documented inline (conservative-block or page — never silent under-count).

## Validation

- **Automated:** `bun test` — the existing lifecycle suite plus the new guard
  test must pass. (Runs `plugins/agentic-engineering/tests/lifecycle_board_test.py`.)
- **Live shape check (required once before shipping):** run one real
  `gh api graphql` querying `blockedBy(first: N) { nodes { state } }` against a
  known issue with a closed blocker, and confirm the `nodes[].state` shape
  matches the parser — per `docs/solutions/integration-issues/gh-projects-v2-backfill-item-list-shapes.md`
  and `.../gh-api-graphql-list-object-variables.md`, live-execute any new `gh`
  boundary once; recorded mocks encode wrong assumptions.
- **Manual:** on an item whose blockers are all closed,
  `python3 scripts/lifecycle_board.py --ready-work` lists it and
  `--claim <N>` proceeds; on an item with an open blocker, both still exclude/block.
- **Rollback:** revert the single commit; the query returns to `totalCount` and
  behavior reverts (re-introducing the defect, but safe).

## Context

- **Blast radius — test fixtures encode the old shape.** Several existing
  fixtures hard-code `blockedBy: { totalCount: N }` and one test asserts the
  parser reads exactly that shape:
  `lifecycle_board_test.py:362` (batched), `:396` (`_issue_query_response`
  builder), `:1059–1068` (parser-shape assertion), `:1199–1201`, `:1310–1312`
  (sub-issue payloads). Changing the query to `nodes { state }` **breaks these
  in lockstep** — the fixtures, the `_issue_query_response` builder, and the
  shape-assertion test must all move to the `nodes { state }` shape as part of
  this fix. This is the largest hidden cost and is why the change is single-task
  but non-trivial.
- The `_issue()` decision-core builder (`:28`) takes `blocked=<count>` and is
  unaffected — it feeds `blocked_by_count` directly; only the *parse-layer*
  fixtures (which model raw gh JSON) change.
- One writer per transition, stdlib-only, zero-network tests — honor the
  file's existing design rules (see the module docstring).

## Sources

- Origin issue: #204 (author `aagnone3`, MEMBER — trusted).
- Code: `plugins/agentic-engineering/scripts/lifecycle_board.py` — `ISSUE_QUERY`
  (`:608`), `parse_issue_state` (`:679`/`:683`), `decide_claim` (`:915`),
  `merge_ready_legs` (`:1043`), `_batched_blocked_counts` (`:1509`).
- Tests: `plugins/agentic-engineering/tests/lifecycle_board_test.py`.
- Learnings: `docs/solutions/integration-issues/gh-projects-v2-backfill-item-list-shapes.md`,
  `docs/solutions/integration-issues/gh-api-graphql-list-object-variables.md`
  (live-execute new gh boundaries; don't trust hand-written mocks).
