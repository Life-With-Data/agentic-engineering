---
title: "Recorded fixtures that no test loads are false confidence — wire replay tests or delete them"
category: testing-patterns
tags: [fixtures, mocks, gh-cli, json-shape, false-confidence]
module: lifecycle-board
symptom: "All 123 tests green while the flagship verb refused 100% of real inputs"
root_cause: "Hand-written mocks encoded a guessed JSON shape (list) while the recorded fixture held the real one (dict) — and nothing loaded the fixture"
---

# Recorded Fixtures Must Be Load-Bearing

## Problem

The lifecycle claim verb parsed `gh issue view --json blockedBy` as a list:

```python
blocked_by_count = len(json.loads(out).get("blockedBy", []))   # gh emits a DICT
```

gh actually emits `{"blockedBy": {"nodes": [...], "totalCount": N}}` — so `len()` of the dict returned 2 **always**, and `--claim` refused every issue as blocked. The full suite (123 tests) stayed green because the unit tests fed hand-written mocks with the guessed shape. The bitter part: a fixture with the **correct** shape had been recorded into `tests/fixtures/gh/` by the recording script — but no test loaded any fixture. The recording infrastructure existed purely as documentation.

Found only by an integration reviewer executing the verb against the live board.

## Solution

1. **Parse the shape the platform emits** (here: `(d.get("blockedBy") or {}).get("totalCount", 0)`) — and prefer folding the read into an existing GraphQL query over a second CLI call with a different shape.
2. **Wire a fixture-replay test class**: every recorded fixture is fed through its real consumer (`parse_field_list`, the blockedBy parse, the stateReason switch). A future gh JSON change then surfaces as a fixture-vs-parser failure, not a silent lie.
3. **Live-execute flagship verbs once** before shipping — the claim protocol was the design's centerpiece and had zero non-mock coverage.

## Prevention

- Rule of thumb: *if you record fixtures, a test must fail when a fixture and its parser disagree.* Recorded-but-unloaded fixtures are worse than none — they read as coverage.
- The repo now enforces this: `FixtureReplayTest` in `lifecycle_board_test.py`, plus argv-validating fakes so mocks can't drift from the call contract silently, plus the tier-3 smoke workflow re-exercising the real surface weekly.

## Resources

- Fixed in: PR #44 review cycle (issue found by integration-boundary review, live repro on board #5)
- The plan's test-strategy section predicted exactly this failure mode ("hand-written mock JSON prohibited") — the prohibition was written, the enforcement wasn't. Both are needed.
