---
name: wf-delivery
description: Workflow policy for CI repair, release preparation, pull requests, merge gates, artifact transfer, deployment handoff, and release communication. Use when work is implemented and must be shipped. This skill owns delivery sequencing; repository commands and credentials come from repository capability targets.
---

# Delivery workflow

Layer: Workflow policy

Owns: preflight and the final pre-merge compounding gate.

Requires repository capabilities: `test-execution`, `delivery`.

Does not contain: CI provider configuration, release commands, production credentials, environment URLs, or rollback mechanics.

## Start here

```bash
python3 <skill-directory>/scripts/repository-context.py \
  --require test-execution \
  --require delivery
```

Require `infrastructure-operations` and `security-and-access` before any deployment or production verification. Stop on contract failure; read primary targets first, supporting targets only as needed.

## Route the request

- Repair CI failures: read [CI workflow issues](references/ci-resolve-workflow-issues.md).
- Prepare or update release notes: read [changelog](references/changelog.md).
- Drive an open PR to merge: read [land PR](references/land-pr.md), passing the PR number and optional `--auto` context.

Documentation-only delivery is routed through `wf-documentation`.
Artifact transports and release-media tooling come from repository capability targets.

## Sub-agent delegation

Delegate per-unit stage work to focused sub-agents; the orchestrator retains
verification and every tracker, board, and PR write. Roles, dispatch, model
selection, and the inline fallback:
[sub-agent delegation](../wf-orchestrate/references/subagent-delegation.md).

## Delivery gates

1. Confirm testing and review evidence exists for the current head; absent evidence is a blocker returned to the caller, never a gate this stage runs itself.
2. Reconcile the branch with its target using repository guidance.
3. Run the repository's delivery checks.
4. Resolve CI and review threads.
5. Create or update the PR with accurate evidence.
6. Immediately before merge, perform the final compounding disposition against
   the current PR head and record its audit evidence. This gate is mandatory
   even when every CI and review signal is already green.
7. Merge only when policy and repository gates pass.
8. Deploy or verify production only through declared capabilities.

Delivery is complete only when the issue is closed and the board reads `Status = done`, verified by read-back — not when the merge command returns. The [land route](references/land-pr.md) owns that mechanics.

## Wrong-layer recovery

If a delivery reference guesses a CI provider, deploy command, versioning convention, or credential flow, stop. Workflow policy wins on process; repository guidance wins on mechanics — consult the mapped repository capability targets for the latter.
