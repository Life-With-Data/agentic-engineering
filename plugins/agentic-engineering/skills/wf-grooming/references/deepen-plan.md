# Deepen a plan

Use this reference after a plan exists but important uncertainty remains. It
improves evidence and sequencing without turning planning into implementation.

## Inputs

- The current plan and work-item identifier, when one exists.
- Acceptance criteria and validation requirements.
- The repository contract's primary targets for `repository-overview`,
  `documentation`, and any capability implicated by the change.

## Procedure

1. Mark claims in the plan as established, inferred, or unknown.
2. Inspect repository evidence for every unknown that can change scope,
   architecture, safety, or validation.
3. Follow supporting capability targets only when the primary target is
   insufficient for that question.
4. Research external primary sources only for unstable or third-party facts.
5. Identify interfaces, migrations, rollout boundaries, failure modes, and
   observability needs introduced by the plan.
6. Reorder work so dependencies and risk-reducing probes occur first.
7. Make each validation step falsifiable: name the behavior, evidence, and
   expected outcome without inventing repository commands.
8. Record unresolved decisions as explicit blockers or owner questions.

## Review lenses

Apply only lenses relevant to the change:

- product intent and user-visible behavior;
- data integrity and reversibility;
- security and trust boundaries;
- concurrency, performance, and scale;
- compatibility and rollout;
- test strategy and observability;
- documentation and operational handoff.

Use available reviewers or skills when they add domain knowledge, but never
assume a repository defines a particular skill name or storage layout. The
repository contract, not a scan of tool-specific skill directories, supplies
local operational context.

## Completion

Return the revised plan plus a short change log covering strengthened evidence,
new risks, reordered work, and unresolved blockers. A deeper plan is still a
plan: do not claim work, edit product code, or silently resolve product choices.
