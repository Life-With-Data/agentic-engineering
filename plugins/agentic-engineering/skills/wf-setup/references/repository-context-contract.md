# Repository context contract

Layer: Workflow policy

This document defines how a repository supplies operational knowledge to the agentic-engineering workflow layer.

## Required root section

Every adopting repository must contain this section in its root `AGENTS.md`:

```markdown
## Agentic Engineering Repository Contract

contract-version: 2

- repository-overview: [architecture](AGENTS.md#architecture), [service catalog](docs/services.md)
- development-environment: [local setup](docs/development.md), [service commands](tools/development/SKILL.md)
- test-execution: [test guide](docs/testing.md), [CI behavior](docs/ci.md)
- bug-reproduction: [debugging playbook](docs/debugging.md), [local setup](docs/development.md)
- observability: [production diagnostics](docs/operations.md#diagnostics), [access procedure](docs/access.md)
- data-operations: [data runbook](docs/data.md)
- infrastructure-operations: [operations runbook](docs/operations.md)
- delivery: [release process](docs/releases.md), [CI behavior](docs/ci.md)
- security-and-access: [access procedure](docs/access.md), [security policy](SECURITY.md)
- documentation: [documentation conventions](AGENTS.md#documentation), [publication process](docs/publishing.md)
```

All ten keys are mandatory. If a capability genuinely does not apply, use:

```markdown
- data-operations: not-applicable — This repository has no persistent application data.
```

Omission is never equivalent to `not-applicable`.

## Mapping semantics

Each available capability maps to one or more comma-separated Markdown links on the same line.

- Links are ordered. The first is the primary operational source; later links are supporting context.
- The same repository asset may appear under multiple capabilities.
- A target may be an existing skill, `AGENTS.md` or `CLAUDE.md` section, runbook, or other repository-owned guidance.
- Use descriptive link text to state why the asset is relevant. Do not add a second role taxonomy.
- A fragment such as `docs/operations.md#diagnostics` narrows a broad document
  without requiring a wrapper. It must resolve to an actual Markdown heading or
  explicit HTML anchor; the validator rejects stale fragments.
- `not-applicable` is exclusive; do not combine it with links.

Workflow skills read the primary target first, then load supporting targets only when the task needs them. Mapping order controls progressive disclosure, not authority or override precedence.

Granular mechanisms belong inside these assets rather than in new top-level
contract keys. For example, `test-execution` may point to a testing guide whose
"Browser verification" section names the repository-approved browser mechanism.
Workflow routes describe the runtime behavior they require; the repository
asset and available host metadata resolve the concrete tool.

## Capability target contract

Targets must be repository-relative, remain inside the repository, and exist on disk. The root contract is the authoritative classification, so existing targets do not need special frontmatter or these declarations:

```markdown
Layer: Repository operations
Capability: bug-reproduction
```

Those declarations remain useful optional metadata for newly created dedicated guidance. If the target is a skill, its existing frontmatter name is valid; the plugin imposes no naming convention. Do not wrap, rename, or annotate an otherwise suitable asset merely to satisfy the contract. Repository assets provide mechanics only; they do not redefine workflow stages, gates, or completion.

Each target should explain:

- The supported commands or interfaces.
- Required environment and access procedure.
- Inputs, outputs, and observable evidence.
- Common failure modes and safe recovery.
- Prohibited operations and escalation points.

Document how to obtain credentials; never store credentials in the guidance.

## Setup inventory and interview

`wf-setup` connects the capabilities to repository assets through an inventory-first interview:

1. Inspect root instructions, conventional documentation directories, existing skills, development scripts, CI configuration, and operational runbooks.
2. Draft mappings from that evidence before asking the user questions.
3. Review the draft in four operational journeys:
   - orient and build: `repository-overview`, `development-environment`
   - test and debug: `test-execution`, `bug-reproduction`
   - operate and access: `observability`, `data-operations`, `infrastructure-operations`, `security-and-access`
   - ship and explain: `delivery`, `documentation`
4. Ask only about missing or ambiguous mechanics, credentials procedures, safety boundaries, and proposed `not-applicable` entries.
5. Reuse existing assets wherever they are adequate. Create new guidance only when knowledge is missing or too fragmented to use safely.
6. Put the most direct operational source first and supporting context after it.
7. Show the completed map, record any evidence-backed non-applicability reasons, and run strict validation.

Setup must not manufacture commands, infer credential values, or create pass-through wrappers solely to achieve one capability per file.

## Migrating version 1

Change `contract-version` to `2`, then replace any wrapper-only targets with the repository assets they merely forwarded to. Existing single-link values remain valid v2 mappings. Add supporting links only where they materially help an agent perform the capability; do not add links to make every mapping look uniform. Per-target `Layer:` and `Capability:` declarations may remain, but are no longer required.

## Validation

Validate the complete contract:

```bash
python3 "<skill-directory>/scripts/repository-context.py"
```

Require capabilities for a particular workflow:

```bash
python3 "<skill-directory>/scripts/repository-context.py" \
  --require bug-reproduction \
  --require test-execution
```

The validator exits non-zero on malformed, incomplete, inaccessible, or insufficient mappings. Its JSON result preserves target order and link labels for workflow consumers. Ordinary workflow skills must stop rather than guess. `wf-setup` may continue only long enough to construct, migrate, or repair the contract, and setup remains incomplete until validation succeeds.
