# Failure Modes Catalog

The characteristic ways agent task-execution goes wrong. Each entry: what it is, the detection signal, the countermeasure. Consult this catalog when progress stalls, when behavior starts looping, or as a pre-report sweep.

## Execution

### Success theater

Green output that does not actually exercise the change — skipped tests, cached builds, a passing suite that never touches the new path.

- **Signal:** Confidence went up, but no observed output specifically demonstrates the change working.
- **Countermeasure:** The make-it-fail-once discipline; count tests instead of reading exit codes. See [verification-playbook.md](./verification-playbook.md).

### Patch spiral

Third, fourth, fifth variant of the same fix, each a guess mutated from the last.

- **Signal:** Two consecutive failed fixes at the same point.
- **Countermeasure:** The two-strike rule — stop editing, gather evidence: re-read the failing path, add a log line, build a minimal reproduction. Return only with new information.

### Wrong-file edit

Edits that change nothing because the executed code lives elsewhere: path shadowing, a generated copy, the wrong package, a stale build.

- **Signal:** Behavior identical after an edit that should visibly change it.
- **Countermeasure:** Prove the file is live — introduce a deliberate syntax error or log line, observe it surface, revert.

### Confident API hallucination

Calling a method or flag from memory of how such an API "usually" looks; it does not exist in the installed version.

- **Signal:** About to use an unfamiliar API without having opened its docs or source this session.
- **Countermeasure:** Check the installed version's actual surface first — read the source in `node_modules`/gems/site-packages, or fetch current docs — before the first call site is written, not after it fails.

### Mock blindness

Tests pass because the mocks encode the same wrong assumption as the code.

- **Signal:** Every test touching a boundary mocks that boundary.
- **Countermeasure:** One integration-level check per boundary touched — real serialization, real subprocess, real (local) service.

## Planning

### Imagined codebase

Planning against how the code probably looks rather than how it does.

- **Signal:** The plan names files or functions never opened this session.
- **Countermeasure:** Ground-truth reading before decomposition; quote real signatures in the plan.

### Scope drift

"While I'm here" edits accumulate until the diff no longer maps to the request.

- **Signal:** The diff contains changes matching no ledger item.
- **Countermeasure:** The ledger is the contract: new work becomes a new item (or gets reverted), never a silent expansion. Flag genuinely worthwhile side discoveries for a separate task instead of doing them inline.

### Sunk-cost spike

A throwaway probe becomes load-bearing architecture because deleting it feels wasteful.

- **Signal:** Untested prototype code on the main path of the final diff.
- **Countermeasure:** Spikes end in deletion or explicit promotion (cleanup pass plus tests). Port learnings, not lines.

## Steering

### Lost thread

A subtask silently dropped after an interruption, an error, or a long tool sequence.

- **Signal:** The ledger has an in-progress item that recent actions do not relate to.
- **Countermeasure:** Re-read the ledger after any interruption; before reporting, sweep it for orphaned items.

### Context amnesia

Retrying an approach that already failed earlier in the session or in a previous one.

- **Signal:** A "new" idea that feels familiar; an error message seen before.
- **Countermeasure:** Record ruled-out approaches on the ledger, with their disqualifying evidence, at the moment they are ruled out.

### Asking instead of looking

Escalating a question answerable by grep, read, or a ten-second experiment.

- **Signal:** About to ask the user something containing the words "does the codebase…".
- **Countermeasure:** The blocked-state taxonomy: facts are self-served; only decisions escalate.

### Looking instead of asking

Burning an hour reverse-engineering intent that only the user possesses: product scope, naming preferences, which of two valid behaviors is wanted.

- **Signal:** Long exploration producing no new *facts* — only competing interpretations.
- **Countermeasure:** Recognize interpretation questions early; ask once, with a concrete recommendation and a default.

## Finishing

### Premature done

Reporting complete on the strength of "the edits look right".

- **Signal:** The report contains no observed output — only intentions and descriptions of edits.
- **Countermeasure:** The done-definition gate: acceptance check passed + independent channel + negative space + empty ledger. Otherwise the honest status is "in progress" or "blocked", and the report says which.

### Hedged success

"Should work now" — uncertainty rounded up to completion.

- **Signal:** Modal verbs in the summary: should, probably, likely.
- **Countermeasure:** Calibrated reporting — every claim labeled Verified / Checked / Assumed per [verification-playbook.md](./verification-playbook.md). Downstream work builds on these labels; a false "verified" poisons everything after it.

### Stopping at a plan

Ending the turn with "Next, I'll…" — a promise where work should be.

- **Signal:** The final paragraph describes future actions that are executable right now.
- **Countermeasure:** If the closing line promises an action within current capability and scope, do not write it — do the action, then report it done.
