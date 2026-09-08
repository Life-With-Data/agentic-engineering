# Groom an intake item

Grooming converts an idea, request, bug report, or stub issue into a deliberate
planning decision. It never edits product code or claims implementation.

## Classify

1. Read the item and repository overview.
2. Identify whether it is a bug, feature, refactor, operational change,
   documentation change, or investigation.
3. Classify the shape, alongside the type, into one of three paths:
   - **Spike** — a feasibility question whose output is an answer, not code
     kept. Skips scope resolution, acceptance criteria, and decomposition.
   - **Bounded** — a change to a flow that already exists in this repo.
     Skips brainstorming and multi-issue decomposition: one planned issue
     with acceptance criteria, no sub-issues.
   - **Architectural** — a new subsystem, or a change to an interface other
     components depend on. Skips nothing: full interview and brainstorming,
     then the plan route.
4. Find duplicates, dependencies, and already-decided constraints.
5. Confirm the user-visible or operational outcome.
6. State the chosen shape to the requester in one line — for example,
   "this looks bounded, so it gets one issue with acceptance criteria, no
   sub-issues" — and continue; do not wait for a reply. An override, if the
   requester gives one, arrives like any other correction.

## Apply the route gate

- Unclear intent, competing outcomes, or an architectural shape: use
  interview and brainstorming.
- Bug: require verified reproduction and a complete bug report.
- Investigation, or a spike shape: define the question, evidence needed, and
  stopping condition; do not disguise it as an implementation plan. Label
  anything built during a spike throwaway.
- Ready request, or a bounded shape: proceed to
  [workflow plan](workflows-plan.md) for one planned issue with acceptance
  criteria and no sub-issues.

## Resolve scope

Record in-scope behavior, explicit exclusions, acceptance criteria, validation
expectations, dependencies, and product decisions. Ask the user only for
decisions that cannot be resolved from repository evidence or the issue.

**Default-and-note rule:** when a scope question resolves to a minimal
defensible default from repository evidence, do not ask — pick the default,
record it as a stated assumption in the issue body, and let the human revise
it at the `ready_for_work` stamp. Examples:

- "stream-job and delete-job share the userId-only gate — include them?" →
  default: include both (same root cause), record the assumption.
- "which of two equivalent naming patterns?" → default: the dominant existing
  pattern, note it.

Before settling that scope, dispatch the `scope-skeptic` agent to argue the case
for cutting it — whether the item should exist at all and which proposed work
earns its place. The agent reports; the orchestrator still owns every scope
decision and every tracker write. Record what the challenge changed, or that
scope survived it, in the item's exclusions or decisions.

## Completion

Grooming completes only by handing an unambiguous item to planning or by
recording a concrete blocker, duplicate, rejection, or deferral. It may update
GitHub issue content and project state owned by this stage, but it must not
create branches, implementation commits, or repository conventions.
