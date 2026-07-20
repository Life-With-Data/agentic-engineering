# Triage an intake queue

Triage turns unclassified findings and requests into explicit decisions. It does
not implement fixes, invent a local task-file system, or alter repository
operational guidance.

## Prepare

Resolve the configured GitHub tracker mode through the workflow preflight. Read
the repository overview and any existing issue template or contribution rules.
Gather the candidate items without changing them.

## Evaluate each item

Present one item at a time with:

- title and concise problem statement;
- source and available evidence;
- impact, urgency, and affected scope;
- known reproduction or validation state;
- dependencies and likely owner;
- recommendation: groom now, defer, merge with an existing issue, or reject.

Ask for a decision when priority or product scope requires judgment. Do not code
during triage.

## Record the decision

- **Groom now:** create or update a GitHub issue as an intake stub, preserving
  repository templates, labels, ownership, and project linkage. Route bugs to
  reproduction before they can become ready.
- **Defer:** keep the item in the repository's tracker with the chosen state and
  rationale.
- **Duplicate:** link the canonical issue and close or annotate the duplicate
  according to repository policy.
- **Reject:** record the concrete reason so the item is not rediscovered without
  new evidence.

When no GitHub tracker is available, return a structured decision record for the
user to place; do not create an unconfigured repository-local tracker.

## Completion

Report counts and links by decision, unresolved dependencies, and the next item
that should enter the full grooming route. No item becomes ready for development
merely because triage accepted it.
