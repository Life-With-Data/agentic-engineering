---
name: wf-documentation
description: Workflow policy for creating, reviewing, repairing, compounding, and shipping documentation. Use when documentation is the primary deliverable or when engineering work must leave durable knowledge before delivery completes. Repository locations, tooling, and publication steps come from repository capability targets.
---

# Documentation workflow

Layer: Workflow policy

Owns: document purpose and audience.

Requires repository capabilities: `repository-overview`, `documentation`.

Does not contain: repository documentation layout, site commands, publication credentials, or house style.

## Start here

```bash
python3 <skill-directory>/scripts/repository-context.py \
  --require repository-overview \
  --require documentation
```

Stop on contract failure; read primary targets first, supporting targets only as needed.

## Route the request

- Capture a solved problem: read [compound docs](references/compound-docs.md).
- Run the pre-merge workflow compounding stage: read [workflow compound](references/workflows-compound.md).
- Review and refine a document: read [document review](references/document-review.md).
- Turn a debugging lesson into maintained guidance: read [reflect for skill updates](references/reflect-for-skill-updates.md).
- Ship documentation changes: read [land docs](references/land-docs.md); require `delivery` when publication is requested. Publication mechanics come from the repository's mapped `delivery` capability.

## Completion boundary

Documentation is complete when it is accurate, discoverable where readers
already look, and passes repository documentation checks. Do not create a
document merely to prove the workflow considered documentation.

## Wrong-layer recovery

The decision whether durable knowledge belongs in a document or a repository
skill comes from the mapped repository assets. Workflow policy wins on
process; repository guidance wins on mechanics — consult the mapped
repository capability targets for the latter.
