# Review a change

Use this reference for a comprehensive review of implemented work. It defines
review sequencing and evidence standards; repository conventions and commands
come from the capability map.

## Establish intent

1. Identify the work item, acceptance criteria, and validation requirements.
2. Read the complete diff and affected interfaces.
3. Read the primary `repository-overview` and `test-execution` targets.
4. Load supporting capability targets only where the change crosses their
   domain, such as data, infrastructure, or security.

Do not review against guessed requirements or a preferred framework style that
the repository has not adopted.

## Select review lenses

Use only lenses supported by the risk surface:

- acceptance-criteria conformance;
- correctness and failure handling;
- security and trust boundaries;
- data integrity and migration safety;
- concurrency, performance, and resource use;
- architecture and interface compatibility;
- test sufficiency and observability;
- documentation and operational readiness.

Specialized reviewers are optional. Give each the intended behavior, relevant
diff, and repository evidence; do not ask every available reviewer to inspect
every change.

## Findings contract

Every finding must contain:

- severity and user/system impact;
- exact file and narrow line range;
- reproducible evidence or a concrete failure path;
- the violated acceptance criterion, repository rule, or safety invariant;
- a bounded remediation direction.

Use these levels:

- P1: unsafe, corrupting, exploitable, or materially under-delivers required behavior.
- P2: real functional or operational defect that should block readiness.
- P3: bounded improvement that does not invalidate the change.

Deduplicate findings by root cause. Do not elevate style preferences into
blocking findings without repository evidence.

For a UI-affecting change, absent visual evidence is itself a reviewable
finding: request the evidence from the development stage (via the
orchestrator or the PR thread), never by pausing to ask the user. Raise it at
P3 as a
"request before/after or expected-state screenshots" finding, and escalate when
the acceptance criteria demand visual proof — to P2 when a criterion is not
verifiable without it, or P1 when it materially under-delivers required
behavior. In an autonomous run where the repository maps no capture or
attachment mechanism, local capture paths recorded in the PR body satisfy the
evidence request, with the missing mechanism noted as a capability gap. This
applies only to changes that touch a user-visible surface; do not
raise it against non-UI changes.

## Record and resolve

Record findings through the repository's configured tracker or review system.
Non-blocking findings triage is a routine gate standard mode keeps and
autonomous mode suppresses in its favor (autonomous fixes P2 and defers P3
per policy instead of asking); see the
[escalation contract](../../wf-orchestrate/references/escalation-contract.md)
for the complete, named set of reasons a run stops regardless of mode. For
each proposed fix:

1. return to `wf-development` for implementation;
2. re-run relevant evidence through `wf-testing`;
3. re-check the affected finding and acceptance criterion;
4. resolve the review thread only after evidence passes.

## Verdict

Return `ready` only when acceptance criteria are satisfied, required validation
is credible, and no unresolved P1 or P2 findings remain. Otherwise return
`not-ready` with the blocking findings and the next owning workflow.

A `ready` verdict names the reviewed head SHA — the commit the reviewed diff
came from — and holds only for that head; any later commit, including rework
requested by the user, invalidates it and returns the item to not-yet-reviewed.
The verdict is live run state returned to the caller, never persisted as
trusted control-flow: a later run that cannot produce a verdict for the
current head re-runs the review rather than reconstructing one from tracker
or PR comments.
