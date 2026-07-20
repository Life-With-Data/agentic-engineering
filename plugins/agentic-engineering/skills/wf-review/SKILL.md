---
name: wf-review
description: Workflow policy for reviewing code, architecture, security, plans, documents, and pull-request feedback. Use when evaluating a proposed or implemented change and deciding whether findings block progress. This skill owns review gates and triage; repository conventions come from repository capability targets.
---

# Review workflow

Layer: Workflow policy

Owns: review scope, reviewer selection, finding severity, deduplication, fix/defer decisions, and approval readiness.

Requires repository capabilities: `repository-overview`, `test-execution`.

Does not contain: repository conventions, production access, test commands, or deployment procedures.

## Start here

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/repository-context.py" \
  --require repository-overview \
  --require test-execution
```

Stop on contract failure. Read each required capability's primary target, then supporting targets only when needed, before judging convention or completeness.

## Route the request

- Run the comprehensive implementation review: read [workflow review](references/workflows-review.md).
- Audit an agent-native system: read [agent-native audit](references/agent-native-audit.md).
- Challenge important decisions during development: read [doubt-driven development](references/doubt-driven-development.md).
- Review security and trust boundaries: read [security and hardening](references/security-and-hardening.md); require `security-and-access` when repository systems are involved.
- Resolve review comments: read [resolve PR parallel](references/resolve-pr-parallel.md).

Document-specific review policy lives in `wf-documentation`; testing sufficiency lives in `wf-testing`.

## Review contract

1. Identify the intended behavior and affected system boundaries.
2. Read the full diff and relevant repository guidance.
3. Select only reviewers relevant to the risk surface.
4. Require reproducible evidence for findings.
5. Deduplicate and classify findings by impact.
6. Re-verify any fixes through `wf-testing`.
7. Produce a clear ready/not-ready decision.

## Wrong-layer recovery

If a review reference asserts repository-specific style or commands without support from the repository contract, treat that assertion as ungrounded. Consult the mapped repository assets, then resume the review policy here.
