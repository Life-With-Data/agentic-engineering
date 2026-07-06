---
title: "gh api graphql cannot pass list-of-objects variables — inline them as GraphQL literals"
category: integration-issues
tags: [gh-cli, graphql, projects-v2, updateProjectV2Field]
module: lifecycle-board-bootstrap
symptom: "Variable $options of type [ProjectV2SingleSelectFieldOptionInput!]! was provided invalid value"
root_cause: "gh api graphql -f/-F only carry scalar variables; a JSON-encoded list arrives as a string and the API rejects it"
---

# gh api graphql Has No Transport for Structured Variables

## Problem

`gh api graphql -f options=<json>` sends the variable as a **string**. Any mutation whose input is a list of objects (e.g. `updateProjectV2Field`'s `singleSelectOptions: [ProjectV2SingleSelectFieldOptionInput!]!`) rejects it: *"was provided invalid value"*. There is no gh flag for structured variables, and `--input` (raw request body via stdin) doesn't fit an argv-only runner seam.

## Solution

Inline the structured value into the mutation **document** as a GraphQL literal and keep only scalar variables:

```python
def _options_graphql_literal(options):
    parts = []
    for o in options:
        fields = []
        if o.get("id"):
            fields.append(f'id: {json.dumps(o["id"])}')      # json escaping is valid GraphQL escaping
        fields.append(f'name: {json.dumps(o["name"])}')
        fields.append(f'color: {o["color"]}')                 # enum literals are UNQUOTED
        fields.append(f'description: {json.dumps(o.get("description", ""))}')
        parts.append("{" + ", ".join(fields) + "}")
    return "[" + ", ".join(parts) + "]"

document = MUTATION_TEMPLATE.replace("__OPTIONS__", _options_graphql_literal(options))
runner(["api", "graphql", "-f", f"query={document}", "-f", f"fieldId={field_id}"])
```

Two escaping rules: `json.dumps` output is valid GraphQL string escaping (including non-ASCII `\uXXXX`); enum values (colors) must be bare identifiers, never quoted. Only inline values you control or server-opaque ids — never untrusted text.

## Prevention

- Golden-fixture tests pin the **document** shape (options inlined, `__OPTIONS__` placeholder replaced, enum unquoted) and assert no `options=` variable flag is ever sent (`bootstrap_lifecycle_board_test.py::MutationDocumentTest`).
- Found only by running the bootstrap against the live platform — hand-written mocks had encoded the wrong transport and stayed green. Live-execute at least once any GraphQL mutation a script owns.

## Resources

- Fixed in: PR #44 (`scripts/bootstrap_lifecycle_board.py`, `apply_status_options`)
- Related: [github-graphql-owner-resolution.md](./github-graphql-owner-resolution.md) — the other live-run-only GraphQL bug
