---
name: wf-development
description: Workflow policy for implementing planned engineering changes, diagnosing root causes, fixing reproduced bugs, refactoring, and building APIs and interfaces. Use when code or configuration must change after grooming. This skill owns implementation sequencing and completion evidence; cross-stage routing belongs to wf-orchestrate and repository mechanics to repository capability targets.
---

# Development workflow

Layer: Workflow policy

Owns: claiming ready work, scope control, and change isolation.

Requires repository capabilities: `repository-overview`, `development-environment`, `test-execution`.

Does not contain: repository build commands, framework-specific setup, infrastructure access, secrets, or cross-stage routing.

## Start here

```bash
python3 <skill-directory>/scripts/repository-context.py \
  --require repository-overview \
  --require development-environment \
  --require test-execution
```

Stop on contract failure; read primary targets first, supporting targets only as needed.

This skill implements one approved work item. It starts only after grooming produced the plan and the item was stamped approved — by a human on every path but `wf-auto`, which holds that approval itself; it never routes tickets, decides delivery posture, or drives other stages — `wf-orchestrate` owns all of that.

## Route the request

- Execute a prepared plan, including parallel independent units: read [workflow work](references/workflows-work.md). Pull-request review threads are out of scope here; `wf-review` owns them.
- Diagnose a reproduced bug, establish root cause, and recover safely: read [debugging and error recovery](references/debugging-and-error-recovery.md). Require `bug-reproduction` and, for production or integration failures, `observability`.
- Work in an isolated checkout: read [git worktree](references/git-worktree.md).
- Design an API or interface: read [API and interface design](references/api-and-interface-design.md).
- Build a frontend: resolve visual direction, typography, and component mechanics from the mapped repository assets and the host's available skill metadata. This plugin's `design-iterator` agent covers iterative visual refinement. Report a missing-capability note when nothing resolves; this workflow does not prescribe aesthetics.
- Add instrumentation while building: read [observability and instrumentation](references/observability-and-instrumentation.md); require `observability` if it needs repository systems.

Load only the selected reference. Framework, language, vendor, and tool-specific
implementation techniques must come from mapped repository assets or separately
installed capabilities; this workflow does not prescribe them.

## Sub-agent delegation

Delegate per-unit stage work to focused sub-agents; the orchestrator retains
verification and every tracker, board, and PR write. Roles, dispatch, model
selection, and the inline fallback:
[sub-agent delegation](../wf-orchestrate/references/subagent-delegation.md).

## Completion contract

Development ends when the change is implemented, repository gates pass, and the implementation evidence is reported. It never declares the work item done: testing, review, and delivery are separate stages that `wf-orchestrate` dispatches after this one returns. When invoked standalone, report completion and name `wf-testing` as the next stage without executing it.

In Project mode, development owns exactly two board transitions, each real only as an observable postcondition: the claim holds only when `--claim <N>` returns proceed (`Status = in_progress` on the board), and development's exit is `--set-status <N> in_review` succeeding at PR open. Sub-issue progress is the `status:*` label track, not board Status; the [work route](references/workflows-work.md) owns that mechanics.

A bug fix enters here only with reproduction evidence from `wf-grooming`. Development owns localization, root cause, and the fix; it must not edit a speculative fix before root cause is established.

## Wrong-layer recovery

Workflow policy wins on process; repository guidance wins on mechanics — consult the mapped repository capability targets for the latter.
