---
name: wf-delivery
description: Workflow policy for CI repair, release preparation, pull requests, merge gates, artifact transfer, deployment handoff, and release communication. Use when work is implemented and must be shipped. This skill owns delivery sequencing; repository commands and credentials come from repository capability targets.
---

# Delivery workflow

Layer: Workflow policy

Owns: preflight, CI gates, release evidence, PR creation, merge readiness,
the final pre-merge compounding gate, deployment handoff, and delivery
reporting.

Requires repository capabilities: `test-execution`, `delivery`.

Does not contain: CI provider configuration, release commands, production credentials, environment URLs, or rollback mechanics.

## Start here

Resolve `<skill-directory>` to the directory containing this `SKILL.md`. All
scripts used by this workflow are bundled there; do not resolve them through a
plugin root.

```bash
python3 <skill-directory>/scripts/repository-context.py \
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

## Sub-agent delegation

The session's default agent orchestrates and validates delivery; it delegates
the diagnosis and drafting. Dispatch focused sub-agents for per-job CI-failure
diagnosis and for release-note and PR-body drafting. The orchestrator retains
merge decisions, every PR and tracker state write, and release evidence, and
verifies each delegated result against the actual CI and repository state.
Set each sub-agent's model explicitly at dispatch — hosts otherwise inherit
the session's model — choosing the lowest tier the task allows: an economy
tier for mechanical log collection and drafting from templates, a standard
tier for single-job failure diagnosis, the strongest available tier only for
cross-job or flaky-infrastructure analysis. Hosts without a sub-agent mechanism run the
same steps inline.

## Delivery gates

1. Confirm `wf-testing` and `wf-review` are complete.
2. Reconcile the branch with its target using repository guidance.
3. Run the repository's delivery checks.
4. Resolve CI and review threads.
5. Create or update the PR with accurate evidence.
6. Immediately before merge, perform the final compounding disposition against
   the current PR head and record its audit evidence. This gate is mandatory
   even when every CI and review signal is already green.
7. Merge only when policy and repository gates pass.
8. Deploy or verify production only through declared capabilities.

Delivery is complete only when the issue is closed and the board reads `Status = done`, verified by read-back — `--reconcile --issue <N>` repairs a missed stamp and `--delete-packet <N>` independently verifies the terminal state — not when the merge command returns. The [land route](references/land-pr.md) owns that mechanics.

## Wrong-layer recovery

If a delivery reference guesses a CI provider, deploy command, versioning convention, or credential flow, stop and use the mapped repository assets. The workflow decides when delivery is allowed; the repository decides how it is performed.
