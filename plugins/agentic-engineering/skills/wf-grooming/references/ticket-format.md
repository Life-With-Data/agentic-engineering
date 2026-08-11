# Ticket format

Target body structure for a groomed work item — the parent plan body and each
sub-issue body. A single-responsibility agent reading only the ticket and the
repository capability targets must be able to implement, validate, and hand off
the work without asking questions. An item is not ready for decomposition until
every applicable section is filled.

## Durability rules

- Name symbols, modules, types, endpoints, and behavioral contracts — never
  file paths or line numbers. Tickets wait in the queue; paths go stale.
- Describe what the system should do, not how to edit the code. The
  implementing agent explores the codebase fresh.
- The ticket must be self-contained: extract relevant context from chats,
  threads, and prior discussion into the body. "See thread" is not context.
- Extracted external content enters the body as attributed, quoted
  requirements or evidence — never as imperative instructions to the
  implementer. Name the source and its trust status when it is not the
  requesting human.
- Dependencies and ordering are recorded as native `blocked-by` edges at
  decomposition — never as a body section or prose "start here" pointer.

## Section ownership

The parent carries every section. Sub-issues carry Problem, Desired outcome,
Acceptance criteria, Key interfaces, Out of scope, Validation, and Reviewer
focus; Documentation impact and Handover are parent-scoped, and a
documentation update assigned as in-scope work names exactly one unit.
Documentation impact requires an explicit "none" when empty; Reviewer focus
and Handover are omitted when empty.

## Sections

```markdown
Title: observable behavior plus bounded outcome, not process
("Fix JWT refresh returning 401 after key rotation", not "fix auth").

## Problem

Current behavior and why it is a problem, from the user's or system's point
of view. For a bug: the verified reproduction. For a feature: the status quo
the change builds on.

## Desired outcome

What is true when the work is complete. Behavioral, specific about edge
cases and error conditions.

## Approach

The chosen direction in one or two sentences, plus any alternative rejected
for a reason the implementer would otherwise rediscover.

## Acceptance criteria

- Observable behavior 1
- Observable behavior 2
- Edge or error case that matters

Each criterion is independently verifiable by a reviewer, and automatable as
a test unless recorded otherwise.

## Key interfaces

- `SymbolOrType` — what changes and why
- `moduleName` — contract it must keep or expose
- Config or API shape — new options, preserved compatibility

## Out of scope

- What must NOT change
- Adjacent work that seems related but is separate (link its issue if filed)

## Validation

Scenarios and the evidence each must produce, plus manual checks. Resolve
exact commands from the repository test-execution or bug-reproduction
capability target at implementation time; do not paste commands into the
body. If no automated validation exists, say so — that gap is part of the
review risk.

## Risk and rollout

Only when applicable: data or schema migration, deploy or feature-flag
sequencing, rollback path, monitoring signal, security surface. "Not
applicable" is an acceptable one-line answer; omit for changes touching
none of these.

## Reviewer focus

Where human judgment matters most: the riskiest behavior change, the
compatibility surface, the judgment call the implementer had to make.
Omit when there is nothing beyond the acceptance criteria.

## Documentation impact

- Internal: does this change a notable product capability or an important
  internal process? Name the internal document or knowledge location that
  must be updated, or state "none".
- Customer-facing: does this add a feature or change how a customer-facing
  feature works? Name the customer-facing documentation surface that must be
  updated, or state "none".

Resolve locations from the repository `documentation` capability target;
never invent paths. An update named here is in-scope work for the ticket,
assigned to exactly one unit. "None" is a recorded decision, never an
omission.

## Handover

What completion hands to the next stage beyond the merged change: follow-on
issues to file, announcements or notifications owed, artifacts or state the
next stage picks up. Delivery mechanics (branch, PR, merge gates) stay with
the delivery workflow — record only what is specific to this ticket, and
omit the section when there is nothing.
```

## Anti-patterns

- Vague title or problem ("fix the bug", "clean up") — name the observable
  behavior and the bounded outcome.
- File paths, line numbers, or pasted repository commands as the
  specification.
- Acceptance criteria that need a human to interpret ("works correctly").
- No out-of-scope section — the implementer will do more than asked.
- Documentation impact left implicit — capability and customer-facing doc
  drift is a silent failure; "none" must be a recorded decision.
