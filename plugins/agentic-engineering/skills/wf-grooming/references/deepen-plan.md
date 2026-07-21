# Deepen a plan

Use this reference after a plan exists but important uncertainty remains. It
improves evidence and sequencing without turning planning into implementation.

## Inputs

- The current GitHub issue-backed plan and work-item identifier.
- Acceptance criteria and validation requirements.
- The repository contract's primary targets for `repository-overview`,
  `documentation`, and any capability implicated by the change.

## Procedure

1. Read the current lifecycle state with
   `lifecycle_board.py --gate orchestrate --issue <N>`. If implementation has
   started (`in_progress`, `in_review`, or `done`), do not rewrite scope or
   regress Status; stop and route the proposed change through the owning
   development/delivery workflow.
2. Classify the proposed edits. Evidence and wording improvements may retain
   `planned`; any material scope, acceptance, validation, dependency, security,
   or provenance change invalidates the existing readiness attestation. Before
   making such a change, set Status back to `brainstormed` through the lifecycle
   engine and leave it there while decisions remain unresolved.
3. Mark claims in the plan as established, inferred, or unknown.
4. Inspect repository evidence for every unknown that can change scope,
   architecture, safety, or validation.
5. Follow supporting capability targets only when the primary target is
   insufficient for that question.
6. Research external primary sources only for unstable or third-party facts.
7. Identify interfaces, migrations, rollout boundaries, failure modes, and
   observability needs introduced by the plan.
8. Reorder work so dependencies and risk-reducing probes occur first.
9. Make each validation step falsifiable: name the behavior, evidence, and
   expected outcome without inventing repository commands.
10. Record unresolved decisions as explicit blockers or owner questions.
11. After a material change is resolved, re-enter the main planning route so
    its provenance check, decomposition writer, groom verification, and
    `Status = planned` attestation all run against the revised issue.

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

Update the issue and sub-issues, then return the revised plan plus a short
change log covering strengthened evidence, new risks, reordered work, and
unresolved blockers. A deeper plan is still a plan: do not create repository
plan files, claim work, edit product code, or silently resolve product choices.
