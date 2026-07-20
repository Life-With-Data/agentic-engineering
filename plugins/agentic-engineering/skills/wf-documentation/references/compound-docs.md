# Compound a solved problem

Use this reference after a non-trivial problem is solved and verified. Capture
durable reasoning without assuming where a repository stores documentation or
whether it uses repository skills.

## Gate

Compound only when:

- the observed problem and root cause are known;
- the solution has verification evidence;
- the lesson is likely to recur or prevents a costly failure;
- the repository's `documentation` capability identifies an appropriate home.

Skip compounding for one-off facts, speculative fixes, or information already
owned by an existing source.

## Build the record

1. State the symptom and affected context in searchable language.
2. Explain the investigation path, including misleading signals.
3. State the root cause precisely.
4. Describe the solution and why it works.
5. Record verification commands and expected evidence from the repository.
6. Extract the reusable principle separately from incident-specific details.
7. Add cross-links to relevant code, work items, decisions, and existing docs.

When the repository uses structured solution documents, use the schema and
template named by its mapped documentation guidance. This workflow deliberately
ships no repository document schema.

## Choose the owner

- Repository mechanics go into the mapped asset for the relevant capability.
- Product and architectural decisions go into the repository's established
  decision or design documentation.
- Shared workflow policy belongs in the owning `wf-*` skill only when the
  plugin's cross-repository process itself changed.

Prefer amending an existing source that agents already reach. If the learning
has no suitable owner, route to `wf-setup` to update the capability map. Do not
create a new repository skill, wrapper, or directory merely because the source
incident involved an agent.

## Validate and hand off

Run the repository's documentation checks, verify links and examples, and use
the repository's normal documentation-delivery path. Report the new durable
source and the capability that owns it.
