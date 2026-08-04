---
title: "A dedup guard is not a cache: copying a cache's swallow-everything miss rule costs duplicate durable state"
category: logic-errors
tags: [idempotency, receipt, cache, guard, error-handling, decompose, lifecycle-board, ordering, partial-failure, github-issues]
module: plugins/agentic-engineering/scripts/lifecycle_board.py, plugins/agentic-engineering/tests/lifecycle_board_test.py
symptom: "`--decompose` run twice created two complete disjoint GitHub issue sets; the first fix still missed two of the three real incidents because the guard artifact was written last"
root_cause: "A guard artifact was modeled on the file's existing TTL cache — written at the end of the happy path, and treated as absent on every read error — but a cache miss costs one API call while a guard miss costs duplicate durable remote state that only manual cleanup can undo"
---

# A Dedup Guard Is Not a Cache

## Problem

`lifecycle_board.py --decompose` creates a parent GitHub issue, its sub-issues, and their
dependency edges from a model-authored JSON spec. It was the only verb that creates durable
structure from a **non-issue-keyed** input: every other effectful verb is keyed by an issue
number and writes a fixed target state, so a repeat invocation converges. `--decompose` had no
memory of prior invocations, so two identical runs produced two complete, disjoint issue sets.

Three real occurrences, across two repositories:

| Trigger | Result |
|---|---|
| Output piped through `tail -20` cut off the `parent` field, so the agent re-ran the verb to read what it had truncated | `bluestar-intel` #270-#274 duplicating #265-#269 |
| The step-5b posture `label create` raised HTTP 422 after steps 1-4 had landed; recovery re-run | `agent-leverage` #2171-#2174 duplicating #2175-#2178 |
| The same step-5b raise, during this repository's own grooming of #349 | None — the re-run was deliberately withheld |

The fix was a local receipt under Git's common directory, keyed by a hash of the invocation and
checked before the first GitHub mutation.

## Investigation path, and the two misleading signals

**Misleading signal 1: the incident report named truncated stdout as the cause.** It was the
cause of occurrence 1 only. Grooming initially designed the receipt around it — write the
complete result at the end of the verb, so lost output is recoverable from disk. That design is
correct for occurrence 1 and useless for occurrences 2 and 3, which is only visible by reading
what the tail of the verb actually does:

```python
# step 5 / 5b, AFTER the parent, sub-issues, edges and the planned stamp exist
apply_complexity_label(...)   # raises BoardError("label_write_failed") on a failed gh label create
apply_posture_label(...)      # same
```

A receipt written after those raises is never written at all. The recovery re-run duplicates
everything — unchanged by the "fix".

**Misleading signal 2: the file's own TTL cache was sitting right there as a precedent.**
`load_cache` in the same module swallows every read error and returns a miss, with an entirely
sound rationale. The first implementation copied that reasoning verbatim into the receipt reader:

> A corrupt receipt is a MISS, not an error: re-creating is recoverable, and refusing to
> decompose because a local cache file rotted is not.

The first clause is right and the justification is inverted. It reads as prudent defensiveness,
which is why it survived into a merged design.

## Root cause

Two distinct mistakes, both from treating a **guard** as if it were a **cache**:

1. **Write position.** A cache is written when the value is known — at the end. A guard must
   exist from the moment the thing it guards against becomes possible. Here that is the instant
   durable remote structure exists, which is *before* every write that can raise.

2. **Miss cost.** A cache miss costs one recomputation: swallow every read error and move on. A
   dedup-guard miss costs a duplicate set of real GitHub issues, requiring manual closing and
   unlinking, and producing spurious board stamps via the item-closed automation. The costs
   differ by orders of magnitude, so the same error-handling rule cannot serve both.

A third, subtler instance of the same confusion: the receipt filename carried only the first 16
hex characters of the digest, and the payload did not record the key at all. For a cache keyed by
path that is fine. For a guard it means **nothing on the hit path proves the artifact describes
this invocation** — a receipt copied between clones would be replayed as this spec's own result,
silently suppressing a real decomposition and reporting another one's issue numbers. That failure
is worse than the duplication bug: a missing issue set plus a confident wrong answer.

## Solution

**Write the guard twice, positioned by risk rather than by data availability.**

- A *guard receipt* immediately after dependency wiring, carrying the durable structure plus
  `partial: true`, before `set_status` and the advisory label writes.
- An *overwrite* with the complete result and `partial: false` after the final step.

Both through `_atomic_private_write`, so a crash between them leaves a valid guard receipt rather
than a truncated file, and a failed overwrite still leaves the re-run guarded.

**Split "absent" from "present but unusable."** Absent is the only routine miss and stays silent.
Unreadable, unparseable, and wrong-shape remain misses — refusing to decompose because a local
file rotted really would be worse — but they report through a dedicated `receipt_anomaly` field
and a stderr warning. Kept separate from `receipt_error` deliberately: the run still writes a
fresh receipt and ends up guarded, so folding the two together would report
`receipt_written: false` for a receipt that was written.

**Record the key in the payload and require it to match on a hit**, since the truncated filename
cannot identify an invocation on its own.

**Announce an unguarded run on stderr the moment it is known.** The return value only reaches a
caller if the verb returns; every raise between the guard write and that return discards it — and
a raise after the issue set exists is precisely when the operator must know whether a retry is
safe. Without this, a failed guard write and a successful one produce byte-identical output on
the exact path the guard exists to cover.

## Verification

Ordering is the load-bearing property, so the test asserts it directly rather than asserting that
a receipt exists. It injects `set_status` and reads the receipt from disk *inside* that call:

```python
def fake_set_status(parent, stage, ctx, run, force=False):
    at_set_status["receipt"] = lb.read_decompose_receipt(path)[0]
    ...
self.assertIsNotNone(guard, "guard receipt must precede the set_status write")
```

An end-of-run receipt cannot satisfy this. Confirmed by mutation — moving the guard-write block
to immediately *after* `set_status` still fails it, which the weaker "a receipt exists"
assertion would not catch.

Seven further mutations, all killed: key drops `spec` / drops `parent` / drops `slug`, hex-key
gate disabled, hit-path key check removed, key dropped from the final result, anomaly not
reported. Before the review, the first three survived the entire suite.

```bash
python3 -m unittest discover -s plugins/agentic-engineering/tests -p '*_test.py'
bun test && bun run typecheck
bun run skills:sync && bun run skills:check
```

## Reusable principle

**Before copying an error-handling or write-position rule from a nearby artifact, compare what a
miss costs, not what the two artifacts look like.** A cache, a lock, a receipt, and an
idempotency token are all "a file we check before doing work" and are not interchangeable:

- **Write position** follows the risk window, not data availability. If the artifact prevents a
  repeat of side effects, it must exist before the first side effect is complete — even when the
  full result is not yet known. Splitting into a provisional write and a final overwrite is
  cheaper than the duplicate it prevents.
- **Miss cost sets the error policy.** Recoverable-and-cheap earns a silent swallow.
  Expensive-and-manual earns a loud miss. Both can still be non-fatal; "non-fatal" and "silent"
  are separate decisions, and conflating them is what hides the failure.
- **A guard must identify what it guards.** A truncated or path-derived key with no recorded
  identity cannot distinguish "this ran before" from "something else ran before."
- **Anything that only reaches the caller through a successful return is invisible on the failure
  path.** If the information matters most when the run fails, emit it when it is discovered.

The general shape: a partial-failure window is created by any sequence of `create durable remote
state` → `then do more writes that can fail`. Ask what a retry does after each raise in that
sequence.

## Links

- Issue [#349](https://github.com/Life-With-Data/agentic-engineering/issues/349) — analysis,
  reproduction, occurrences table, rejected alternatives
- Sub-issues [#355](https://github.com/Life-With-Data/agentic-engineering/issues/355) (engine),
  [#356](https://github.com/Life-With-Data/agentic-engineering/issues/356) (prose)
- PR [#370](https://github.com/Life-With-Data/agentic-engineering/pull/370)
- [#369](https://github.com/Life-With-Data/agentic-engineering/issues/369) — the advisory writes
  whose hard failure triggers the retry in the first place
- [#386](https://github.com/Life-With-Data/agentic-engineering/issues/386) — deferred P3 hardening
- [Idempotent backfill and recorded-config design](idempotent-backfill-and-recorded-config-design.md)
  — the converging-verb pattern every other effectful verb already follows
- [Tests that shell out to git must scrub GIT_*](../testing-patterns/tests-shelling-out-to-git-must-scrub-git-env-vars.md)
  — surfaced while testing this change
