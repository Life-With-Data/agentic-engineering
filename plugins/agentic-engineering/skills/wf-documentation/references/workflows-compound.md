# Capture a reusable engineering lesson

Use this route only when completed work revealed a non-obvious lesson likely to
help future work and that lesson is not already enforced by code or tests.

## Decide

Capture knowledge when all are true:

- the lesson is specific and reusable;
- future engineers would not discover it quickly from the code or failure;
- the repository has an established durable owner for it; and
- keeping it accurate is worth the maintenance cost.

Otherwise return `not needed` and stop. Do not create an audit comment, empty
document, badge, or CI cycle to record that nothing was learned.

## Capture

1. Prefer a regression test or executable check when it can enforce the lesson.
2. Otherwise amend the existing maintained document readers already use.
3. Create a new document only when no suitable owner exists and repository
   guidance defines the location and indexing convention.
4. Run the repository's documentation checks for files actually changed.

Compounding is never a lifecycle status or merge gate. When practical, include
warranted documentation in the implementation PR; genuinely new knowledge found
after merge may use a separate documentation change.
