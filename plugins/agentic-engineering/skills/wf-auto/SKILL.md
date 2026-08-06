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
definitions, the escalation set, posture resolution, or repository commands.
This skill is a thin front door onto `wf-orchestrate`, never a second
pipeline.

## Start here

```bash
python3 <skill-directory>/scripts/repository-context.py \
  --require repository-overview
```

Stop on contract failure. Then read [unattended run](references/auto-run.md):
it selects the ticket and dispatches `wf-orchestrate` for that item.

## What "unattended" means

An unattended run is `wf-orchestrate`'s autonomous mode with every optional
check-in suppressed — it adds no new authority and relaxes no gate. Which
gates autonomous mode already suppresses, and which stops survive it, are
stated once in the
[escalation contract](../wf-orchestrate/references/escalation-contract.md)
and in [orchestrate](../wf-orchestrate/references/orchestrate.md); this skill
adds nothing to either list.

What it does add: no run ever stops merely to ask whether to continue. A stop
that the contract does not name is not a stop. When the contract does name
one, the escalation is recorded on the tracker and the run ends there — the
tracker comment is the escalation, not a chat prompt.

## Completion

Report as `wf-orchestrate` does, plus the ticket selected and why. No ready
work is a result, not a question.

## Wrong-layer recovery

When the run needs stage internals or the next stage, that is
`wf-orchestrate`'s decision, not this skill's — dispatch, do not inline. When
a reference guesses a repository command, use the mapped repository
capability targets.
