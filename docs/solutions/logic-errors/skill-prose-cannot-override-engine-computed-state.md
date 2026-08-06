---
title: Skill prose cannot override engine-computed state
category: logic-errors
tags: [skills, lifecycle-board, posture, workflow-policy]
created: 2026-08-06
severity: high
component: plugins/agentic-engineering/skills
---

# Skill prose cannot override engine-computed state

## Problem

`wf-auto` (#407) is the maximally autonomous route: no structural gates. Its
first draft handled supervision labels by telling the agent to ignore them:

> **`posture:standard`, or any other `posture:*` label**: ignore it.

That reads as sufficient and is not. `resolve_clearance` in
`scripts/lifecycle_board.py` returns `posture: standard` for *any* label in the
`posture:` namespace, and `--groom-verify` fuses that into `hands_off`. The
stages `wf-auto` dispatches — `wf-orchestrate`, then `land-pr` — branch on the
engine's verdict, not on what `wf-auto`'s markdown says. A surviving label
therefore left `hands_off: false` and reinstated plan approval, findings
triage, and the interactive merge `[y/N]`: the exact three gates the route
exists to remove, silently, in the one mode where nobody is watching.

The instruction was not wrong about intent. It was addressed to the wrong
reader — the dispatching agent — when the actual reader was the engine.

## Solution

Change the state, not the documentation about the state:

```bash
gh issue edit <N> --repo <owner/repo> --remove-label posture:standard
```

Strip the label, then re-read `--groom-verify`. Now every downstream consumer
of the verdict — including ones this skill never mentions — sees an autonomous
run, because the fact they read has actually changed.

## Rule

**When a skill needs a behavior that some other component computes, it must
write the input that component reads.** Prose can only direct the agent that
reads it. Anything resolved by a script, a gate verb, or a downstream skill
branching on structured output is unreachable from prose in a different file.

Two questions catch this before it ships:

1. *Who reads this instruction?* If the answer is "the engine" or "a stage I
   dispatch," prose is the wrong instrument.
2. *What is the observable state after this step?* If a subsequent
   `--groom-verify` / `--gate` / status read would return the same value it
   returned before, nothing happened.

The same failure shape appears anywhere policy is expressed twice — once as an
engine computation and once as narrative. The engine wins every time, and the
narrative version fails silently, which is worse than failing loudly.

## Detection

A guardrail test freezes the fix by category in
`tests/workflow-skill-architecture.test.ts` ("the unattended entry point keeps
zero structural gates"): the route must contain a `--remove-label` write, not
merely a claim about labels. Asserting the *write* rather than the *sentence*
is what makes the test able to fail on a revert to prose-only handling — see
`docs/solutions/testing-patterns/grep-acceptance-checks-and-subset-fixtures-give-false-confidence.md`.

## Provenance

Found by a second review pass at the branch head, after an earlier review of an
earlier head had passed. The gap was introduced by a commit written *after* the
first review — which is why review verdicts are bound to the reviewed SHA
(#406) and a re-review at head is not a formality.
