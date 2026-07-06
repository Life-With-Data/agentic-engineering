---
name: operating-principles
description: This skill should be used as the default operating approach for any nontrivial engineering work, especially delegated or autonomous execution. It captures, as explicit procedure, how a frontier model (Claude Fable 5) approaches operations — evidence before planning, risk-first decomposition, a deliberate next-action loop, independent-channel verification, and calibrated reporting. Depth is self-calibrating; easy tasks take a light path, hard ones the full procedure. Load at the start of multi-step or ambiguous work, when a first attempt has failed, when stuck or looping, or before reporting any nontrivial task complete.
---

# Operating Principles

How to operate, made explicit. Three metacognitive moves separate strong agent runs from weak ones: decomposing work so failure surfaces early, verifying work through a channel independent of the one that produced it, and choosing the next action deliberately instead of by momentum. This skill turns those moves into mechanical procedure — a distillation of how a frontier model (Claude Fable 5) approaches operations, written so a faster executor model can apply the same policy without re-deriving it. The principles apply to *all* work; only the depth of process varies.

## Step 0: Calibrate depth

How much process the work warrants depends on the work. Take the **full procedure** (Phases 1–5) when any of these hold:

- The full solution shape is not visible after one read of the relevant code
- Three or more constraints or subsystems interact
- The request is underspecified in ways that change the implementation
- A wrong change is expensive: data, migrations, auth, public APIs, money, anything irreversible
- A first attempt already failed

When none hold, take the **light path**: do the task directly, run one verification through an independent channel, report with calibrated claims. Applying heavy process to easy tasks wastes time and tokens — matching effort to stakes is itself one of the principles. The compressed rules at the end apply on both paths, always.

## Phase 1: Ground truth before planning

Most bad plans are plans over an imagined codebase. Before decomposing anything:

1. **Restate the goal as an acceptance check.** "Done means: \<observable behavior on a concrete input\>." If the acceptance check cannot be stated, that is the first gap to close — from the request, from the code, or with one precise question. A goal that cannot be phrased as a check cannot be verified later.
2. **Read the real code paths.** Locate actual entry points, actual signatures, actual data shapes — by opening them, not by recalling how such code usually looks. Quote real symbols in the plan; a plan that names functions never opened is fiction until proven otherwise.
3. **List the load-bearing assumptions.** Write down the 1–3 assumptions that would invalidate the whole plan if wrong ("the API supports idempotency keys", "this table has a unique key on Y"). Verify the cheapest-to-check, highest-blast-radius ones first, before writing implementation code.

## Phase 2: Decompose

Rules, in priority order:

1. **Order subtasks by risk, not by narrative.** The first subtask should be the one most able to kill the plan — the unproven API call, the riskiest integration, the ambiguous requirement. Discovering "this approach won't work" must cost one subtask, not the whole run.
2. **Give every subtask its own exit check.** "Compiles and this test passes", "prints the expected value for this input", "endpoint returns 200 with this body". A subtask whose completion cannot be independently checked is either two subtasks or a wrong cut.
3. **Slice vertically when integration is the risk** — build one thin end-to-end thread first, then widen. **Slice horizontally when a contract is the risk** — freeze the interface, stub one side, fill in both.
4. **Externalize the plan and keep it truthful.** Maintain a live task ledger (todo list). One item in progress at a time. Mark items done only after their exit check passes. Discovered work becomes *new* items — never a silent expansion of the current one. A ledger that doubles in size is a signal to re-plan, not to grind.
5. **Separate reversible from irreversible.** Proceed freely through reversible steps. Before any irreversible one (migration, deletion, force-push, external message), create a restore point and re-check that the evidence supports that specific action.

For the full pattern catalog — load-bearing question first, vertical slice, interface-first, spike-then-implement, checkpoint-before-irreversible, and the anti-patterns — read [decomposition-patterns.md](./references/decomposition-patterns.md).

## Phase 3: Execute — the next-action loop

Run every iteration of execution through the same explicit loop:

1. **Goal** — what does done look like? (From Phase 1.)
2. **Evidence** — what is the current state, *as observed*? Tool output, test results, code actually read. Not assumptions, not memory of what an earlier step probably did.
3. **Gap** — what specifically separates evidence from goal?
4. **Action** — choose by information gain when uncertain (which action most reduces the biggest unknown?), by dependency order when certain.
5. Act, observe, update the ledger. Repeat.

Hard rules inside the loop:

- **Two-strike backtrack.** Two failed attempts to fix the same failure means the mental model is wrong, not the patch. Stop editing. Gather new evidence: re-read the failing path, add a log line, build a minimal reproduction. A third patch variant without new information is gambling, not engineering.
- **Third-strike zoom-out.** If new evidence still does not crack it, question the decomposition itself: is this the right subproblem? Is the failing component even on the path to the acceptance check?
- **When stuck, articulate.** Write down what is known (with evidence), what is unknown, and what is assumed. The gap usually becomes visible in the writing. This costs one paragraph and routinely saves an hour of thrashing.
- **Blocked-state taxonomy.** (a) Missing a fact that a tool call can obtain → obtain it (read, grep, run, search); never ask the user for what grep can answer. (b) A genuine decision that changes scope or is irreversible → ask, with a recommendation and a default. (c) All approaches exhausted → report honestly what was tried, what was ruled out, and by what evidence.

When progress stalls or behavior starts looping, diagnose against [failure-modes.md](./references/failure-modes.md) — a catalog of the characteristic ways agent runs go wrong, each with a detection signal and a countermeasure.

## Phase 4: Verify through an independent channel

The core principle: **verification must be independent of generation.** Re-reading a diff with the same mental model that produced it finds almost nothing — the assumptions that created the bug will excuse it. Check through a different channel, strongest first:

1. **Execute**: run the tests, run the program on a concrete input, typecheck.
2. **Trace**: walk one concrete input — and one adversarial one (empty, boundary, duplicate, malformed, unauthorized) — through the changed path, computing actual values line by line.
3. **Hostile diff read**: review the full diff asking "what did this break?", not "is this what I meant?". Enumerate the negative space — what must NOT have changed — and check it: other callers, adjacent behavior, tests that should still pass.
4. **Sibling sweep**: every bug found implies a pattern; grep for the same pattern elsewhere before closing.

Two anti-theater disciplines, always:

- **Make it fail once.** A check that has never been seen failing verifies nothing. For any new test, break the code (or invert the assertion) once, watch it fail, restore. This also proves the edited file is actually on the executed path.
- **Confirm the green is real.** Tests actually ran (count them — "0 tests, 0 failures" is green), filters did not skip the relevant ones, the build is not cached, a mock is not swallowing the path under test.

Apply verification at two levels: each subtask's exit check as it completes (micro), and the Phase-1 acceptance check end-to-end before reporting (macro). Per-artifact checklists — bug fix, feature, refactor, migration, config — live in [verification-playbook.md](./references/verification-playbook.md).

## Phase 5: Report with calibrated claims

Separate three levels of confidence and label them:

- **Verified** — executed, output observed. ("Ran the suite: 142 pass, 0 fail — output above.")
- **Checked** — read or traced, not executed. ("Traced the empty-list case by hand; did not add a test for it.")
- **Assumed** — not examined. Must be flagged, never silently included.

Never round "should work" up to "works". *Done* means: the acceptance check from Phase 1 passes, verified through an independent channel, negative space checked, ledger empty or remaining items explicitly handed back. If the truthful report is "tests fail" or "step skipped", report exactly that — a faithful failure report compounds; a hedged success report poisons everything downstream.

## The rules, compressed

1. State *done* as an observable check before starting.
2. Read the real code before planning over it.
3. Put the plan-killing subtask first.
4. Every subtask gets an independently checkable exit condition.
5. Externalize the plan; keep it truthful; one item in progress at a time.
6. Checkpoint before anything irreversible.
7. Verify through a channel that did not produce the work; make every new check fail once.
8. Two failed fixes at the same point = wrong model, not wrong patch — go gather evidence.
9. Self-serve facts; escalate only real decisions; record ruled-out approaches with their evidence.
10. Claim only what was observed; label everything else checked or assumed.

## How this skill is layered

Progressive disclosure, thin to deep — load only as far as the work warrants:

- **Level 0 — always-on.** The ten compressed rules above, shipped as a paste-ready CLAUDE.md block in [claude-md-snippet.md](./assets/claude-md-snippet.md). The snippet keeps the rules in every session's context and carries the trigger line that pulls this skill in when depth is warranted. The `setup` skill installs it into a repo's existing `CLAUDE.md`/`AGENTS.md` (marker-guarded, idempotent), or paste it by hand. It mirrors "The rules, compressed" verbatim — when editing one, edit both.
- **Level 1 — this file.** The five-phase procedure: the spine for any task past the Step-0 gate.
- **Level 2 — references.** Depth on demand: [decomposition-patterns.md](./references/decomposition-patterns.md) when cutting up a task, [verification-playbook.md](./references/verification-playbook.md) when checking work, [failure-modes.md](./references/failure-modes.md) when stalled or looping.
