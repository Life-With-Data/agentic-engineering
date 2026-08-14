# Review a change

Review in proportion to risk. The goal is to find consequential defects, not to
prove that a review ceremony occurred. This review always runs after
development and before delivery — risk decides scope and depth, not whether it
happens.

## Establish intent

Read the request or work item, the complete diff, affected interfaces, and the
repository guidance relevant to those interfaces. Do not review against a
personal framework preference.

## Choose lenses

Always check required behavior, correctness, failure handling, and test
sufficiency. Add security, data integrity, concurrency, performance,
architecture, operations, accessibility, or UX only when the change touches
that risk surface.

Use a concise self-review for routine localized work — still a real pass, and
still posted on the PR. Use an independent reviewer for high-blast-radius,
security-sensitive, destructive, cross-cutting, or explicitly requested work.
Multiple reviewer agents are optional and should have distinct, relevant
scopes.

## Findings

Every actionable finding includes impact, exact location, evidence or a concrete
failure path, and a bounded fix direction.

- P1: unsafe, corrupting, exploitable, or materially fails required behavior.
- P2: a real defect that should block delivery.
- P3: a non-blocking improvement.

Do not turn style preferences, missing optional boilerplate, or hypothetical
edge cases with no plausible path into blockers. Deduplicate by root cause.

## Verdict

Return `ready` when acceptance criteria are met, required validation is
credible, and no P1/P2 finding remains. Otherwise return `not-ready` with the
blocking findings. Record the reviewed head SHA when an independent review is
being used as delivery evidence; a later material change invalidates that review.
