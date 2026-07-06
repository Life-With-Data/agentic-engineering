---
name: verification-loop
description: Run a systematic verify-before-done loop over a change — build, types, lint, tests, security, and diff review — and produce a ready/not-ready verdict. Use after completing a feature or refactor, before opening a PR, or whenever a change needs to clear quality gates.
---

# Verification Loop

Run a repeatable verification pass over a change before declaring it done. Each phase is a gate: run it, read the result, and fix blocking failures before moving on. The pass ends with a single report and a ready / not-ready verdict.

## When to Use

- After completing a feature or a significant code change
- After a refactor, before trusting the result
- Before opening a PR
- Whenever a change needs to clear quality gates and there is no existing verification harness driving it

## Principle

Detect the project's own commands first, then run them. Do not assume a stack. Read `package.json`, `Makefile`, `pyproject.toml`, `Cargo.toml`, `mix.exs`, or the CI config to learn the real build, lint, and test invocations. The commands below are illustrative defaults — substitute the project's equivalents. A phase that has no applicable command for the project is skipped and marked N/A, not failed.

## Verification Phases

Run the phases in order. A blocking failure in an early phase (build, types) makes later phases unreliable — stop and fix before continuing.

### Phase 1: Build

Confirm the project compiles or assembles. Run the project's build command, e.g. one of:

```bash
npm run build
make build
cargo build
```

If the build fails, stop and fix it before continuing — later phases run against stale artifacts otherwise.

### Phase 2: Type Check

Run the project's type checker where one applies, e.g.:

```bash
npx tsc --noEmit      # TypeScript
pyright .             # Python
```

Report every type error. Fix errors that block correctness before continuing.

### Phase 3: Lint

Run the project's linter/formatter check, e.g.:

```bash
npm run lint          # JS/TS
ruff check .          # Python
```

Record warnings; fix anything the project treats as an error.

### Phase 4: Tests

Run the test suite, with coverage when the project supports it:

```bash
npm test
pytest
cargo test
```

Report totals: tests run, passed, failed, and coverage if available. Investigate every failure — a failing test is a blocking result.

### Phase 5: Security Sweep

Scan the change for secrets accidentally committed and for debug residue left behind. Adjust patterns and file globs to the project's languages:

```bash
# Committed secrets (adapt the token patterns to the providers in use)
git diff --cached | grep -nE '(api[_-]?key|secret|token|BEGIN [A-Z ]*PRIVATE KEY)' || true

# Debug residue in the changed files
git diff --name-only | xargs grep -nE 'console\.(log|debug)|binding\.pry|breakpoint\(\)|dbg!' 2>/dev/null || true
```

Treat any hit as an issue to confirm or clear before shipping.

### Phase 6: Diff Review

Read the change as a reviewer would:

```bash
git diff --stat
git diff
```

For each changed file, check for: unintended edits, missing error handling, and unhandled edge cases.

## Output Format

After running the phases, produce one verification report:

```
VERIFICATION REPORT
===================

Build:     [PASS / FAIL / N/A]
Types:     [PASS / FAIL / N/A]  (N errors)
Lint:      [PASS / FAIL / N/A]  (N warnings)
Tests:     [PASS / FAIL / N/A]  (X/Y passed, Z% coverage)
Security:  [PASS / FAIL]        (N issues)
Diff:      [N files changed]

Overall:   [READY / NOT READY]

Issues to Fix:
1. ...
2. ...
```

Declare `READY` only when no phase reports a blocking failure. Otherwise report `NOT READY` and list the concrete issues.

## Checkpoint Mode

For long working sessions, do not defer all verification to the end. Run a lightweight subset (types + tests for the touched area) at natural checkpoints — after each finished function or component, and before switching tasks — and run the full loop before the final report or PR. Catching a regression at the checkpoint is far cheaper than tracing it across an accumulated diff.
