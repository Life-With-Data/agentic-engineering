---
title: "A GraphQL connection's default arguments can disable a whole code path — and a hand-built fixture will never notice"
category: integration-issues
tags: [github-graphql, gh-cli, fixtures, false-confidence, reconciler, lifecycle-board]
module: lifecycle-board
symptom: "A reconciler rule was unreachable in production for months while its unit test passed"
root_cause: "closedByPullRequestsReferences defaults to includeClosedPrs:false, so the CLOSED+unmerged node the rule keys on was never returned — and the test fed plan_repairs a hand-built node the real query cannot produce"
---

# GraphQL Connection Defaults Silently Disable Code Paths

## Problem

`lifecycle_board.py`'s reconciler rule 3 regresses an `in_review` issue back to
`in_progress` when its closing PR was closed without merging:

```python
if s.state == "OPEN" and s.stage == "in_review" and closing_prs \
        and all(p["state"] == "CLOSED" and not p["merged"] for p in closing_prs):
```

The rule was dead. `ISSUE_QUERY` fetched:

```graphql
closedByPullRequestsReferences(first: 5) { nodes { number state merged ... } }
```

`closedByPullRequestsReferences` takes an `includeClosedPrs` argument that
**defaults to `false`**. Nothing errors, no field is missing, the response is
well-formed — it simply omits every CLOSED-unmerged PR, which is exactly and
only the node rule 3 exists to match. Verified live on one issue:

```bash
# default
gh api graphql -f query='{repository(owner:"O",name:"R"){issue(number:56){
  closedByPullRequestsReferences(first:5){nodes{number state merged}}}}}'
# -> [{"number":61,"state":"MERGED","merged":true}]

# with the argument
gh api graphql -f query='{repository(owner:"O",name:"R"){issue(number:56){
  closedByPullRequestsReferences(first:5,includeClosedPrs:true){nodes{number state merged}}}}}'
# -> [{"number":27,"state":"CLOSED","merged":false}, {"number":61,"state":"MERGED","merged":true}]
```

So `closing_prs` could never contain a closed-unmerged node. With only
OPEN/MERGED nodes reachable, `all(...)` is always false; if the closed PR was
the issue's only closing reference the list is empty and the `and closing_prs`
guard fails. Either way: no repair, no error, no flag. Silence.

### Why the tests were green

The unit test built the input by hand:

```python
s = _issue(stage="in_review", closing_prs=[_pr(state="CLOSED", merged=False)])
repairs, _ = lb.plan_repairs([s], "main")   # passes
```

That node is a shape the real query cannot return. The fixture was not *wrong*
about the parser — it was describing data the query never asks for. This is a
different failure from
[recorded fixtures must be load-bearing](../testing-patterns/recorded-fixtures-must-be-load-bearing.md),
where the fixture and the parser disagreed about a shape both saw. Here the
parser and fixture agreed perfectly with each other and both diverged from the
**query text**, which no test read.

The same gap hid two more defects in the same change, both found by mutation
testing rather than by review reading: deleting `author { login __typename }`
from `ISSUE_QUERY`, and deleting `author_is_bot = state.author_is_bot` from the
effectful verbs, each left the entire suite green while restoring the original
bug in production.

## Solution

1. **Pass the argument explicitly** rather than relying on a connection default:

   ```graphql
   closedByPullRequestsReferences(first: 5, includeClosedPrs: true) { ... }
   ```

2. **Pin the query text with tests, by category not by spelling.** A fixture can
   only prove the parser reads what it is given; only an assertion on the query
   itself proves the query asks for it:

   ```python
   class IssueQueryShapeTest(unittest.TestCase):
       def test_closed_unmerged_prs_are_included(self):
           self.assertIn("includeClosedPrs: true", lb.ISSUE_QUERY)

       def test_issue_author_typename_is_requested(self):
           # scope to the issue's OWN selections — nested connections also
           # select `author`, so an unscoped assertion passes while the
           # issue-level selection is missing
           issue_level = lb.ISSUE_QUERY.split("closedByPullRequestsReferences", 1)[0]
           self.assertRegex(issue_level, r"author\s*\{[^}]*__typename")
   ```

   The scoping detail is not incidental: the first version of that assertion
   searched the whole query, matched the nested block, and let the mutation
   survive.

3. **Mutation-test the guard, not just the feature.** For each new production
   line, delete it and re-run the suite. A line that can be deleted with a green
   suite is not covered, however many tests appear to exercise the feature. This
   is how all three defects above were found.

## Prevention

- **Read the argument list, not just the field name.** GitHub's GraphQL schema
  is full of connection arguments whose defaults exclude data:
  `includeClosedPrs`, `projectItems(includeArchived:)` (defaults **true**, the
  opposite trap — this repo already handles it), `states:`, `orderBy:`. Check
  the schema for any connection whose result drives a conditional.
- **A silent repair is worse than a loud failure.** Rules that "just don't fire"
  produce no error and no flag. Any rule keyed on a narrow node shape deserves a
  test asserting the query can actually produce that shape.
- **Query text is production code.** Treat a GraphQL document like any other
  branch: if deleting a selection does not fail a test, the selection is
  unprotected regardless of how many parser tests exist.

## Resources

- Fixed in: PR #394 (parent issue #372, unit #380)
- Related: [recorded fixtures must be load-bearing](../testing-patterns/recorded-fixtures-must-be-load-bearing.md)
  — the adjacent failure mode, fixture-vs-parser rather than fixture-vs-query
- Related: [grep acceptance checks and subset fixtures give false confidence](../testing-patterns/grep-acceptance-checks-and-subset-fixtures-give-false-confidence.md)
- Guards added: `IssueQueryShapeTest` and `BotProvenanceVerbThreadingTest` in
  `plugins/agentic-engineering/tests/lifecycle_board_test.py`
