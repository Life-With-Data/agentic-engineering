---
name: wf-delivery
description: Workflow policy for CI repair, release preparation, pull requests, merge gates, artifact transfer, deployment handoff, and release communication. Use when work is implemented and must be shipped. This skill owns delivery sequencing; repository commands and credentials come from repository capability targets.
---

# Delivery workflow

Layer: Workflow policy

Owns: preflight, pull-request state, and merge execution.

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

## Delivery gates

1. Confirm repository-required checks exist for the current head; run missing
   local checks when practical instead of bouncing the work to another stage.
2. Reconcile the branch with its target using repository guidance.
3. Run the repository's delivery checks.
4. Resolve failing required CI and blocking review findings.
5. Create or update the PR with accurate evidence.
6. Merge only when policy and repository gates pass and the run has merge
   authority.
7. Deploy or verify production only through declared capabilities.

In Project mode, verify issue/board completion after merge. Otherwise, verify the
PR or release state relevant to the request. The [land route](references/land-pr.md)
owns the mechanics.

## Wrong-layer recovery

If a delivery reference guesses a CI provider, deploy command, versioning convention, or credential flow, stop. Workflow policy wins on process; repository guidance wins on mechanics — consult the mapped repository capability targets for the latter.
