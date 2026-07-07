---
title: "Idempotent backfill + recorded-config design: advisory watermarks, atomic writes, preserve-raw, orthogonal keys"
category: logic-errors
tags: [idempotency, high-water-mark, atomic-write, config, invariants, re-run, projects-v2]
module: lifecycle-board
symptom: "A re-runnable operation with a recorded high-water mark and a committed decision file — where are the silent-corruption and lost-decision traps?"
root_cause: "Watermarks over gappy id spaces over-promise; in-place config writes aren't crash-safe; preserve-on-rerun keyed on validity erases malformed intent; multi-key config read non-orthogonally cross-contaminates"
---

# Four Design Traps in Idempotent Backfill + Recorded-Config

Four correctness lessons a 3-agent review surfaced on PR #66 (issue #64 — making the repo→board binding an explicit recorded decision, with a one-time idempotent issue backfill). None was a crash in the happy path; each was a silent-corruption or lost-intent trap in a re-run/edge path. Companion to [[gh-projects-v2-backfill-item-list-shapes]].

## 1. A high-water mark over a gappy id space is ADVISORY, not a guarantee

**Trap.** The backfill records `github_project_backfilled_through: N` (highest issue confirmed on the board), and the comments/tests asserted the invariant *"everything ≤ N is on the board."* **False.** Issue numbers are gappy — PRs and closed issues consume numbers in the same sequence — so a contiguous-prefix mark over the *open-issue* list can sit above issues that legitimately aren't on the board (closed, or later reopened). Two reviewers flagged this as a P1 invariant violation.

**Why it was harmless anyway — and the real fix.** The mark is **never read to skip work.** `verb_backfill` always re-enumerates the full open-vs-board set difference and adds whatever's missing (idempotent), so running it is always complete; the mark only decides whether setup *re-offers* the prompt. The fix was to make the comments/tests **honest** (advisory watermark, gates re-offer only), not to change behavior.

**Lesson.** When a "high-water mark" rides a gappy id space, keep it advisory and keep the operation self-correcting via **full re-enumeration**. Never build gap-skipping logic on such a mark, and never document it as a completeness guarantee — a future reader will trust the comment and build the unsafe optimization.

## 2. Load-bearing committed files need atomic writes

**Trap.** `write_config_keys` did `read_text()` then `write_text()` (truncate-in-place) on `agentic-engineering.md` — the committed board identity that **all** lifecycle resolution depends on. A crash / `SIGKILL` / `ENOSPC` between truncate and full flush leaves it truncated or empty → `read_board_config` returns `None` → the whole board silently "disappears."

**Fix.** Write to a temp file, then `os.replace(tmp, path)` (atomic on POSIX/NTFS). The sibling `save_cache` already had this pattern **for the throwaway cache** — the far more critical committed file was the one missing it. Note the asymmetry: `save_cache` swallows `OSError` (a cache is an optimization); the config writer must **not** swallow it (a durable decision must fail loudly if it can't be written).

**Lesson.** Audit every load-bearing *committed* file for the tmp+rename atomic pattern. "One logical write" (both keys in one dict) is not the same as "one crash-safe physical write."

## 3. Preserve-on-rerun must key on the RAW value, not the validated one

**Trap.** Bootstrap's preserve-on-rerun read the *validated* enum: `read_binding_config(ctx).forward_binding`. `read_binding_config` degrades an unrecognized value (a typo like `auto_add`) to `None`. So on re-run: typo → `None` → fell through to the default → `write_committed_config` **overwrote the operator's malformed-but-intentional value with the default** — the exact erasure the preservation exists to prevent.

**Fix.** Key off the raw recorded value (`forward_raw`), defaulting only when it is genuinely empty. The doctor then WARNs on the malformed value instead of it silently vanishing.

**Lesson.** "Preserve on re-run" logic must branch on **presence of a raw value**, not on validity. Validating-then-defaulting destroys exactly the intent you meant to protect. Validation and preservation are different questions — don't collapse them.

## 4. Orthogonal config keys must be read orthogonally

**Trap.** `read_binding_config` scanned sources (`.local` then committed) and returned the **first source carrying *either* key** — for *both* keys. So a `.local` override that set only the forward binding masked the committed backfill marker (returned `None`), which in turn made the backfill misread `prior` and spuriously re-write the marker.

**Fix.** Resolve **each key independently**, each with its own source precedence (first source that has *that* key wins).

**Lesson.** If two config values are documented as "orthogonal / independent," they must be *read* independently. A single first-hit-wins scan couples them silently — the coupling only bites when the two keys live in different layers (the exact `.local`-override testing path).

## Prevention checklist for the next re-runnable + recorded-decision feature

- [ ] Is any recorded "mark/watermark" ever *read to skip work*? If so, prove the invariant over the actual (possibly gappy) id space; otherwise document it as advisory and re-enumerate fully.
- [ ] Does every committed/durable file write go through tmp+`os.replace` (and NOT swallow `OSError`)?
- [ ] Does preserve-on-rerun branch on *raw presence*, not *validated value*?
- [ ] Are independent config keys resolved independently, or does one scan return both?

## References

- PR #66, issue #64. Verified by 3 parallel review agents (Python correctness, integration boundary, data integrity); insights 1 and 3 were the two ship-blockers.
- gh CLI shapes: [[gh-projects-v2-backfill-item-list-shapes]]. Fixture discipline: [[recorded-fixtures-must-be-load-bearing]].
