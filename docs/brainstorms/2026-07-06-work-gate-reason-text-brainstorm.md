---
date: 2026-07-06
topic: work-gate-reason-text
github_issue: 46
---

# Work Gate Reason Text Misstates the Stage

## What We're Building

A one-line correctness fix in `lifecycle_board.evaluate_gate`'s `work` branch: when the gate routes to plan because no join-keyed plan doc exists, the reason string is hard-coded to "Status says planned…" even when the actual board stage is something else (e.g. `in_progress` — observed live during the PR #44 end-to-end verification, where a claimed-but-unplanned scratch issue produced `stage: in_progress` alongside a reason claiming `planned`).

The reason string is part of the gate's user-facing contract — commands echo it verbatim when they STOP, so a wrong stage in the prose sends the human chasing the wrong state.

## Why This Approach

Interpolate the actual `stage` into the reason (`f"Status is {stage} but no plan doc…"`). Rejected alternative: restructuring the gate to emit structured reason parts — YAGNI; the verdict/route/stage fields are already structured, only the prose lags.

## Key Decisions

- **Fix the string, not the shape**: verdict (`route_to_plan`) and behavior are correct; only the prose misreports.
- **Assert lightly in tests**: the tier-1 gate test gains a check that the reason names the actual stage — prose stays free to evolve, the stage mention is pinned.

## Resolved Questions

- Does any other gate branch hard-code a stage name in its reason? Swept `evaluate_gate`: the other reasons either interpolate (`f"already {stage}"`) or don't name a stage. This is the only offender.

## Next Steps

→ `/workflows:plan`
