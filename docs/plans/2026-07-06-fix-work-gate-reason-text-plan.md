---
title: "fix: work gate reason text misstates the stage when plan doc is missing"
type: fix
date: 2026-07-06
origin: docs/brainstorms/2026-07-06-work-gate-reason-text-brainstorm.md
github_issue: 46
---

# fix: Work Gate Reason Text Misstates the Stage

The `work` branch of `lifecycle_board.evaluate_gate` returns `route_to_plan` with a hard-coded reason "Status says planned but no plan doc with this join key exists" whenever the join-keyed plan doc is missing — even when the actual stage is `in_progress` or `in_review`. Observed live during PR #44's end-to-end verification (see brainstorm: docs/brainstorms/2026-07-06-work-gate-reason-text-brainstorm.md). Commands echo the reason verbatim on STOP, so the prose misdirects the human.

## Acceptance Criteria

- [ ] The no-plan-doc reason interpolates the actual `stage` (e.g. "Status is in_progress but no plan doc…")
- [ ] Tier-1 gate test asserts the reason names the actual stage for a non-`planned` case
- [ ] Full python suite green

## Context

Single-line fix in `plugins/agentic-engineering/scripts/lifecycle_board.py` (the `work` branch of `evaluate_gate`) plus one test assertion in `plugins/agentic-engineering/tests/lifecycle_board_test.py`. No other gate branch hard-codes a stage name (swept during brainstorming). No external wiring required.

## Sources

- **Origin brainstorm:** [docs/brainstorms/2026-07-06-work-gate-reason-text-brainstorm.md](../brainstorms/2026-07-06-work-gate-reason-text-brainstorm.md)
- Observed during: PR #44 live E2E (issue #45 scratch run)
