---
title: "Querying organization(login:) for a user account is a hard GraphQL error — use repositoryOwner"
category: integration-issues
tags: [github-graphql, projects-v2, user-vs-org, repositoryOwner]
module: lifecycle-board-bootstrap
symptom: "gh: Could not resolve to an Organization with the login of '<user>'"
root_cause: "GraphQL type-specific owner lookups error (not null) when the login is the other owner type; gh treats any errors array as command failure"
---

# Owner-Type-Agnostic Project Queries Need repositoryOwner

## Problem

A query asking both holders for a Projects v2 board —

```graphql
query($owner: String!, $number: Int!) {
  user(login: $owner) { projectV2(number: $number) { ... } }
  organization(login: $owner) { projectV2(number: $number) { ... } }
}
```

— **hard-fails for every user-owned project**: `organization(login:)` on a user login produces a GraphQL error entry (not a null), and `gh api graphql` exits non-zero whenever the `errors` array is non-empty, even though `data.user` resolved fine.

## Solution

One lookup that resolves both owner types, with inline fragments:

```graphql
query($owner: String!, $number: Int!) {
  repositoryOwner(login: $owner) {
    ... on User        { projectV2(number: $number) { workflows(first: 20) { nodes { id name enabled } } } }
    ... on Organization { projectV2(number: $number) { workflows(first: 20) { nodes { id name enabled } } } }
  }
}
```

## Prevention

- A tier-1 test pins the query shape: contains `repositoryOwner(login:` and never `organization(login:` (`bootstrap_lifecycle_board_test.py::WorkflowConfigTest`).
- Same lesson as the sibling doc: this survived unit tests with hand-built fixtures for *both* holder shapes and failed only against the real API. Live-execute owner-facing GraphQL at least once on a **user**-owned repo — org-assumptions hide there.

## Resources

- Fixed in: PR #44 (`scripts/bootstrap_lifecycle_board.py`, `query_workflows`)
- Related: [gh-api-graphql-list-object-variables.md](./gh-api-graphql-list-object-variables.md)
