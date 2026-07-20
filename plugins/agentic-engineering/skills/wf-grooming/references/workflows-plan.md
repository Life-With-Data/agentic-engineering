# Plan a groomed engineering change

Turn a clear request into an implementation-ready work item without changing
product code. Repository architecture and artifact locations come from
`repository-overview` and `documentation`.

## Entry gate

Planning may begin only when intent, scope, and expected outcome are clear. A
bug also requires successful reproduction under [reproduce bug](reproduce-bug.md).
If competing product approaches remain, return to brainstorming or interview.

## Research

1. Read the mapped repository overview and relevant source.
2. Find existing patterns, interfaces, tests, and prior decisions.
3. Identify affected boundaries, dependencies, compatibility constraints, data
   or deployment risk, and unanswered questions.
4. Verify load-bearing assumptions before designing around them.

Use repository guidance for discovery mechanics. Do not assume a framework,
directory layout, plan-document path, or research agent.

## Produce the plan

The plan must include:

- problem statement and desired outcome;
- in-scope and explicitly out-of-scope work;
- chosen approach and rejected alternatives when the decision is material;
- affected components and interfaces;
- ordered implementation tasks with dependencies;
- acceptance criteria observable by a reviewer;
- validation scenarios and expected evidence, including the original
  reproduction for a bug;
- rollout, migration, monitoring, rollback, security, and data considerations
  when applicable;
- unresolved decisions and named blockers.

Tasks should be independently reviewable and small enough to verify. State what
must change and why; repository operational assets supply exact commands.

## Persist and track

Store the plan only when the mapped `documentation` capability defines a durable
plan location or format. Otherwise place the complete plan in the GitHub issue.
Use the repository's GitHub issue template, labels, ownership, and project
linkage. Decompose into sub-issues only when separate dependency or ownership
tracking materially helps.

In project-board mode, the planning route owns the transition to `planned`. In
plain GitHub mode it updates the issue without board writes. With no tracker,
return the complete plan and state that it is untracked.

If repository policy requires a documentation PR for the plan artifact, use
[land plan docs](land-plan-docs.md) with the exact mapped path.

## Ready boundary

Hand off to `wf-development` only when the work item has an unambiguous scope,
complete acceptance and validation criteria, resolved dependencies, and a
durable source of truth. Planning never claims implementation work.
