---
name: wf-delivery
description: Workflow policy for CI repair, release preparation, pull requests, merge gates, artifact transfer, deployment handoff, and release communication. Use when work is implemented and must be shipped. This skill owns delivery sequencing; repository commands and credentials come from repository capability targets.
---

# Delivery workflow

Layer: Workflow policy

Owns: preflight, CI gates, release evidence, PR creation, merge readiness, deployment handoff, and delivery reporting.

Requires repository capabilities: `test-execution`, `delivery`.

Does not contain: CI provider configuration, release commands, production credentials, environment URLs, or rollback mechanics.

## Start here

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/repository-context.py" \
  --require test-execution \
  --require delivery
```

Require `infrastructure-operations` and `security-and-access` before any deployment or production verification. Stop on contract failure. Read each required capability's primary target, then supporting targets only when needed.

## Route the request

- Repair CI failures: read [CI workflow issues](references/ci-resolve-workflow-issues.md).
- Prepare or update release notes: read [changelog](references/changelog.md).
- Drive an open PR to merge: read [land PR](references/land-pr.md).
- Use the workflow merge entry point: read [workflow merge](references/workflows-merge.md).

Documentation-only delivery is routed through `wf-documentation`.
Artifact transports and release-media tooling come from repository capability targets.

## Delivery gates

1. Confirm `wf-testing` and `wf-review` are complete.
2. Reconcile the branch with its target using repository guidance.
3. Run the repository's delivery checks.
4. Resolve CI and review threads.
5. Create or update the PR with accurate evidence.
6. Merge only when policy and repository gates pass.
7. Deploy or verify production only through declared capabilities.

## Wrong-layer recovery

If a delivery reference guesses a CI provider, deploy command, versioning convention, or credential flow, stop and use the mapped repository assets. The workflow decides when delivery is allowed; the repository decides how it is performed.
