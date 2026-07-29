---
name: wf-grooming
description: Workflow policy for turning ideas, requests, bug reports, and un-groomed work into an actionable plan. Use first for requirements discovery, brainstorming, triage, bug reproduction, issue decomposition, grooming, or planning. This skill owns the ready-for-development boundary and never invents repository-specific commands.
---

# Grooming workflow

Layer: Workflow policy

Owns: intent discovery, scope decisions, bug-report readiness,
reproduction-before-grooming, issue-backed plans, and the transition to
ready-for-development.

Requires repository capabilities: `repository-overview`, `documentation`.

Does not contain: repository architecture details, tracker credentials, local commands, environment procedures, or product implementation.

## Start here

Validate the repository contract before reading repository guidance:

Scripts are bundled beside this `SKILL.md`; resolve `<skill-directory>` to that
directory, never through a plugin root.

```bash
python3 <skill-directory>/scripts/repository-context.py \
  --require repository-overview \
  --require documentation
```

Stop on a non-zero result. Report the validator's error codes and do not substitute generic assumptions. When valid, read each required capability's primary target, then supporting targets only when needed, before creating grooming artifacts.

For a bug report, also require the repository's reproduction mechanics before grooming:

```bash
python3 <skill-directory>/scripts/repository-context.py \
  --require development-environment \
  --require bug-reproduction
```

Production or integration failures also require `observability`. A bug remains un-groomed until the reported behavior is reproduced through repository guidance. Inability to reproduce is a blocker to record, not permission to plan a speculative fix.

## Route the request

- Unclear intent or competing approaches: read [interview-me](references/interview-me.md), then [brainstorming](references/brainstorming.md).
- Formal brainstorm stage: read [workflow brainstorm](references/workflows-brainstorm.md).
- Groom an idea, bug report, or stub: read [workflow groom](references/workflows-groom.md).
- Work item with a significant UI/design aspect: read [design context](references/design-context.md).
- Reproduce reported behavior before grooming a bug: read [reproduce bug](references/reproduce-bug.md).
- Create or improve the bug report: read [report bug](references/report-bug.md).
- Produce the implementation plan and issue decomposition: read [workflow plan](references/workflows-plan.md).
- Strengthen an existing plan: read [deepen plan](references/deepen-plan.md).
- Sort an intake queue: read [triage](references/triage.md).

Load only the references needed for the active route.

## Sub-agent delegation

Delegate codebase reconnaissance, prior-art and learnings research, reproduction
attempts, and the scope challenge that argues for cutting proposed work to
focused sub-agents; the orchestrator retains scope decisions, user interviews,
plan readiness, and all issue writes. Roles,
dispatch, per-unit model selection, verification, and the inline fallback for
hosts without a sub-agent mechanism are owned by [sub-agent
delegation](../wf-development/references/subagent-delegation.md).

## Completion boundary

Grooming is complete only when the request is unambiguous, acceptance and validation criteria are explicit, repository capabilities have been consulted, and the work item is ready for `wf-development`. For bugs, the reproduction evidence is mandatory. Grooming never claims implementation work or edits product code.

In Project mode, grooming is complete only when `--groom-verify <N>` passes —
`Status >= planned` and Project Priority set (`p1`|`p2`|`p3`) on read-back,
where the `--decompose` write is the attestation, not the prose judgment; the
[plan route](references/workflows-plan.md) owns that mechanics. In an
unconfigured repository (`no_board`), make no tracker claim.

Groomed is not claimable. `planned` is grooming's ceiling, not `wf-development`'s floor: the groomed PARENT becomes claimable only once a human stamps `ready_for_work` — an approval no agent path performs, detailed in the `wf-setup` [lifecycle reference](../wf-setup/references/lifecycle.md#agent-write-scope-and-the-approval-seam). End a grooming run at `planned` by reporting that the item awaits that stamp, never by claiming it is ready for development. Its sub-issues are task units and must never be described individually as ready for development, and a sub-issue's board Status is never a readiness signal.

## Wrong-layer recovery

If repository mechanics are needed, return to the capability targets from the validator. If a repository operational asset was opened before this workflow, use it only for mechanics and return here for gates and completion criteria.
