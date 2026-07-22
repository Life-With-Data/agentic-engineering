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

Resolve `<skill-directory>` to the directory containing this `SKILL.md`. All
scripts used by this workflow are bundled there; do not resolve them through a
plugin root.

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

The session's default agent orchestrates and validates grooming; it delegates
the legwork. Dispatch focused sub-agents for codebase reconnaissance,
prior-art and learnings research, and reproduction attempts, then verify their
reports before relying on them. The orchestrator retains scope decisions, user
interviews, plan readiness, and all issue writes. Set each sub-agent's model
explicitly at dispatch — hosts otherwise inherit the session's model — choosing
the lowest tier the task allows: an economy tier for mechanical searches, a
standard tier for scoped research and summarization, the strongest available
tier only for ambiguous reproduction or architectural analysis. Hosts without a sub-agent
mechanism run the same steps inline.

## Completion boundary

Grooming is complete only when the request is unambiguous, acceptance and validation criteria are explicit, repository capabilities have been consulted, and the work item is ready for `wf-development`. For bugs, the reproduction evidence is mandatory. Grooming never claims implementation work or edits product code.

## Wrong-layer recovery

If repository mechanics are needed, return to the capability targets from the validator. If a repository operational asset was opened before this workflow, use it only for mechanics and return here for gates and completion criteria.
