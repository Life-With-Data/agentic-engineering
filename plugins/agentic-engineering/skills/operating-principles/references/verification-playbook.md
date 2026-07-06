# Verification Playbook

Concrete verification procedures by artifact type. The governing principle everywhere: **verify through a channel independent of the one that produced the work.** The mental model that wrote the bug will approve the bug on re-read.

## Channel strength ranking

1. **Execute** — run tests, run the program on a concrete input, typecheck, lint. Machine judgment; strongest.
2. **Trace** — hand-walk a concrete input through the changed path, computing actual values. Catches logic the type system cannot.
3. **Hostile diff read** — read the full diff as a reviewer whose job is to find what broke, not to confirm intent.
4. **Pattern sweep** — grep for siblings of any bug found.

Prefer the strongest channel available; always use at least one channel that is not "re-read the code".

## Universal disciplines

### Make it fail once

A check never seen failing verifies nothing. For every new test: break the code under test (or invert the assertion), run, watch it fail, restore, watch it pass. This proves simultaneously that the test bites and that the edited file is actually on the executed path. Skipping this step is the single most common source of false confidence.

### Confirm the green is real

Before trusting a passing run:

- The tests **ran** — check the count, not the exit code. "0 tests, 0 failures" is green.
- Filters did not exclude the relevant tests (focused specs, `-k` patterns, tag filters, skipped suites).
- The build is not stale or cached — a deliberately introduced syntax error should break it (then revert).
- Mocks are not swallowing the path under test — the code path being verified must execute real logic somewhere.

### Negative space

Enumerate what must NOT have changed, then check it:

- All callers of every modified function/class (grep for them — do not recall them). The behavior contract holds for each.
- Adjacent tests still pass — run the surrounding suite, not just the new test.
- Public surface unchanged unless the task says otherwise: exports, API responses, CLI flags, serialized shapes, schema.

## Per-artifact checklists

### Bug fix

1. Reproduce first — see the bug fail before touching code. A fix for an unreproduced bug is a guess.
2. Fix; watch the reproduction pass.
3. Add the reproduction as a regression test (it has now been seen failing — the make-it-fail-once discipline comes free).
4. Sibling sweep: the same wrong pattern usually exists elsewhere; grep for it.
5. Check callers of the changed code for behavioral collateral.

### New feature

1. Execute the Phase-1 acceptance check end-to-end with realistic data — at the level of user intent, not code internals. "The function returns the right value" is not "the feature works".
2. Run the boundary set: empty / one / many / max / duplicate / malformed / unauthorized.
3. Verify error paths do what the spec implies — rejecting loudly vs. degrading quietly is a decision, not an accident.

### Refactor

1. Establish the baseline first: run the full suite before the change; record the exact failure set (it may not be empty).
2. After: identical failure set. Any delta is a behavior change wearing a refactor costume.
3. Public surface diff is empty: exports, signatures, serialized shapes.
4. For performance-motivated refactors: measure before and after; otherwise the motivation is unverified.

### Migration / data change

1. Dry-run against production-shaped data — realistic volume, realistic nulls and duplicates — not the pristine dev fixture.
2. Compare row counts / checksums before and after.
3. The rollback path is **tested**, not just written.
4. Irreversibility check: find the point of no return in the migration and checkpoint before it.

### Config / infra

1. Apply in the lowest environment first; diff the *effective* config (what the system actually loaded), not the file.
2. Write down the blast radius before applying: what reads this value, what restarts, what invalidates.

## Reporting language

Map every claim in the final report to one of three labels:

| Label | Meaning | Example |
|-------|---------|---------|
| Verified | Executed; output observed in this session | "Suite: 142 passed, 0 failed (output above)" |
| Checked | Read or hand-traced; not executed | "Traced the empty-input path; returns `[]` as intended" |
| Assumed | Not examined | "Assumed staging config mirrors prod — not verified" |

"Should work", "looks correct", and "I believe" are the Assumed row wearing better clothes. Either upgrade the claim by verifying, or label it honestly.
