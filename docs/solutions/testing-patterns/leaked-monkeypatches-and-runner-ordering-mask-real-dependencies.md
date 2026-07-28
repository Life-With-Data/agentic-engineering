---
title: "A leaked global monkeypatch plus a different local test runner hid a real dependency until CI"
category: testing-patterns
tags: [monkeypatch, test-isolation, pytest, unittest, test-ordering, ci-parity, addCleanup, false-green, lifecycle]
module: plugins/agentic-engineering/tests/lifecycle_board_test.py, plugins/agentic-engineering/scripts/lifecycle_board.py, .github/workflows/ci.yml
symptom: "Full local Python suite passed; CI failed 8 tests with `BoardError: Could not resolve Git's common directory` from a newly added preflight call"
root_cause: "Four test classes assigned lb.load_cache/lb.save_cache as module globals in setUp without restoring them, so whichever class ran first silently patched every later class; pytest and CI's `unittest discover` order classes differently, so locally the patch was in place before the affected tests and in CI it was not"
---

# A Leaked Global Monkeypatch Plus a Different Local Runner Hid a Real Dependency

## Problem

A new precondition was added to `verb_decompose` so that an un-migrated board
fails *before* the verb creates a parent issue and its sub-issues (a partial
decomposition no retry can repair). The first version resolved the board schema
through the on-disk cache:

```python
_schema_cache = load_cache(ctx)
resolve_schema(board, ctx, runner, _schema_cache)
save_cache(ctx, _schema_cache)
```

The full local Python suite passed — 581 tests. CI failed eight
`DecomposeVerbTest` cases with:

```
lifecycle_board.BoardError: Could not resolve Git's common directory
```

The failure was real, not infrastructural: `load_cache` resolves Git's common
directory, and `DecomposeVerbTest` builds a `RepoContext` that is not a git
repository. The code genuinely depended on something those tests could not
provide. Local runs simply could not see it.

## Investigation

The misleading signal was that local and CI ran "the same tests" and disagreed.
That framing sends you looking for an environment difference — Python version,
missing binary, sandbox permissions — when the actual difference was **which
tests had already run**.

Two independent facts combined:

1. **The patch leaked.** Four test classes did this in `setUp`:

   ```python
   lb.load_cache = lambda _ctx: {}
   lb.save_cache = lambda _ctx, _cache: None
   ```

   These are assignments to module globals on the imported `lifecycle_board`
   module. Nothing restored them, so once *any* of those four classes ran, every
   later test in the same process saw the stubs — including classes that never
   asked for them and whose own fixtures could not satisfy the real functions.

2. **The runners order classes differently.** CI runs
   `python3 -m unittest discover -s plugins/agentic-engineering/tests -p '*_test.py'`.
   Locally the suite was being driven with `pytest`. The two collect and order
   tests differently, so locally a patching class happened to run before
   `DecomposeVerbTest` and in CI it did not.

Either fact alone is harmless. Together they make green-vs-red depend on
collection order, which is exactly the kind of state that differs between a
developer's machine and CI.

## Root cause

`setUp` mutated imported-module globals without restoring them, giving tests a
hidden ordering dependency. The local runner's ordering happened to satisfy that
dependency and CI's did not, so a real production dependency on cache I/O was
masked locally and only surfaced after the change was pushed.

The deeper point: **a leaked patch does not merely risk a false failure, it can
manufacture a false PASS for code that is genuinely broken.** The stub made
`load_cache` succeed in a context where the real function cannot.

## Solution

Two changes, one for each contributing fact.

**Remove the dependency where it was not needed.** A preflight must not require
more environment than the verb it guards. The schema resolve now bypasses the
on-disk cache entirely:

```python
# Deliberately resolved WITHOUT the on-disk cache: this is a preflight, and it
# must not depend on Git's common directory being resolvable.
resolve_schema(board, ctx, runner, {})
```

The cost is one extra `field-list` call on a verb that already issues N issue
creates — a fair price for a precondition that cannot half-write.

**Make the patches self-restoring** so the masking mechanism cannot recur:

```python
_real_load, _real_save = lb.load_cache, lb.save_cache
self.addCleanup(lambda: setattr(lb, "load_cache", _real_load))
self.addCleanup(lambda: setattr(lb, "save_cache", _real_save))
lb.load_cache = lambda _ctx: {}
lb.save_cache = lambda _ctx, _cache: None
```

## Verification

Reproduce CI's ordering locally — this is the command that matters, because it
is the one CI runs:

```bash
python3 -m unittest discover -s plugins/agentic-engineering/tests -p '*_test.py'
```

Expected: `Ran 581 tests ... OK`. Before the fix this command failed eight
`DecomposeVerbTest` cases locally while `pytest` on the same tree passed, which
is itself the cheapest way to confirm an ordering dependency exists.

Both runners must agree:

```bash
python3 -m pytest plugins/agentic-engineering/tests/ -q
```

## Reusable principles

- **Run the gate the way CI runs it before claiming green.** A different local
  runner is a different test suite. Where CI's command is known, prefer it for
  the final check; a passing run under another runner is supporting evidence,
  not the gate. This repository's Python gate is `unittest discover`.
- **Never mutate imported-module globals in `setUp` without `addCleanup`.**
  Test isolation is not only about the test that patches — it is about every
  test that runs afterward in the same process.
- **Suspect ordering when local and CI disagree on "the same tests."** Before
  hunting environment differences, ask what ran *before* the failing test in
  each place.
- **A precondition must not need more environment than the operation it
  guards.** Preflight checks run early precisely so they can run cheaply; giving
  one an I/O dependency the guarded verb's own tests cannot satisfy is a signal
  the check is reaching too far.
- **A green suite that depends on collection order is not a green suite.** If
  reordering changes the result, the tests encode state, not behavior.

## See also

- [Recorded fixtures must be load-bearing](recorded-fixtures-must-be-load-bearing.md)
- [Grep acceptance checks and subset fixtures give false confidence](grep-acceptance-checks-and-subset-fixtures-give-false-confidence.md)
  — the same family of defect: a check that cannot distinguish fix-present from
  fix-absent.
