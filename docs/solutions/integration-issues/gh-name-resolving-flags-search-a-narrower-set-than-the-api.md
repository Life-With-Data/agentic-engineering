---
title: "gh name-resolving flags search a narrower set than the REST API you looked the name up with"
category: integration-issues
tags: [gh-cli, milestones, rest-api, preflight, lifecycle-board]
module: lifecycle-board
symptom: "A milestone found by `gh api repos/{slug}/milestones?state=all` then fails to attach via `gh issue edit --milestone <title>`, surfacing as a misleading issues-write permission error"
root_cause: "gh's convenience flags resolve a NAME to an id through their own hardcoded query (`milestones(first:100,states:OPEN)`), which is narrower than the REST endpoint used to discover the name"
---

# A gh Name Flag and a REST Lookup Do Not Search the Same Set

## Problem

`--decompose` resolves a milestone create-or-reuse by exact title, then attaches
it with gh's native flag:

```python
listed = runner(["api", "--paginate", "--jq", ".[] | {number, title}",
                 f"repos/{ctx.slug}/milestones?state=all&per_page=100"])   # discovery
...
runner(["issue", "edit", str(parent), "--repo", ctx.slug, "--milestone", title])  # attachment
```

Two different resolvers, two different search sets. `state=all` finds **closed**
milestones; gh's `--milestone` flag does not. The gh binary carries exactly one
milestone-listing fragment for that path:

```bash
strings "$(which gh)" | grep -o 'milestones(first:[0-9]*[^)]*)'
# milestones(first:100,states:OPEN)
```

So a repository with a closed milestone titled `Non-demo data` takes the reuse
branch (`created: false`, no POST), and the very next call — the first mutation
in the verb — dies with gh's generic failure. The engine reports it as
`issue_edit_failed` / *"Verify the issue exists and you have issues-write
permission"*, sending the operator at permissions when the real cause is
milestone state. The preflight-before-mutation discipline was intact and still
produced a misleading diagnosis, because the preflight asked a **different
question** than the mutation would.

The same asymmetry sits under `first:100`: the engine paginates its own lookup,
gh's resolver is capped, so a repo past 100 open milestones reuses one the
attachment step cannot find.

## Solution

Keep the wide `state=all` listing — but use it to *diagnose*, not to reuse.
Match exactly, then reject anything the attachment step could not honor, before
any mutation:

```python
if row.get("title") != title:
    continue
if str(row.get("state", "")).lower() == "closed":
    raise BoardError("milestone_closed",
                     f"milestone {title!r} exists in {ctx.slug} but is CLOSED; "
                     "issues can only be assigned to an open milestone",
                     "Reopen the milestone, or use a different spec.milestone.title")
```

Narrowing the listing to `state=open` instead would have been worse: the closed
milestone becomes invisible, the verb POSTs a duplicate title, and GitHub's 422
lands as `milestone_create_failed` — a second wrong diagnosis. Widening the
query and narrowing the *acceptance* is what makes the error message true.

The general shape: when a preflight and the mutation it guards use different
resolvers, the preflight must assert the mutation's constraints, not its own.

## Prevention

- Verify a name-resolving flag's scope before designing lookup-then-attach.
  `strings "$(which gh)"` on the embedded GraphQL fragment is faster and more
  honest than reading the docs; `--help` confirms a flag exists, never what it
  searches. `gh_contract_test.py`'s `HELP_FLAG_MATRIX` pins existence only —
  it cannot catch a scope change.
- Normalize an identity key once, at resolution (`title = milestone["title"].strip()`),
  and pass the normalized value to every downstream consumer. A spec title with
  a trailing space otherwise wedges permanently: run 1 creates, run 2 finds no
  match and re-POSTs a title GitHub already stores.
- Mutation-check the tests that pin this. Three tests here passed against a
  deliberately broken implementation before they were tightened — dropping
  `*milestone_args` from the parent `issue create`, lowercasing the title match,
  and disabling the closed-milestone guard each left the suite green. A guard
  test that does not fail when its guard is removed is documentation, not a test
  (see [recorded-fixtures-must-be-load-bearing.md](../testing-patterns/recorded-fixtures-must-be-load-bearing.md)).

## Resources

- Fixed in: PR #358 (issue #350; `plugins/agentic-engineering/scripts/lifecycle_board.py`, `resolve_milestone`)
- Related: [gh-api-graphql-list-object-variables.md](./gh-api-graphql-list-object-variables.md) — the other case where a gh transport does not do what its flag implies
