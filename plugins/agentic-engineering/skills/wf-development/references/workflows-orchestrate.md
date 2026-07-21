# Orchestrate the engineering workflow

Coordinate a prepared work item across the seven workflow owners while
preserving each owner's gates. Orchestration does not collapse grooming,
testing, review, delivery, or documentation into development.

## Modes

- **Autonomous:** make reversible implementation choices from evidence and stop
  only for genuine blockers or material product-scope changes.
- **Final review:** operate autonomously until the repository's merge boundary,
  then present one decision packet.
- **Steered:** surface product approach, plan approval, non-blocking review
  triage, and merge decisions.

## Resolve the starting state

Use the GitHub issue/project state and explicitly supplied artifacts. Do not
search a guessed plan directory, todo directory, or documentation path.

- Ungroomed request or unreproduced bug: route to `wf-grooming`.
- Planned, unclaimed work: continue with `wf-development`.
- Implemented change: route to `wf-testing`.
- Verified change: route to `wf-review`.
- Review-ready PR: route to `wf-delivery`.
- A current PR needing its required knowledge-disposition check: route to
  `wf-documentation` before delivery merges it.

## Execute

1. Validate the repository capabilities required by the current and next stage.
2. Claim work only at the development boundary.
3. Decompose implementation by dependency and file ownership. Parallelize only
   independent units; otherwise serialize or use repository-approved isolation.
4. Review every delegated result against acceptance criteria and rerun relevant
   repository gates independently.
5. Route failures back to the owning workflow with the concrete evidence.
6. Preserve tracker writer ownership; implementation helpers do not mutate
   shared issue or board state.

Retry a returned implementation at most twice when the failure is specific and
progress is measurable. Escalate ambiguous product decisions, missing access,
irreversible scope changes, or repeated failures.

## Decision and merge boundaries

P1 review findings block delivery and return to development. In autonomous mode,
fix P2 findings and defer P3 findings in the configured GitHub tracker unless
repository policy says otherwise. In steered mode, ask which non-blocking
findings to address.

Never infer merge authority. `wf-delivery` applies repository merge policy. A
final-review packet includes scope, key decisions, acceptance evidence, test
results, review findings and dispositions, delivery state, and remaining risk.

## Completion

Report the stage reached, tracker and artifact links, exact verification
evidence, decisions made, deferred work, and blockers. The complete loop ends
only after the pre-merge knowledge-disposition check and delivery have
completed.
