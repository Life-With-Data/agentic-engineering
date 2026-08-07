---
name: wf-orchestrate
description: Workflow policy for running the complete engineering lifecycle end to end. Default entry point for any work item; resolves the item's current stage, dispatches the owning stage skill, enforces gates between stages, and carries the run to completion. This skill owns cross-stage routing, delivery posture, escalation, and sub-agent delegation policy; stage internals belong to the stage skills and repository mechanics to repository capability targets.
---

# Orchestration workflow

Layer: Workflow policy

Owns: lifecycle routing across stages, delivery-posture resolution, the
escalation contract, sub-agent delegation policy, stage-boundary gates, and
run completion reporting.

Requires repository capabilities: `repository-overview`; each dispatched stage
validates its own additional capabilities at its boundary.

Does not contain: stage-internal procedure (grooming, implementation, testing,
review, delivery, or documentation mechanics), repository commands, or
credentials.

## Start here

```bash
python3 <skill-directory>/scripts/repository-context.py \
  --require repository-overview
```

Stop on contract failure; read primary targets first, supporting targets only
as needed. Delegation is vertical: this router resolves the
work item's stage and dispatches the owning `wf-*` skill; stage skills do
their stage and return control here. They never route laterally to each other.

## Route the request

- Drive a work item through the lifecycle (the default): read
  [orchestrate](references/orchestrate.md). It resolves the starting state,
  reads delivery posture, and dispatches each stage skill at its boundary.
- Delegate stage work to sub-agents while validating results: read
  [sub-agent delegation](references/subagent-delegation.md).
- Decide whether a run stops to ask a human: read the
  [escalation contract](references/escalation-contract.md).

A single-stage request needs no orchestration: invoke the owning stage skill
directly and it reports its own completion.

## Completion

The run is complete only after a head-bound `wf-review` comprehensive verdict
exists for the head that was merged (see [land-pr condition
2](../wf-delivery/references/land-pr.md#landability-conditions)), the
pre-merge knowledge-disposition check has run, and delivery's terminal state
is verified by read-back.

## Wrong-layer recovery

When routing needs stage internals, dispatch the stage skill instead of
inlining its procedure here. When any reference guesses a repository command,
use the mapped repository capability targets. Workflow policy wins on
process; repository guidance wins on mechanics.
