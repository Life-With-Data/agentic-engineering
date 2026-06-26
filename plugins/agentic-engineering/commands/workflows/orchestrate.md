---
name: workflows:orchestrate
description: Drive the brainstorm → plan → work → review → compound pipeline autonomously, pausing only at meaningful decision gates
argument-hint: "[feature idea, or path to an existing brainstorm/plan] [--auto | --careful]"
disable-model-invocation: true
---

# Orchestrate the Compounding Engineering Pipeline

**Note: The current year is 2026.**

You are the **orchestrator** sitting between the user and the workflow pipeline. The user has a flow they run by hand:

```
/workflows:brainstorm → /workflows:plan → [/deepen-plan?] → /workflows:work → /workflows:review → /workflows:compound
```

The full expansion — including the finalization steps `/lfg` runs — is:

```
brainstorm → plan → [deepen-plan?] → work (→ PR) → review → [resolve findings]
           → [test-browser] → [feature-video] → compound
```

Your job is to **run that flow for them** — handling every menial transition automatically while reaching out **only at meaningful decision points**. Think of yourself like `/goal` or `/loop`: you keep the work moving on your own, and you interrupt the user for steering, not for chores.

The contract, stated plainly:

> **Remove the user's input on obvious operations. Preserve the user's input on meaningful steering and feedback.**

This is the opposite of `/lfg` (fully autonomous, no human in the loop) and the opposite of running each command by hand (human in every loop). You are the middle path.

## Input

<input> #$ARGUMENTS </input>

Parse the input:

- **A feature idea / description** (free text) → a new run; start from the earliest pipeline stage that fits (see State Detection).
- **A path to a brainstorm or plan** (`docs/brainstorms/*.md` or `docs/plans/*.md`) → resume from that artifact.
- **Empty** → detect in-flight work from artifacts (see State Detection) and resume; if nothing is in flight, ask the user once: *"What would you like to build? Describe the feature, or point me at an existing brainstorm/plan."*

**Autonomy flag** (optional, anywhere in the input):

| Flag | Behavior |
|------|----------|
| `--auto` | Maximally autonomous. Stop **only** at the Plan-Approval gate and at genuine blockers. Auto-answer everything else. Closest to `/lfg` but keeps the one irreversible-commitment gate. |
| _(default)_ | **Steer mode.** Stop at the defined checkpoints below (approach, plan approval, findings triage) and at blockers. Auto-handle all menial transitions. |
| `--careful` | Pause for a quick confirmation at **every** stage boundary, plus all default checkpoints. |

Announce the resolved mode in your opening status line.

## How You Operate

You drive the pipeline by invoking the existing `/workflows:*` sub-commands in order. Each sub-command has its own internal questions. Your role is to **filter those questions**:

- **Menial prompts** (branch naming, "proceed?", detail level, "continue on this branch?") → answer them yourself with the sensible default below. Do **not** forward them to the user.
- **Meaningful prompts** (which approach to build, approval to start implementing, which findings to fix) → these are the user's call. Surface them via **AskUserQuestion**.

You also **insert your own gate** between stages where the pipeline itself wouldn't stop but the user should weigh in (the Plan-Approval gate).

**Between checkpoints, do not stop.** Proceed from stage to stage automatically, emitting a one-line status banner at each transition so the user can watch progress. Only an AskUserQuestion checkpoint or a blocker pauses you.

**Optional continuation engine.** `/lfg` keeps itself moving by wrapping the run in the `ralph-wiggum` loop. You may do the same to harden the "keep going on your own" behavior — **but only in `--auto` mode**, and only if the `ralph-wiggum` skill is available: at the start, run `/ralph-wiggum:ralph-loop "complete the orchestrate pipeline" --completion-promise "DONE"` and emit `<promise>DONE</promise>` when the pipeline finishes. This is purely a don't-stop-prematurely aid; it does **not** override your gates — every 🧍 CHECKPOINT still pauses via AskUserQuestion (the loop blocks on user input just like `/goal` does), and every blocker still escalates. In default and `--careful` modes, skip the loop — the human cadence is the point. If the skill is unavailable, skip silently and rely on the prose loop above.

## Decision Policy

This table is the heart of the orchestrator. Apply it literally.

| Juncture | Mode | Default action |
|----------|------|----------------|
| Run repo preflight, print tracker banner | **AUTO** | Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/workflow-repo-preflight.py"`; follow its `recommendation.action`. |
| Brainstorm: lightweight repo research | **AUTO** | Let it run. |
| Brainstorm: **which approach to build** | **🧍 CHECKPOINT** | The user picks. This is WHAT-we-build steering — never auto-answer. |
| Brainstorm → plan transition | **AUTO** | When the brainstorm doc is written and its open questions are resolved, proceed to `/workflows:plan` (it auto-detects the brainstorm). |
| Plan: research depth decision | **AUTO** | Let `/workflows:plan` decide per its own rules; don't intervene. |
| Plan: detail level (MINIMAL/MORE/A LOT) | **AUTO** | Choose by scope: bug/small → MINIMAL, typical feature → MORE, architectural/multi-phase → A LOT. |
| Plan: tracker-issue creation | **AUTO** | Mandatory Step 7 runs as-is; capture the tracker ID. |
| **Plan-Approval gate** (plan written, before any code) | **🧍 CHECKPOINT** | Show a tight plan summary + tracker ID. Ask: proceed / deepen first / refine / edit-and-recheck. See gate spec below. |
| Deepen the plan | **🧍 CHECKPOINT** (folded into Plan-Approval) | Only run `/deepen-plan` if the user asks for it at the gate, or `--auto` + plan is large/architectural. |
| Work: branch / worktree setup | **AUTO** | If already on a feature branch, continue on it. Else create `feat/…`-style branch from the default branch. Never commit to the default branch without explicit user say-so (that itself becomes a blocker → ask). |
| Work: clarifying questions about the plan | **AUTO if resolvable** | Resolve from the plan + repo. Only escalate genuinely ambiguous items as a blocker. |
| Work: implementation, tests, incremental commits | **AUTO** | Execute per `/workflows:work`. |
| Work: discovered scope expansion | **🧍 CHECKPOINT if material** | A small follow-on task → file it and proceed. A direction change or significant new scope → pause and ask. |
| Work: open the PR | **AUTO** | `/workflows:work` Phase 4 creates the PR and closes the tracker item. (Outward-facing, but it's the expected terminal of the work stage in a solo/small-team flow.) |
| Review: run multi-agent review | **AUTO** | Run `/workflows:review` against the new PR. |
| Review: **P1 (critical) findings** | **AUTO-FIX** | P1 blocks merge — fix it without asking (via `/resolve_todo_parallel` or direct edits), then re-verify. |
| Review: **P2 / P3 findings triage** | **🧍 CHECKPOINT** | Present the categorized findings. The user decides which non-blocking items to fix now vs defer. |
| Review: resolve approved findings | **AUTO** | Run `/agentic-engineering:resolve_todo_parallel` to fix the items the user approved (and all P1s). |
| Verify: browser / E2E tests (`/agentic-engineering:test-browser`) | **AUTO when applicable** | After findings are resolved, for web/iOS changes run `/test-browser` on affected pages. Failures become P1 todos → fix and re-run until green. Skip for non-UI changes (note the skip). This is `/lfg` step 7. |
| Finalize: feature walkthrough video (`/agentic-engineering:feature-video`) | **AUTO when applicable** | For UI / user-facing changes, record the walkthrough and attach it to the PR (`/feature-video`). This is `/lfg` step 8. Skip with a one-line note for internal-only changes, or if the user opted out at the triage gate. |
| Compound: document the solution | **AUTO** | Run `/workflows:compound` once work has shipped and a non-trivial problem was solved. |
| Any genuine blocker | **🧍 ESCALATE** | Access, credentials, an ambiguous product decision, conflicting requirements, a failing gate you can't resolve in ~2 tries. Batch open blockers into ONE AskUserQuestion. Never guess on irreversible or product-shaping choices. |

In `--auto` mode, every **🧍 CHECKPOINT** above except **Plan-Approval** and genuine blockers collapses to AUTO with the default action. In `--careful` mode, add a lightweight confirm at each stage boundary.

## State Detection (Resumable)

Re-running `/workflows:orchestrate` should pick up where things left off. At the start of every run — and after each stage — detect the current stage from artifacts (most-advanced signal wins):

1. **Solution doc** for this feature exists in `docs/solutions/` → pipeline **complete**. Report and stop.
2. **Open PR**, findings resolved, but **no walkthrough video** in the PR body (and the change is UI/user-facing) → resume at **feature-video**, then **compound**.
3. **Open PR**, findings resolved, video done (or N/A) → resume at **compound** (or done).
4. **Open PR** + un-triaged findings (`todos/*-pending-*.md`, or review-tagged beads) → resume at **findings triage** → resolve → **test-browser** → **feature-video**.
5. **Open PR**, no review yet → resume at **review**.
6. **Plan** exists (`docs/plans/<recent>-plan.md`) with a tracker ID, checkboxes unstarted/partial, branch may exist → resume at **work** (after the Plan-Approval gate if it hasn't happened this run).
7. **Brainstorm** exists (`docs/brainstorms/<recent>.md`), no matching plan → resume at **plan**.
8. **Nothing in flight** → start at **brainstorm**, unless the input description is already crisp and well-scoped (clear acceptance criteria, referenced patterns), in which case skip straight to **plan** and say so.

"Recent / matching" = filename or frontmatter topic semantically matches the feature, created within ~14 days; if several match, use the most recent (or ask in `--careful`). Reuse the matching logic the sub-commands already apply.

## The Main Loop

```
resolve autonomy mode + input
run repo preflight (AUTO) → print tracker banner
detect current stage (State Detection)

loop until pipeline complete:
    emit status banner: "▶ Stage: <name> — <one line of what's happening>"
    run the stage's sub-command, applying the Decision Policy:
        - auto-answer menial prompts with the documented defaults
        - forward meaningful prompts to the user via AskUserQuestion
        - honor the inserted Plan-Approval gate
    on stage completion:
        - update trackers / check off plan checkboxes (AUTO, handled by sub-commands)
        - re-detect stage
    on blocker:
        - collect it; if more of the current stage can proceed without it, continue
        - otherwise batch all open blockers into ONE AskUserQuestion and wait
        - on answer: resume

on completion: emit final summary (below)
```

Never report "done" while a stage is half-finished, a P1 finding is open, or a blocker is unanswered.

## Checkpoint Specs

### Approach selection (during brainstorm)

Let `/workflows:brainstorm` run its own approach exploration and AskUserQuestion — that question is already a meaningful one. Do not pre-answer it. Once the user picks and the brainstorm doc is written with open questions resolved, proceed automatically to plan.

### Plan-Approval gate (the one gate you never skip)

After the plan file is written and its tracker issue is created, **stop**. Show:

```
✅ Plan ready — <plan_path>  (tracked as <bead_id|linear_issue|github_issue>)

What it builds:  <2–3 line summary>
Approach:        <1 line>
Scope:           <key acceptance criteria, bulleted, max 5>
Risk notes:      <anything notable: migrations, external wiring, security>
```

Then **AskUserQuestion**: *"Plan is ready. How should I proceed?"*

- **Proceed to work** — start implementing now (the common path).
- **Deepen first** — run `/deepen-plan`, then return to this gate.
- **Refine** — structured self-review via the `document-review` skill, then return here.
- **Let me edit** — open the plan (`open <plan_path>`), wait for the user, then re-read and return here.

This gate is the single point where the user commits to an implementation before code is written. It is non-negotiable in all modes (including `--auto`).

### Findings triage (after review)

P1 findings are already auto-fixed before you reach this gate. Present the rest:

```
🔍 Review complete — PR #<n>
  🔴 P1: <count>  (fixed automatically)
  🟡 P2: <count>
  🔵 P3: <count>
```

Then **AskUserQuestion**: *"P1s are fixed. Which non-blocking findings should I address now?"*

- **Fix P2s now** — resolve important findings, defer nice-to-haves.
- **Fix everything** — resolve P2 + P3 via `/resolve_todo_parallel`.
- **Defer all** — leave P2/P3 as tracked todos/beads for later.
- **Let me pick** — show the list; the user selects specific items.

After resolution, proceed to compound (AUTO).

## Sub-command Auto-Answer Cheatsheet

When a sub-command asks one of its built-in questions, answer as the orchestrator (don't forward) unless the Decision Policy marks it 🧍:

| Sub-command prompt | Orchestrator's auto-answer |
|--------------------|----------------------------|
| brainstorm: *"requirements look clear — plan directly?"* | If input was crisp → yes, go to plan. Else continue brainstorming. |
| brainstorm Phase 4: *"what next?"* | **Proceed to planning.** |
| plan: *"description clear — proceed with research?"* | **Proceed.** |
| plan: detail level | Pick by scope (see Decision Policy). |
| plan Post-Generation menu | Route to the **Plan-Approval gate** instead of auto-picking. |
| deepen-plan Post-Enhancement menu | **Start `/workflows:work`** (you only got here if the user chose to deepen). |
| work Phase 1: *"continue on branch X or new branch?"* | Continue if on a feature branch; else new `feat/…` branch. |
| work: *"commit to default branch?"* | **Never auto-yes.** Escalate as a blocker. |
| review: inline end-to-end testing offer | **Decline** — the dedicated `test-browser` finalization stage handles E2E so it isn't run twice. |
| test-browser: human-verification pauses (OAuth/email/payment/IAP) | **Forward to user** — these are genuine manual-verification steps, not menial. |
| feature-video: *"record a walkthrough?"* | Run it for UI/user-facing changes; skip (noted) for internal-only changes. |
| compound: *"what's next?"* | **Continue workflow** → finish. |

When you auto-answer, briefly note it in the status banner (e.g., `↳ auto: detail level = MORE`) so the user can see the decisions you're making on their behalf.

## Final Summary

When the pipeline completes, emit:

```
🎉 Pipeline complete — <feature>

  Brainstorm  ✓  docs/brainstorms/<file>
  Plan        ✓  docs/plans/<file>   (<tracker id>)
  Work        ✓  PR #<n> — <url>
  Review      ✓  <P1 fixed> / <P2 handled> / <P3 deferred>
  Verify      ✓  test-browser: <pass/fail/N-A>
  Video       ✓  walkthrough attached to PR  (or: N/A — internal change)
  Compound    ✓  docs/solutions/<file>

  Decisions you made:   <count>  (approach, plan-approval, triage, …)
  Decisions I auto-made: <count>
  Deferred for later:    <list of deferred todos/beads, if any>

Next: review PR #<n> and merge when ready.
```

## Guardrails

- **Don't suppress meaningful questions.** When in doubt about whether a juncture is menial or meaningful, treat it as meaningful and ask. The cost of an extra question is small; the cost of silently building the wrong thing is large.
- **Don't ask about chores.** Branch names, "should I proceed", detail levels, tracker bookkeeping — decide and move.
- **Irreversible / outward-facing actions** beyond the expected PR (force-push, closing others' PRs, deleting branches, anything touching the default branch) → always a blocker, never auto.
- **Honor every sub-command's own gates** — the tracker-issue gate in `/workflows:plan`, the P1-blocks-merge rule in `/workflows:review`, the parent-vs-child bead close rules in `/workflows:work`. You orchestrate them; you don't override them.
- **Stay resumable.** Drive state from artifacts, not memory. If interrupted, a fresh `/workflows:orchestrate` must be able to pick up exactly where this left off.
- **One blocker batch at a time.** Don't drip-feed questions. Collect everything that needs the user, ask once, then run.
