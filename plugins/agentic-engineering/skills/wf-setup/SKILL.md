---
name: wf-setup
description: Workflow policy for adopting and configuring agentic-engineering in a repository. Use for first-time setup, repository-contract creation or repair, lifecycle bootstrap, configuration flags, hook installation, and readiness diagnostics. This skill owns setup completion; repository-specific values still come from repository evidence or explicit user input.
---

# Setup workflow

Layer: Workflow policy

Owns: repository adoption, complete capability-contract creation, plugin configuration, lifecycle bootstrap, portable hook installation, readiness checks, and setup repair.

Requires repository capabilities: none before contract bootstrap; the complete fixed contract before setup can finish.

Does not contain: invented repository commands, guessed credentials, product implementation policy, or ongoing plugin-development procedures.

## Start here

Resolve `<skill-directory>` to the directory containing this `SKILL.md`. All
scripts used by this workflow are bundled there; do not resolve them through a
plugin root. Run the strict validator from any path inside the repository
checkout:

```bash
python3 <skill-directory>/scripts/repository-context.py
```

- If it passes, read primary targets first and supporting targets only when needed before changing configuration.
- If it fails because the contract is missing, outdated, or malformed, enter bootstrap mode. Bootstrap mode may create, migrate, or repair the fixed section, but it must derive mappings from existing repository assets or explicit user input.
- Never turn an unknown capability into `not-applicable` merely to make validation pass.

This is the only workflow allowed to proceed temporarily with an invalid contract, and only for the purpose of repairing that contract.

## Route the request

- Adopt or reconfigure the plugin: read [setup](references/setup.md).
- Create or repair the fixed capability map: read [repository context contract](references/repository-context-contract.md).
- Inspect or change configuration: read [config flags](references/config-flags.md).
- Install portable hooks after a skills-only installation: read [install hooks](references/install-hooks.md).
- Adopt or migrate the GitHub Projects lifecycle: read [lifecycle bootstrap](references/lifecycle-bootstrap.md), then use [lifecycle](references/lifecycle.md) for operating policy.
- Understand lifecycle policy without changing setup: read [lifecycle](references/lifecycle.md).
- Verify lifecycle and setup readiness: read [lifecycle doctor](references/lifecycle-doctor.md).

Load only the selected references. Setup references never override repository-owned operational guidance.

## Completion boundary

Setup is complete only when:

1. Root `AGENTS.md` contains the complete fixed capability set.
2. Every available capability maps to one or more existing repository assets in useful reading order.
3. Gaps, safety boundaries, and `not-applicable` decisions are resolved from repository evidence or the setup interview.
4. The strict validator exits successfully.
5. Requested plugin configuration, lifecycle, and hooks are verified through their diagnostics.
6. Lifecycle adoption, when selected, meets the setup-completion checklist in
   [lifecycle bootstrap](references/lifecycle-bootstrap.md), including the
   chosen forward binding and live verification.

## Wrong-layer recovery

`wf-setup` decides what must exist for adoption and readiness. It does not know how a repository builds, tests, deploys, or accesses infrastructure. Inventory repository-owned assets, map suitable existing context directly, interview only for unresolved mechanics, and return here to validate the contract.
