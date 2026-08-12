---
name: wf-orchestrate
description: Workflow policy for end-to-end engineering lifecycle routing from request to delivery. Use to resume a tracked item, choose or dispatch specialist stage skills, escalate blockers, and complete the run without requiring every stage separately.
---

# Orchestration workflow

Layer: Workflow policy

Owns: lifecycle routing, escalation, and run completion reporting.

Requires repository capabilities: `repository-overview`. Validate additional
capabilities when first needed, not again at every stage boundary.

Does not contain: stage-internal procedure (grooming, implementation, testing,
review, delivery, or documentation mechanics), repository commands, or
credentials.

## Start here

```bash
python3 <skill-directory>/scripts/repository-context.py \
  --require repository-overview
```

Stop on contract failure; read primary targets first and supporting targets only
as needed. In one continuous run, reuse validated repository context.

## Route the request

- Drive a work item through the lifecycle (the default): read
  [orchestrate](references/orchestrate.md). It resolves the starting state,
  reads delivery posture, and dispatches each stage skill at its boundary.
- Delegate independent work when parallelism or an independent risk check is
  useful: read [sub-agent delegation](references/subagent-delegation.md).
- Decide whether a run stops to ask a human: read the
  [escalation contract](references/escalation-contract.md).

A single-stage request needs no orchestration. An end-to-end run may also perform
small stages inline instead of manufacturing handoffs.

## Completion

The run is complete when the requested outcome is delivered, required repository
checks pass for the shipped head, blocking findings are resolved, and external
state changed by the run is verified. Use independent review and durable
documentation when risk or a real reusable lesson warrants them.

## Wrong-layer recovery

When routing needs stage internals, dispatch the stage skill instead of
inlining its procedure here. When any reference guesses a repository command,
use the mapped repository capability targets. Workflow policy wins on
process; repository guidance wins on mechanics.
