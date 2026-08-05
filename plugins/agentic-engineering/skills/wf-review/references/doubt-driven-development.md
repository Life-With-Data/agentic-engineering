# Doubt-Driven Development

A confident answer is not a correct one. Long sessions quietly turn
assumptions into "facts". Doubt-driven development materializes a
fresh-context reviewer — biased to **disprove**, not approve — before any
non-trivial output stands. This is not the `wf-review` comprehensive-review
route (a verdict on a finished artifact); it is an in-flight posture applied
while course-correction is cheap.

## When to use

A decision is **non-trivial** when it introduces branching logic, crosses a
module/service boundary, asserts a property the compiler cannot verify
(thread safety, idempotence, ordering), depends on context a future reader
cannot see, or has irreversible blast radius. Skip it for mechanical
operations, clear unambiguous instructions, summaries, one-liners, or when
the user explicitly asked for speed. Doubt applied to every keystroke ships
nothing.

## Loading constraints

Designed for a **main-session orchestrator** with a host-supported
fresh-context spawn. Never add it to a subagent's skills — spawning is one
level deep, so a subagent following Step 3 would attempt a forbidden nested
spawn. Reached from inside a subagent: surface that doubt-driven cannot run
nested; the degraded self-questioning fallback (fresh self-prompt with a hard
separator) is a last resort and must be flagged as degraded.

## The process

1. **CLAIM** — name the decision in 2–3 lines plus why it matters. A claim
   that cannot be written that compactly is a vibe, not a decision.
2. **EXTRACT** — the smallest reviewable unit: the artifact (diff, function,
   or 3–5-sentence proposal) plus the contract it must satisfy. Strip the
   reasoning — handing over conclusions returns validation of conclusions. A
   500-line PR is decomposed first.
3. **DOUBT** — invoke a fresh-context reviewer with an adversarial prompt:

   ```
   Adversarial review. Find what is wrong with this artifact.
   Assume the author is overconfident. Look for: unstated assumptions,
   unhandled edge cases, hidden coupling, contract violations, broken
   conventions, failure modes under unexpected input.
   Do NOT validate. Do NOT summarize. Find issues, or state explicitly
   that you cannot find any after thorough examination.
   ARTIFACT: <artifact>   CONTRACT: <contract>
   ```

   **Pass ARTIFACT + CONTRACT only — never the CLAIM** (handing the reviewer
   the conclusion biases it toward agreement). Match a bundled review agent
   to the domain (`security-sentinel`, `architecture-strategist`,
   `code-simplicity-reviewer`, `integration-boundary-reviewer`,
   `pattern-recognition-specialist`) or use a generic fresh-context agent;
   the adversarial prompt overrides any agent's default balanced-verdict
   shape.
4. **RECONCILE** — reviewer output is data, not verdict; the orchestrator
   re-reads the artifact against each finding and classifies in precedence
   order: **contract misread** (fix the contract, re-classify next cycle) →
   **valid + actionable** (change the artifact, re-loop) → **valid
   trade-off** (document it explicitly) → **noise** (correct under context
   the reviewer lacked — and ask whether the contract should have carried
   that context). A fresh reviewer can be wrong because it lacks context;
   do not defer just because it is fresh.
5. **STOP** — stop when the **current** cycle's findings all classified as
   trade-off or noise (a legitimate outcome, not doubt theater), or 3 cycles
   completed (escalate — three unresolved cycles is information about the
   artifact), or the user says "ship it". Never re-spawn on an unchanged
   artifact to "check again" — repeat findings are stalling. If 3 cycles
   feels insufficient because the artifact is large, the artifact is too
   big — return to Step 2 and decompose; do not lift the bound.

## Cross-model second opinion (optional)

A different-architecture model catches blind spots a single model shares
with itself. In an interactive standard-posture session, offer it **once per
artifact** after
the first single-model review — *"Want a cross-model second opinion (Gemini
CLI, Codex CLI, manual, or skip)?"* — and acknowledge the answer; skipping is
fine, silent skipping is not. In non-interactive contexts and
autonomous-posture runs, cross-model is
skipped and the skip is announced. Never invoke an external CLI without
explicit user authorization, and re-confirm the exact command each run.

Mechanics when the user opts in: verify the binary works before the real
prompt; write the adversarial prompt + ARTIFACT + CONTRACT to a file and
pipe it via **stdin** (never interpolate the artifact into a shell-quoted
argument — backticks and `$(...)` will truncate or execute); run the CLI in a
**read-only sandbox** (`codex exec --sandbox read-only`,
`gemini --approval-mode plan`) because a doubt artifact may itself contain
prompt-injection the CLI would otherwise execute against the workspace. If
the CLI fails, surface the failure and let the user redirect — no silent
single-model fallback.

## Red flags

Spawning a reviewer for a rename; treating reviewer output as authoritative
without re-reading the artifact; >3 cycles without escalating; "is this
good?" prompts; passing the CLAIM; stripping the CONTRACT; doubting only
after committing (that's the comprehensive-review route); classifying every
substantive finding away across multiple cycles **while leaving the artifact
and contract unchanged** — if nothing is actionable and nothing was learned,
escalate rather than loop. The standard rationalizations — "I'm confident",
"the reviewer will nitpick", "I'll doubt at the end", "two opinions are
always better" — are answered by the scope rules above: bounded, non-trivial
decisions only, reconciled rather than deferred to.

## Interaction with other routes

Comprehensive review is the post-hoc PR verdict; doubt-driven is per-decision
and in-flight — use both. A docs lookup verifies facts about a framework;
doubt-driven verifies the reasoning about the artifact. TDD's failing test is
a concrete disproof attempt for a behavioral claim, but it shares the
author's context — it complements, and does not substitute for, the
fresh-context review of a non-trivial artifact. Real failure modes surfaced
by the reviewer route to the `wf-development` debugging reference.

## Verification

- Every non-trivial decision stood as an explicit CLAIM with at least one
  fresh-context adversarial review of ARTIFACT + CONTRACT (no CLAIM, no
  reasoning).
- Findings classified against the artifact text, in precedence order.
- A stop condition was met; in interactive mode the cross-model offer was
  made and acknowledged, in non-interactive mode its skip was announced.
- Any external CLI run was stdin-piped, sandboxed read-only, and explicitly
  authorized.
