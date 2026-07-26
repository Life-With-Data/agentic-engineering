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

The complete, named set of reasons a run stops and asks a human — in either
mode — lives in the [escalation contract](escalation-contract.md). Standard
mode is that same contract plus the routine gates autonomous mode suppresses
(plan approval, non-blocking findings triage, the interactive merge `[y/N]`);
do not restate stop reasons here or elsewhere — link to it instead.

## Delivery posture

Autonomous execution of a claimed work item is gated on two independent
things, not one:

Hands-off execution requires **both** grooming attestation (`Status >=
planned`, verifiable with `--groom-verify N`) **and** the ticket's autonomous
clearance (a `posture:autonomous` label, or an overriding per-invocation
token). Either one alone is not enough.

Clearance itself resolves from three sources in a fixed order, stated in full
exactly once:

**Per-invocation argument tokens > per-ticket posture label > repository
`delivery_mode` default (which itself defaults to `standard`).**

Every other mention of this ordering in this plugin links back to this section
by relative path rather than restating it.

### Reading the posture

Both halves of the gate come from **one** call, already machine-fused — do not
reassemble the conjunction from labels plus Status by hand:

```bash
python3 "<skill-directory>/scripts/lifecycle_board.py" --groom-verify <parent>
```

Branch on its output. Each row reads one field; none re-derives what a
`posture:*` label means:

| Read | Meaning |
|------|---------|
| `cleared: true` | Attested **and** ticket-cleared. Sufficient authority to proceed hands-off. |
| `cleared: false`, `posture_source: "ticket"` | The ticket decided. Standard posture; the repository default does **not** apply. |
| `cleared: false`, `posture_source: "unset"` | The ticket said nothing. Fall back to the preflight JSON's `delivery_mode_resolved` — and only when `groomed` is true. |

**`cleared: false` is not by itself a denial.** It is label-derived: the engine
sees neither the repository default nor per-invocation tokens, so a consumer
that reads only `cleared` fails *safe* — more restrictive, never more
permissive. That is intended.

**The engine owns the label-resolution rule; this document does not restate
it.** Clearance is a positive grant that fails toward `standard` in every
ambiguous case, and `resolve_clearance` in `scripts/lifecycle_board.py` is the
one place that rule is written down. A reader who needs the exact semantics
reads it there. Restating it here is what let a safety property drift between
two languages.

`--groom-verify` also best-effort de-boards open sub-issues, so it is not a
pure read. That is safe at this boundary: the write is idempotent and the
reconciler's rule 6 converges on the same state either way.

Deliberate differences from the complexity read:

- Complexity is read on the **sub-issue** at dispatch time; posture is read on
  the **parent** at the claim / routing boundary, **once per work item**.
- **Posture is fixed for the run at that read.** A run finishes under the
  posture it started with. Mid-run revocation is out of scope: removing the
  label takes effect the next time the item is claimed or routed, not at stage
  boundaries within a run already in flight.
- `--ready-work` does **not** carry labels or clearance — `ReadyItem` is
  `{number, title, priority, repo}`, populated by `merge_ready_legs` from the
  board item list. A queue drain therefore resolves each item's clearance with
  the same one-issue `--groom-verify` call at the claim boundary, where several
  calls already happen. Widening `ReadyItem` is out of scope.

### Who may grant clearance

**Adding `posture:autonomous` to an issue is the act of authorizing unattended
execution.** Anyone who can write labels on the repository can perform it. That
is the trust boundary, and it is worth stating plainly because nothing about a
label *looks* like a privilege grant.

**The conjunction is the defense.** A label alone grants nothing: hands-off
execution also requires `Status >= planned`, and Project Status is a separate
write scope from repository labels. Label-add privilege plus the grooming
attestation is the pair — which is exactly what the engine reports fused as
`cleared`.

Two standard escalation paths must therefore **never** attach
`posture:autonomous`:

- **An issue template's `labels:` key.** It applies its labels for *any*
  creator, including a drive-by external contributor who never held
  label-write privilege. A template that pre-attaches a posture label converts
  "can open an issue" into "can request unattended execution".
- **Any Action running with `issues: write`.** That token can attach the label;
  combined with a workflow triggered by untrusted input, it is a path from an
  external event to a clearance grant. Scope Actions to `permissions: {}` or
  read-only unless a label write is the workflow's actual purpose.

Neither path is open in this repository today — there is no
`.github/ISSUE_TEMPLATE/`, and no workflow holds `issues: write` — so this is a
boundary to preserve, not a finding to fix.

**De-escalating** takes an explicit write: `--decompose` with
`posture: standard` strips every `posture:*` label (a pure removal — the label
vocabulary has no `standard` entry). A hand-added `posture:standard` beside
`posture:autonomous` also revokes clearance on read, by the safe-wins rule the
engine owns.

### Queue drains need no separate opt-in

`/loop` and scheduled queue drains get no separate posture opt-in. Each
ticket's own marking decides its posture as it is claimed, so a single drain
can legitimately run some items hands-off and stop on others for the human.
That is intended behavior, not a degenerate case — the queue is heterogeneous
because the grooming decisions that filled it were.

## Resolve the starting state

Use the GitHub issue/project state and explicitly supplied artifacts.

- Ungroomed request or unreproduced bug: route to `wf-grooming`.
- Planned, unclaimed work: continue with `wf-development`.
- Implemented change: route to `wf-testing`.
- Verified change: route to `wf-review`.
- Review-ready PR: route to `wf-delivery`.
- A current PR needing its required knowledge-disposition check: route to
  `wf-documentation` before delivery merges it.

Only the "Planned, unclaimed work" and "Ungroomed request" branches above
depend on the [resolved posture](#delivery-posture) and its
attestation-AND-clearance gate. Resolve them against all four combinations of
groomed/un-groomed input and cleared/not-cleared posture:

| Input | Clearance | Behavior |
|-------|-----------|----------|
| Groomed (`Status >= planned`) | cleared | Proceed hands-off through implementation -> review -> delivery. |
| Groomed | not cleared | Standard: plan approval, findings triage, merge `[y/N]`. |
| Un-groomed | cleared | Route to `wf-grooming` **with the human**. Clearance does not survive a missing contract. |
| Un-groomed | not cleared | Route to `wf-grooming` with the human (today's behavior). |

**Un-groomed input routes to the human regardless of posture.** Autonomous
posture never silently auto-grooms; grooming stays collaborative by
construction, and a posture label on an un-groomed issue grants nothing.

The net new content is narrow: only the `planned` / unclaimed ->
`wf-development` branch can inherit hands-off execution, and only when the
resolved posture is autonomous.

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
irreversible scope changes, or repeated failures — see the
[escalation contract](escalation-contract.md) for the complete, named set.

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
