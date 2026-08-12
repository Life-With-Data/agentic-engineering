---
name: wf-grooming
description: Workflow policy for turning ideas, requests, bug reports, and un-groomed work into an actionable plan. Use first for requirements discovery, brainstorming, triage, bug reproduction, issue decomposition, grooming, or planning. This skill owns the ready-for-development boundary and never invents repository-specific commands.
---

# Grooming workflow

Layer: Workflow policy

Requires repository capabilities: `repository-overview`, `documentation`.

Does not contain: repository architecture details, tracker credentials, local commands, environment procedures, or product implementation.

## Start here

Validate the repository contract before reading repository guidance:

```bash
python3 <skill-directory>/scripts/repository-context.py \
  --require repository-overview \
  --require documentation
```

Stop on contract failure; read primary targets first, supporting targets only as needed.

For a bug report, also require the repository's reproduction mechanics before grooming:

```bash
python3 <skill-directory>/scripts/repository-context.py \
  --require development-environment \
  --require bug-reproduction
```

Production or integration failures also require `observability`. Reproduce bugs
when practical; if reproduction is unavailable, record the uncertainty and plan
the smallest diagnostic or evidence-backed change.

## Route the request

- Unclear intent or competing approaches: read [interview-me](references/interview-me.md), then [brainstorming](references/brainstorming.md).
- Formal brainstorm stage: read [workflow brainstorm](references/workflows-brainstorm.md).
- Groom an idea, bug report, or stub: read [workflow groom](references/workflows-groom.md).
- Work item with a significant UI/design aspect: read [design context](references/design-context.md).
- Reproduce reported behavior before grooming a bug: read [reproduce bug](references/reproduce-bug.md).
- Create or improve the bug report: read [report bug](references/report-bug.md).
- Produce the implementation plan and issue decomposition: read [workflow plan](references/workflows-plan.md).
- Compose or review a groomed issue body: read [ticket format](references/ticket-format.md).
- Strengthen an existing plan: read [deepen plan](references/deepen-plan.md).
- Sort an intake queue: read [triage](references/triage.md).

Load only the references needed for the active route.

## Completion boundary

Grooming is complete when the next implementation step is clear, success can be
checked, and material unknowns are visible. Match detail to risk: a small change
does not need an enterprise-style plan or issue decomposition.

In Project mode, `--groom-verify <N>` confirms the tracked plan. Grooming stops
at `planned`; a human moves the item to `ready_for_work` before development may
claim it. Grooming never writes that approval stamp. In an unconfigured
repository (`no_board`), make no tracker claim.

## Wrong-layer recovery

Workflow policy wins on process; repository guidance wins on mechanics — consult the mapped repository capability targets for the latter.
