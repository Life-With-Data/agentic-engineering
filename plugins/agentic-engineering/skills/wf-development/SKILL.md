---
name: wf-development
description: Workflow policy for implementing planned engineering changes, diagnosing root causes, fixing reproduced bugs, refactoring, and building APIs, interfaces, or agent-native systems. Use when code or configuration must change after grooming, including end-to-end implementation orchestration. This skill owns development sequencing and handoffs; repository mechanics come from repository capability targets.
---

# Development workflow

Layer: Workflow policy

Owns: claiming ready work, implementation sequencing, scope control, change isolation, sub-agent delegation and per-dispatch model selection, and handoffs to testing, review, and delivery.

Requires repository capabilities: `repository-overview`, `development-environment`, `test-execution`.

Does not contain: repository build commands, framework-specific setup, infrastructure access, or secrets.

## Start here

Resolve `<skill-directory>` to the directory containing this `SKILL.md`. All
scripts used by this workflow are bundled there; do not resolve them through a
plugin root.

```bash
python3 <skill-directory>/scripts/repository-context.py \
  --require repository-overview \
  --require development-environment \
  --require test-execution
```

Stop on contract failure. Read each required capability's primary target, then supporting targets only when needed, before changing files.

## Route the request

- Execute a prepared plan: read [workflow work](references/workflows-work.md).
- Delegate lifecycle work to sub-agents while orchestrating and validating: read [sub-agent delegation](references/subagent-delegation.md).
- Diagnose a reproduced bug, establish root cause, and recover safely: read [debugging and error recovery](references/debugging-and-error-recovery.md). Require `bug-reproduction` and, for production or integration failures, `observability`.
- Drive the complete cross-stage pipeline: read [workflow orchestrate](references/workflows-orchestrate.md), loading other `wf-*` skills at their boundaries.
- Work in an isolated checkout: read [git worktree](references/git-worktree.md).
- Resolve independent implementation items: read [resolve parallel](references/resolve-parallel.md).
- Design an API or interface: read [API and interface design](references/api-and-interface-design.md).
- Build agent-native software: read [agent-native architecture](references/agent-native-architecture.md).
- Build a frontend: read [frontend design](references/frontend-design.md).
- Add instrumentation while building: read [observability and instrumentation](references/observability-and-instrumentation.md); require `observability` if it needs repository systems.

Load only the selected reference. Framework, language, vendor, and tool-specific
implementation techniques must come from mapped repository assets or separately
installed capabilities; this workflow does not prescribe them.

## Sub-agent delegation

The session's default agent is the orchestrator and validator for this
workflow, not the worker. Delegate each planned implementation unit and each
isolated diagnosis experiment to a focused sub-agent; the orchestrator keeps
decomposition, diff verification, gate reruns, and every tracker write. Choose
each sub-agent's model by the complexity of its unit — economy tiers for
mechanical work, standard tiers for well-scoped implementation, the strongest
available tier for ambiguous or high-blast-radius work — per
[sub-agent delegation](references/subagent-delegation.md). Hosts without a
sub-agent mechanism run the same sequence inline.

## Quality handoffs

Development does not declare completion by itself:

1. `wf-testing` proves behavior.
2. `wf-review` evaluates the change and its risks.
3. `wf-delivery` owns PR, merge, and deployment actions.

For bug fixes, start with `wf-grooming`; it hands off only after reproduction evidence and an actionable bug report exist. Development owns localization, root cause, and the fix. It must not edit a speculative fix before root cause is established.

## Wrong-layer recovery

When a development reference guesses a repository command or convention, stop and use the corresponding repository capability targets instead. Workflow policy wins on sequencing; repository guidance wins on mechanics.
