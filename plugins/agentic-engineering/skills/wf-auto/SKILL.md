---
name: wf-auto
description: Workflow policy for unattended, hands-off runs. Picks the highest-priority ready ticket when the caller names none, then carries that one ticket to merge with no check-ins — no plan approval, no findings triage, no merge confirmation — stopping only for a genuine blocker. Use when the human is away or explicitly asks for an unsupervised run. This skill owns ticket selection and check-in suppression; stages, gates, and routing stay with wf-orchestrate.
---

# Unattended run

Layer: Workflow policy

Owns: ticket selection when the caller names none, and suppression of every
optional check-in for the run.

Requires repository capabilities: `repository-overview`; the dispatched
lifecycle validates its own additional capabilities at each stage boundary.

Does not contain: stage sequencing, stage-internal procedure, gate
definitions, the escalation set, or repository commands. This skill is a thin
front door onto `wf-orchestrate`, never a second pipeline.

## Start here

```bash
python3 <skill-directory>/scripts/repository-context.py \
  --require repository-overview
```

Stop on contract failure. Then read [unattended run](references/auto-run.md):
it selects the ticket, states the authorized posture, and dispatches
`wf-orchestrate` for that item.

## What "unattended" means

Suppressed for the whole run: plan approval, non-blocking findings triage,
the interactive merge confirmation, and every "shall I continue?" between
stages. Fix P2 findings, defer P3 in the tracker, and merge under repository
merge policy without asking.

Not suppressed: the named stops in the
[escalation contract](../wf-orchestrate/references/escalation-contract.md).
Untrusted provenance, externally-imposed gates, and irreversible ops outside
the merge path stop an unattended run exactly as they stop any other. A
blocker is recorded on the tracker and the run ends there — the tracker
comment is the escalation, not a chat prompt.

Correctness gates are not check-ins and never relax: P1 review findings still
block delivery and route back to development, and every repository gate still
has to pass.

## Completion

Report the ticket worked, the stage reached, verification evidence, decisions
made, deferred findings, and any recorded blocker. When ticket selection
found no ready work, report that and stop — an empty queue is a result, not a
question.

## Wrong-layer recovery

When the run needs stage internals or the next stage, that is
`wf-orchestrate`'s decision, not this skill's — dispatch, do not inline. When
a reference guesses a repository command, use the mapped repository
capability targets.
