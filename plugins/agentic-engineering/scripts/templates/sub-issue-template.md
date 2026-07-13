<!--
CANONICAL SUB-ISSUE TEMPLATE (agentic-engineering eng workflow)

A sub-issue is the claim/task unit: one focused, independently verifiable piece
of the parent. It is open/closed only — it carries no lifecycle stage. Ordering
between sub-issues is expressed with native dependencies (`--add-blocked-by`),
not prose. This body is written by `/workflows:plan` Step 7 via `--body-file`
when it decomposes the parent into sub-issues.

Keep sub-issues small enough that one person can carry them to a green PR in a
single sitting. If a section below has nothing to say, write why rather than
deleting the heading.
-->
# [Task title — a single deliverable]

Parent: #<parent-issue-number>

## Overview

One or two sentences: exactly what this task delivers and where it fits in the
parent. A claimant should understand the boundaries without reading the whole
plan.

## Context

The minimum a claimant needs to start: the files/modules touched, the pattern to
follow (`file_path:line_number`), and any decision already made in the parent
plan that constrains this task.

## Implementation Notes

The intended approach — enough to prevent a wrong turn, not a line-by-line
script. Call out anything non-obvious: an edge case, a shared helper to reuse, a
gotcha in the surrounding code.

## Acceptance Criteria

Binary, checkable "done" conditions for this task only.

- [ ] [Observable behavior]
- [ ] Tests cover the change
- [ ] No regression in adjacent behavior

## Validation

**How to prove this task works end-to-end.** The exact command(s) and expected
result — the same check the reviewer will run.

```bash
# the test / command that exercises this task
```

- **Automated:** [test(s) that must pass]
- **Manual:** [step to drive the real behavior, if any, and what to observe]

## Dependencies

- **Blocked by:** #<sub-issue> — [why it must land first], or "None".
- **Blocks:** #<sub-issue> — [what waits on this], if any.
