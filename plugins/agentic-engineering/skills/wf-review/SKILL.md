---
name: wf-review
description: Workflow policy for reviewing code, architecture, security, plans, documents, and pull-request feedback. Use when evaluating a proposed or implemented change and deciding whether findings block progress. This skill owns review gates and triage; repository conventions come from repository capability targets.
---

# Review workflow

Layer: Workflow policy

Owns: reviewer selection.

Requires repository capabilities: `repository-overview`, `test-execution`.

Does not contain: repository conventions, production access, test commands, or deployment procedures.

## Start here

```bash
python3 <skill-directory>/scripts/repository-context.py \
  --require repository-overview \
  --require test-execution
```

Stop on contract failure; read primary targets first, supporting targets only as needed.

## Route the request

- Run the comprehensive implementation review: read [workflow review](references/workflows-review.md).
- Audit an agent-native system: read [agent-native audit](references/agent-native-audit.md).
- Challenge important decisions during development: read [doubt-driven development](references/doubt-driven-development.md).
- Review security and trust boundaries: read [security and hardening](references/security-and-hardening.md); require `security-and-access` when repository systems are involved.
- Resolve review comments: read [resolve PR parallel](references/resolve-pr-parallel.md).

Document-specific review policy lives in `wf-documentation`; testing sufficiency lives in `wf-testing`.

## Sub-agent delegation

Delegate per-unit stage work to focused sub-agents; the orchestrator retains
verification and every tracker, board, and PR write. Roles, dispatch, model
selection, and the inline fallback:
[sub-agent delegation](../wf-orchestrate/references/subagent-delegation.md).

## Review contract

1. Identify the intended behavior and affected system boundaries.
2. Read the full diff and relevant repository guidance.
3. Select only reviewers relevant to the risk surface.
4. Require reproducible evidence for findings.
5. Deduplicate and classify findings by impact.
6. Require re-verification evidence for any fixes made during review.
7. Produce a clear ready/not-ready decision and return it with its findings to the caller (`wf-orchestrate` in the standard pipeline); a not-ready verdict names the blocking findings for the development stage.

## Wrong-layer recovery

Workflow policy wins on process; repository guidance wins on mechanics — consult the mapped repository capability targets for the latter.
