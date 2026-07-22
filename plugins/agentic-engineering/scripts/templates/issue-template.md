<!--
CANONICAL PARENT-ISSUE TEMPLATE (agentic-engineering eng workflow)

Fill every section. Delete a section only if you can state why it does not apply
(e.g. write "No external wiring required." rather than deleting that heading).
This body is written to the parent GitHub issue by the `wf-grooming` planning
route via `--body-file`. The issue and its native sub-issues are the durable
plan; no repository plan file or frontmatter join key is created.
-->

# [Issue Title]

## Overview

One or two paragraphs a reviewer can read in 30 seconds: what this changes and
the outcome when it ships. Lead with the "what" and the "why now", not the "how".

## Problem Statement / Motivation

The concrete pain, gap, or opportunity. Who is affected and how you know it
matters (metric, bug report, user quote, failing scenario).

## Visual Context

<!--
Include for work with a UI/design aspect; otherwise write "No visual context:
no UI/design aspect." under this heading (per the deletion rule above).
Externally hosted references (catalog links, Figma frames, hosted screen images)
embed as markdown images/links. Locally captured current-state screenshots attach
via the repository's mapped screenshot/attachment mechanism; when no such
mechanism exists, record the links/paths here and note the gap. Cover inspiration
references, relevant current-state visuals, and any potential future-state visuals.
-->

## Proposed Solution

The high-level approach. Enough for a reviewer to agree with the direction
before any code exists. Keep the complete implementation plan in this issue.

## Scope

- **In scope:** what this issue will deliver.
- **Out of scope:** explicitly what it will not, so reviewers don't expect it.

## System-Wide Impact

- **Interaction graph:** what callbacks / middleware / observers fire when this runs?
- **Error propagation:** how do errors flow across layers; do retry strategies align?
- **State lifecycle risks:** can partial failure orphan or corrupt state?
- **API surface parity:** what other interfaces expose the same functionality and need the same change?

## External System Wiring

For each external system this integrates with, document: the system + console
URL, the configuration objects required (webhooks, OAuth apps, scopes, secrets),
where that configuration lives, host-side wiring (allowlists, env vars, DNS), and
a **verification step that proves the config is live** (e.g. send a test event
from the provider dashboard and observe it in our logs).

If purely internal, state explicitly: **No external wiring required.**

## Planned Sub-Issues

Each entry becomes a native sub-issue under this parent. Order reflects
dependencies (`--add-blocked-by`); a task blocked by another must follow it.
After decomposition, GitHub's sub-issue list and rollup are progress authority;
do not add or maintain a duplicate completion checklist in this body.

- Task 1 — [what ships]
- Task 2 — [what ships] (blocked by Task 1)
- Task 3 — [what ships]

## Acceptance Criteria

Binary, checkable statements of "done". A reviewer must be able to mark each
true or false without judgement calls.

- [ ] [Observable behavior 1]
- [ ] [Observable behavior 2]
- [ ] Tests cover the new behavior and edge cases
- [ ] Docs / changelog updated where user-facing

## Validation

**How a reviewer proves this works — not that it compiles, that it behaves.**
Give the exact commands and the expected result, plus any manual steps.

```bash
# e.g. the test that exercises the new path
bun test path/to/relevant.test.ts
```

- **Automated:** [tests / lint / typecheck that must pass]
- **Manual:** [steps to drive the real flow and what to observe]
- **Rollback:** [how to revert safely if this misbehaves in production]

## Dependencies & Risks

Blocking work, prerequisite migrations, external approvals, and the risks worth
naming up front with their mitigations.

## Sources & References

- **Origin discussion or issue:** [link] — if applicable
- Similar implementations: `file_path:line_number`
- Related issues / PRs: #NNN
