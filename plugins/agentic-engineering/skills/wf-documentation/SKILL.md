---
name: wf-documentation
description: Workflow policy for creating, reviewing, repairing, compounding, and shipping documentation. Use when documentation is the primary deliverable or when engineering work must leave durable knowledge before delivery completes. Repository locations, tooling, and publication steps come from repository capability targets.
---

# Documentation workflow

Layer: Workflow policy

Owns: document purpose, audience, review gates, informational-health checks, compounding decisions, and documentation completion.

Requires repository capabilities: `repository-overview`, `documentation`.

Does not contain: repository documentation layout, site commands, publication credentials, or house style.

## Start here

Resolve `<skill-directory>` to the directory containing this `SKILL.md`. All
scripts used by this workflow are bundled there; do not resolve them through a
plugin root.

```bash
python3 <skill-directory>/scripts/repository-context.py \
  --require repository-overview \
  --require documentation
```

Stop on contract failure. Read the primary target for both required capabilities, then supporting targets only when needed, before editing documentation.

## Route the request

- Capture a solved problem: read [compound docs](references/compound-docs.md).
- Run the pre-merge workflow compounding stage: read [workflow compound](references/workflows-compound.md).
- Review and refine a document: read [document review](references/document-review.md).
- Turn a debugging lesson into maintained guidance: read [reflect for skill updates](references/reflect-for-skill-updates.md).
- Ship documentation changes: read [land docs](references/land-docs.md).
- Prepare documentation deployment: read [deploy docs](references/deploy-docs.md); require `delivery` when publication is requested.

## Completion boundary

Documentation is complete when it is accurate against the current source, placed where the repository says readers will find it, linked from the appropriate index, reviewed for its intended audience, and validated through repository documentation tooling.

## Wrong-layer recovery

Style, paths, publication commands, and decisions about whether durable knowledge
belongs in a document or repository skill come from the mapped repository assets.
If a reference conflicts with them, the repository capability wins. Return here
to apply review and completion policy.
