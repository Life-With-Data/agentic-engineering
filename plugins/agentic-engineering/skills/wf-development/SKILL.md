---
name: wf-development
description: Workflow policy to implement, diagnose, refactor, and verify engineering changes. Use when code or configuration must change. Start from a clear request or groomed item; do not require a separate planning ceremony for small, well-scoped work.
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

Implement one clear work item. In Project mode, claim only a human-approved
`ready_for_work` item; route `planned` items back for approval. Ask only when
scope or an expensive product decision is genuinely unresolved.

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

Use sub-agents only for independent parallel units or a valuable independent
check. Small or tightly coupled changes stay inline.

## Completion contract

Development ends when the change is implemented and proportionate verification
passes. Run focused tests while iterating and the repository-required gate before
delivery. A separate testing or review stage is optional unless risk or the user
calls for it.

In Project mode, development owns exactly two board transitions, each real only as an observable postcondition: the claim holds only when `--claim <N>` returns proceed (`Status = in_progress` on the board), and development's exit is `--set-status <N> in_review` succeeding at PR open. Sub-issue progress is the `status:*` label track, not board Status; the [work route](references/workflows-work.md) owns that mechanics.

For a bug, reproduce when practical. If reproduction is unavailable, say what is
unknown and prefer instrumentation or a narrow, evidence-backed fix over guessing.

## Wrong-layer recovery

Workflow policy wins on process; repository guidance wins on mechanics — consult the mapped repository capability targets for the latter.
