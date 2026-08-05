# Orchestrate the engineering workflow

Drive a work item through the lifecycle by dispatching each stage skill at
its boundary while preserving that stage's gates. Orchestration never
collapses grooming, development, testing, review, delivery, or documentation
into one stage.

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

Autonomous is the default. Hands-off execution is authorized by the engine's
single fused verdict: `hands_off` on `--groom-verify N`, true exactly when a
human's approval stamp (`Status >= ready_for_work`), grooming attestation
(`Status >= planned`), and the ticket's posture (autonomous unless a
`posture:*` label opts it out) all hold. Who may grant the approval is defined
in the `wf-setup`
[approval seam](../../wf-setup/references/lifecycle.md#agent-write-scope-and-the-approval-seam).

Posture resolves from two sources in a fixed order, stated in full exactly
once — every other mention links here rather than restating it:

**Per-invocation argument tokens > per-ticket posture label > `autonomous`.**

### Reading the posture

The whole gate is **one** call and **one** branch field — never reassemble
the conjunction from `approved` plus `cleared` plus labels by hand; the
engine computes it:

```bash
python3 "<skill-directory>/scripts/lifecycle_board.py" --groom-verify <parent>
```

| Read | Behavior |
|------|----------|
| `hands_off: true` | Proceed hands-off through implementation -> review -> delivery. |
| `hands_off: false`, `approved: false` | Route to the human — to `wf-grooming` if ungroomed, or for the `ready_for_work` stamp if already `planned`. Posture never bypasses approval. |
| `hands_off: false`, `approved: true` | Proceed **immediately** in standard mode (plan approval, findings triage, merge `[y/N]`). A dispatch mode, never a halt awaiting further input. |

Component fields (`approved`, `groomed`, `posture`, `cleared`) exist to
report *why* a run is not hands-off, never to re-derive the verdict. The one
thing outside the engine's sight is a per-invocation argument token, which
overrides the **posture** leg for that invocation only — approval and
attestation still gate, and a token never substitutes for the
`ready_for_work` stamp.

**The engine owns the label-resolution rule; this document does not restate
it.** A `posture:*` label only reduces autonomy — every labeled state fails
toward `standard` — and `resolve_clearance` in `scripts/lifecycle_board.py`
is the one place that rule is written down. A reader who needs the exact
semantics reads it there.

- Complexity is read on the **sub-issue** at dispatch time; posture is read on
  the **parent** at the claim / routing boundary, **once per work item**.
- **Posture is fixed for the run at that read.** Mid-run revocation is out of scope:
  removing the label takes effect the next time the item is claimed or routed.
- `--ready-work` does **not** carry labels or clearance — `ReadyItem` is
  `{number, title, priority, repo}`, populated by `merge_ready_legs`; a queue
  drain resolves each item with the same one-issue `--groom-verify` call at
  the claim boundary.

### Who may set posture

**A `posture:*` label only reduces autonomy.** Attaching `posture:standard` —
or any stray, hand-typed, or legacy `posture:*` label — opts the ticket into
supervised execution; no label can grant more autonomy than the default. The
trust boundary for unattended execution is the human's approval stamp
(`Status >= ready_for_work`), a Project Status write scope no label-add
privilege reaches, fused with attestation into the engine's `hands_off`
verdict. An issue template's `labels:` key or an Action with `issues: write`
can therefore at worst force a ticket into supervision — an annoyance, never
an escalation vector.

**Returning a supervised ticket to the default** takes an explicit write:
`--decompose` with `posture: autonomous` strips every `posture:*` label (a
pure removal — the label vocabulary has no `autonomous` entry). A human may
equally remove the label directly in the GitHub UI — a deliberate edit the
lifecycle never fights.

### Queue drains need no separate opt-in

`/loop` and scheduled queue drains get no separate posture opt-in. Each
ticket's own marking decides its posture as it is claimed, so a single drain
is legitimately heterogeneous: some items run hands-off, others stop for the
human.

## Resolve the starting state

Use the GitHub issue/project state and explicitly supplied artifacts.

A re-run reconstructs open questions from the tracker, not from memory. For
any item carrying a `blocked-by` edge, read the sub-issue's — and its
parent's — `human`-labeled comments, and any human replies that follow them,
before surfacing a question; they are the
escalation's system of record (see the
[escalation contract](escalation-contract.md)). A persisted answer is
consumed and cited, never re-asked — only a question with no recorded answer
surfaces again.

- Ungroomed request or unreproduced bug: route to `wf-grooming`.
- Planned but not yet approved (`Status == planned`): route to the human for
  the `ready_for_work` approval stamp. Grooming's job already ended here —
  see [grooming's completion boundary](../../wf-grooming/SKILL.md#completion-boundary).
  Do not stamp it and do not describe it as ready for development.
- Approved, unclaimed work (`Status >= ready_for_work`): continue with
  `wf-development`.
- Implemented change: route to `wf-testing`.
- Verified change: route to `wf-review`.
- Review-ready PR: route to `wf-delivery`. Review-ready means a comprehensive
  `wf-review` verdict is recorded for the current head; a commit landed after
  the reviewed head invalidates that verdict and routes the item back through
  `wf-review` — a single-lens sub-agent pass is not the review stage.
- A current PR needing its required knowledge-disposition check: route to
  `wf-documentation` before delivery merges it.

Posture at this boundary is the engine's `hands_off` verdict — branch on it
per [reading the posture](#reading-the-posture); do not rebuild the table
here. **Not-yet-approved input routes to the human regardless of posture.**
Autonomous posture never silently auto-grooms and never silently
self-approves — the default grants nothing to an ungroomed or unapproved
issue, because `hands_off` folds the approval in.

## Execute

Delegate stage work to sub-agents per
[sub-agent delegation](subagent-delegation.md), setting each sub-agent's
model explicitly at dispatch to the lowest tier its unit's complexity allows.
The orchestrator keeps the session's own model for verification and triage.

Per-unit model selection — including the `complexity:*` label read and tier
mapping — is owned by [sub-agent delegation](subagent-delegation.md).

1. Validate the repository capabilities required by the current and next stage.
2. Claim work only at the development boundary.
3. Decompose implementation by dependency and file ownership. Parallelize only
   independent units; otherwise serialize or use repository-approved isolation.
4. Dispatch one focused sub-agent per unit with a self-contained brief and an
   explicit exit check; implement inline only when the host has no sub-agent
   mechanism or the unit is a trivial single edit. **Carry the resolved
   posture into every stage invocation and every sub-agent brief** — posture
   is read once at the routing boundary and propagated; a dispatched stage or
   sub-agent never re-derives clearance, and without the stated posture a
   stage falls back to its interactive defaults and stalls a cleared run.
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
