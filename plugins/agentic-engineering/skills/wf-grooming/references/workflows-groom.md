# Groom an intake item

Grooming converts an idea, request, bug report, or stub issue into a deliberate
planning decision. It never edits product code or claims implementation.

## Classify

1. Read the item and repository overview.
2. Identify whether it is a bug, feature, refactor, operational change,
   documentation change, or investigation.
3. Find duplicates, dependencies, and already-decided constraints.
4. Confirm the user-visible or operational outcome.

## Apply the route gate

- Unclear intent or competing outcomes: use interview and brainstorming.
- Bug: require verified reproduction and a complete bug report.
- Investigation: define the question, evidence needed, and stopping condition;
  do not disguise it as an implementation plan.
- Ready request: proceed to [workflow plan](workflows-plan.md).

## Resolve scope

Record in-scope behavior, explicit exclusions, acceptance criteria, validation
expectations, dependencies, and product decisions. Ask the user only for
decisions that cannot be resolved from repository evidence or the issue.

## Completion

Grooming completes only by handing an unambiguous item to planning or by
recording a concrete blocker, duplicate, rejection, or deferral. It may update
GitHub issue content and project state owned by this stage, but it must not
create branches, implementation commits, or repository conventions.
