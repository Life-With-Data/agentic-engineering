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

Use the GitHub issue/project state and explicitly supplied artifacts.

- Ungroomed request or unreproduced bug: route to `wf-grooming`.
- Planned, unclaimed work: continue with `wf-development`.
- Implemented change: route to `wf-testing`.
- Verified change: route to `wf-review`.
- Review-ready PR: route to `wf-delivery`.
- A current PR needing its required knowledge-disposition check: route to
  `wf-documentation` before delivery merges it.

## Execute

The orchestrator is the session's default agent acting as coordinator and
validator, not as the worker. Delegate stage work to sub-agents per
[sub-agent delegation](subagent-delegation.md) — research during grooming,
each implementation unit during development, test authoring, review lenses,
CI diagnosis, and documentation drafts — and set each sub-agent's model
explicitly at dispatch (hosts otherwise inherit the session's model), choosing
the lowest tier that unit's complexity allows. The orchestrator keeps the
session's own model for verification and triage.

Read the unit's persisted `complexity:*` label as the **primary** complexity
input rather than re-deriving it — grooming assessed it once with full plan
context (see
[grooming's complexity assessment](../../wf-grooming/references/workflows-plan.md)),
and the sub-issue is the dispatch unit that carries it. Read it with
`gh issue view <sub> --repo <origin> --json labels`. Map the tier to an agent
tier (advisory — the orchestrator retains judgment):

| `complexity:*` label | Intended agent tier |
|----------------------|---------------------|
| `complexity:trivial` | Fastest economy tier (e.g. Haiku, low effort). |
| `complexity:low`     | Economy tier. |
| `complexity:medium`  | Balanced/standard tier. |
| `complexity:high`    | Powerful, orchestrator/verifier-grade tier. |

When a unit carries **no** `complexity:*` label (an unlabeled or legacy issue),
fall back to deriving complexity inline from the unit's scope — economy tiers
for mechanical work, standard tiers for well-scoped work, the strongest
available tier only for ambiguous or high-blast-radius work. The label is an
optimization, never a hard dependency.

1. Validate the repository capabilities required by the current and next stage.
2. Claim work only at the development boundary.
3. Decompose implementation by dependency and file ownership. Parallelize only
   independent units; otherwise serialize or use repository-approved isolation.
4. Dispatch one focused sub-agent per unit with a self-contained brief and an
   explicit exit check; implement inline only when the host has no sub-agent
   mechanism or the unit is a trivial single edit.
5. Review every delegated result against acceptance criteria and rerun relevant
   repository gates independently.
6. Route failures back to the owning workflow with the concrete evidence.
7. Preserve tracker writer ownership; implementation helpers do not mutate
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
