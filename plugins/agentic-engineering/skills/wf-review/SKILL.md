---
name: wf-review
description: Workflow policy to review code, architecture, security, plans, documents, or pull-request feedback in proportion to risk. Use for an explicit review or when an independent check would materially reduce delivery risk.
---

# Review workflow

Layer: Workflow policy

Owns: review scope and finding severity.

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

## Review contract

1. Identify the intended behavior and affected system boundaries.
2. Read the full diff and relevant repository guidance.
3. Select only review lenses relevant to the risk surface; use an independent
   reviewer for high-risk or broad changes, not by default.
4. Require reproducible evidence for findings.
5. Deduplicate and classify findings by impact.
6. Require re-verification evidence for any fixes made during review.
7. Produce a clear ready/not-ready decision. Only correctness, security, data
   loss, or explicit repository-policy findings block delivery; polish and
   preference findings do not.

## Wrong-layer recovery

Workflow policy wins on process; repository guidance wins on mechanics — consult the mapped repository capability targets for the latter.
