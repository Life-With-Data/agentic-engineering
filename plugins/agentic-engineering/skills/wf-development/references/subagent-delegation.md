# Sub-agent delegation

Define how the session's default agent drives a work item's lifecycle by
delegating stage work to sub-agents while retaining validation, shared-state
ownership, and per-dispatch model selection. This is workflow policy: it names
roles and selection rules, never repository commands or host-specific APIs.

## Roles

- **Orchestrator** — the session's default agent. It owns decomposition,
  dispatch, verification, every tracker or board write, escalation, and
  completion reporting. It is the validator of delegated results, not the
  worker: it does not implement delegatable units itself.
- **Sub-agents** — the workers. Each receives exactly one tightly scoped unit
  with explicit exit checks and returns a structured report. Sub-agents never
  mutate shared tracker, board, or PR state.

Role assignment is self-disambiguating: an agent operating under a dispatch
brief is a sub-agent for that unit. It executes the brief directly and never
re-enters this policy as orchestrator, loads workflow routers to re-route its
unit, or delegates further.

## When to delegate

Delegate any unit that has a definable exit check and meaningful working
context: research fan-out, implementation of a planned unit, test authoring,
a review lens, CI-failure diagnosis, document drafting.

Keep with the orchestrator: direct conversation with the user, decisions that
need user input, scope and severity judgments, shared-state writes, and final
validation. Purely conversational turns and single-line mechanical edits may
stay inline; everything with an exit check defaults to a sub-agent.

Use only the host's documented sub-agent mechanism. If the host has none,
run the same sequence inline in stage order — delegation is an execution
model, never a gate on the work itself.

## Lifecycle delegation map

| Stage | Delegate to sub-agents | Orchestrator retains |
|---|---|---|
| Grooming | Codebase reconnaissance, prior-art and learnings research, reproduction attempts | Scope decisions, user interviews, plan readiness, issue writes |
| Development | Implementation of each planned unit, isolated diagnosis experiments | Decomposition, wave planning, diff verification, gate reruns, board writes |
| Testing | Test authoring per surface, failure analysis | Test strategy, evidence sufficiency, ready/not-ready verdicts, independent gate rerun |
| Review | One reviewer per selected review lens | Lens selection, deduplication, severity classification, fix/defer decisions |
| Delivery | Per-job CI-failure diagnosis, release-note and PR-body drafting | Merge decisions, PR and tracker state writes, release evidence |
| Documentation | Drafting and per-document review passes | Accuracy validation against source, placement, publication decisions |

## Model selection

The orchestrator chooses each sub-agent's model at dispatch time, per unit —
never one tier for the whole run. Set the model explicitly on every dispatch:
most hosts run a sub-agent on the session's own model when none is specified,
so omission silently buys the most expensive tier — inheriting by default is a
selection failure, not a choice. The default is the lowest tier that can pass
the unit's exit checks; reserve stronger tiers for units that demonstrably
need them. Judge complexity on three axes: ambiguity of the exit check,
reasoning depth required, and blast radius of a wrong answer.

| Tier | Use for |
|---|---|
| Economy (fastest, cheapest) | Mechanical, low-ambiguity work with a deterministic exit check: renames, formatting, count updates, regenerating derived files, running prescribed commands and reporting output |
| Standard | Well-scoped implementation against clear acceptance criteria, research summarization, test authoring, first-draft writing |
| Strongest available | Ambiguous or high-blast-radius work: root-cause debugging, architectural and security judgment, cross-cutting refactors, criteria that need interpretation |

Selection rules:

- When uncertain between two tiers, start with the lower one; the retry path
  below is the recovery mechanism, and a cheap failed attempt costs less than
  routinely over-provisioning every dispatch. Exception: when a wrong answer
  would be expensive to detect or undo, take the stronger tier — retry only
  recovers from failures the exit checks can catch.
- Escalate one tier when re-dispatching after a dry attempt.
- The orchestrator keeps the session's own model for verification and triage;
  never validate a result with a weaker model than the one that produced it.

## Dispatch contract

Every brief is self-contained and includes:

1. **Scope** — exactly one unit; name what is explicitly out of scope.
2. **Context** — relevant files, patterns to mirror, conventions to match.
3. **Exit checks** — the acceptance criteria and quality gates that must pass.
4. **Exclusions** — no tracker/board/PR writes, no scope growth, no
   speculative extras, no adopting the orchestrator role: the recipient must
   not load workflow routers to re-route its unit or delegate further.
5. **Report format** — files touched, criterion-by-criterion evidence, exact
   gate results, assumptions made, and blockers stated explicitly.

Parallelize only file-disjoint units; otherwise serialize or isolate with the
[git worktree](git-worktree.md) reference and its bundled manager.

## Verification

Accept a delegated result only after independent verification: review the
diff against the unit's criteria and rerun the relevant repository gates at
the top level, through a channel independent of the sub-agent's own report.

- Bound retries at ~2 per unit, re-dispatching with the concrete failure
  appended. A retry with no measurable progress is a dry attempt; two dry
  attempts is a stall — block and escalate instead of looping.
- Work a sub-agent discovers becomes a tracked follow-on item, never silent
  extra scope inside the same dispatch.
- Stage sequencing, gates, and completion criteria stay with the owning
  `wf-*` workflow; delegation changes who executes a unit, not what the
  workflow requires.
