# Decomposition Patterns

A catalog of ways to cut a hard task into subtasks, each with the condition that selects it. Selection rule: identify the dominant risk first — integration? contract? unknown API? irreversibility? sheer size? — then pick the pattern built for that risk.

## Load-Bearing Question First

**When:** One uncertainty, once resolved, makes the rest of the task mechanical.

**How:** Name the question explicitly ("does the vendor API support idempotency keys?", "can the parser handle streaming input?"). Answer it with the cheapest possible probe — a doc lookup, a 5-line script, one curl — before designing anything that depends on the answer.

**Exit:** The question has an evidence-backed answer, recorded in the ledger.

**Failure it prevents:** Building three layers on an assumption that dies on contact with reality.

## Vertical Slice

**When:** Integration risk dominates — many layers must cooperate (route → handler → service → store → response) and the fear is they won't compose.

**How:** Build the thinnest end-to-end thread first: one endpoint, one happy-path input, hardcoded where harmless. Prove the layers connect. Then widen each layer.

**Exit:** A demonstrable round trip through every layer.

**Failure it prevents:** Big-bang integration at the end, where every layer's bugs surface simultaneously.

## Interface First (horizontal slice)

**When:** Contract risk dominates — two sides (client/server, module/module, team/team) must agree on a boundary.

**How:** Freeze the boundary first: types, schema, endpoint shapes, error contract. Stub one side. Build both sides against the frozen contract.

**Exit:** Both sides compile/typecheck against the same contract; the stub can be swapped for the real implementation without edits to consumers.

**Failure it prevents:** Rework when the two sides meet and disagree.

## Spike, Then Implement

**When:** An approach is uncertain enough that implementing it cleanly might be wasted work.

**How:** Timebox a deliberately throwaway probe that answers only the uncertain question. No error handling, no tests, no style. Then implement for real, using the spike as evidence.

**Rule:** Port learnings, not lines. Spike code becomes foundation code only after an explicit cleanup pass with tests — silently promoting it is how prototypes end up in production.

**Exit:** The uncertain question is answered; the spike is deleted or explicitly promoted.

## Checkpoint Before Irreversible

**When:** Any step that cannot be undone by `git checkout`: schema migrations, data deletion or mutation, force-pushes, external side effects (emails, payments, published posts), production config.

**How:** Classify each planned step reversible/irreversible up front. Before each irreversible one: create a restore point (backup, branch, snapshot, saved dry-run output), re-verify the evidence supports this exact action, and — if the action changes scope or outward-facing state — surface it rather than proceeding silently.

**Failure it prevents:** The unrecoverable mistake. Everything else in this catalog is about wasted time; this one is about damage.

## Scope Ledger

**When:** Always, for any task past the Step-0 gate.

**How:** Keep the externalized todo list as the single source of truth for intended work. One item in progress at a time. New discoveries become new items with their own exit checks. Record ruled-out approaches on the ledger too, with the disqualifying evidence — a future iteration (or a resumed session) must not retry them.

**Signals it emits:**
- Ledger doubled → re-plan rather than grind.
- Diff contains changes that map to no ledger item → scope drift; revert them or add the item explicitly.
- An item bounced in-progress → done → in-progress → its exit check was too weak; strengthen it.

## Fail-Fast Ordering

**When:** Choosing what to do first among decomposed subtasks.

**How:** Score subtasks by (probability of invalidating the plan) × (cheapness to attempt). Do the highest-scoring one first. Note this inverts the comfortable instinct to bank easy wins early — easy wins are worthless if subtask six kills the design.

## Anti-patterns

- **Narrative-order decomposition.** Subtasks mirror the order the feature would be described in ("first the model, then the view…") instead of dependency and risk order. Symptom: the risky part is scheduled last.
- **Mega-subtask.** "Implement the feature" as one ledger item. If an item cannot fail fast or be verified on its own, it is not a decomposition — it is the original task wearing a checkbox.
- **Imagined-codebase planning.** A plan that names files and functions that were never opened. Symptom: implementation immediately diverges from the plan. Fix: Phase-1 reading is not optional.
- **Horizontal lasagna.** Building complete layers bottom-up with no vertical thread — nothing integrates until everything integrates. Choose Interface First deliberately, or slice vertically; do not default into layers.
- **Sunk-cost spike.** The throwaway probe quietly becomes the architecture because deleting it feels wasteful. The waste already happened; keeping it just adds interest.
