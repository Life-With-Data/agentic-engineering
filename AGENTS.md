# Agent Instructions

This repository contains two products: the distributed `agentic-engineering`
plugin under `plugins/agentic-engineering/` and a Bun/TypeScript converter and
installer under `src/`. This file is the tool-agnostic source of truth for
repository guidance; tool-specific context files should import it and add only
their own exceptions.

## Working Agreement

- Make each change leave the repository easier to work in. Capture durable
  learnings in `docs/solutions/`, or enforce them with a test when practical.
- Create a feature branch for non-trivial work. If the task already has the
  correct branch, keep using it; do not add worktrees unless requested.
- Preserve user data and unrelated work. Avoid destructive commands.
- Use ASCII unless the file already contains Unicode.
- Run the checks required by [repository operations](.agents/skills/agentic-engineering-repository/SKILL.md#test-execution).
  `bun test` is the source of truth for converter behavior, manifests, counts,
  frontmatter, policies, and generated documentation.
- Do not hand-edit plugin versions or release changelog entries. Release Please
  derives both from Conventional Commit PR titles; see
  [plugin versioning](docs/solutions/plugin-versioning-requirements.md).
- File out-of-scope follow-up work as a GitHub Issue with an explicit repository
  target instead of leaving ad hoc notes.

## Repository Guide

- [Repository operations](.agents/skills/agentic-engineering-repository/SKILL.md)
  covers structure, environment, testing, debugging, delivery, security, and
  documentation mechanics.
- [README.md](README.md) documents the product, installation, and converter CLI;
  [the plugin README](plugins/agentic-engineering/README.md) is the component
  reference, and [WORKFLOW_SKILLS.md](plugins/agentic-engineering/WORKFLOW_SKILLS.md)
  defines the workflow architecture.
- [Conversion policy](docs/conversion-policy.md) defines which assets may be
  translated. Consult the relevant file under `docs/specs/` before changing a
  target; do not add hook conversion to another target.
- [Dependency policy](docs/dependency-policy.md) and
  [the upstream registry](docs/upstream-sources.md) govern external code and
  plugin dependencies.
- Active brainstorms and implementation plans live in their GitHub issues and
  sub-issues. `docs/brainstorms/` and `docs/plans/` are historical archives; do
  not create new files there. Compounded engineering learnings live in
  `docs/solutions/`. Do not hand-edit
  generated regions in `docs/index.html` or `docs/pages/*.html`.

## Agentic Engineering Repository Contract

contract-version: 2

- repository-overview: [repository operations](.agents/skills/agentic-engineering-repository/SKILL.md#repository-overview)
- development-environment: [repository operations](.agents/skills/agentic-engineering-repository/SKILL.md#development-environment)
- test-execution: [repository operations](.agents/skills/agentic-engineering-repository/SKILL.md#test-execution)
- bug-reproduction: [repository operations](.agents/skills/agentic-engineering-repository/SKILL.md#bug-reproduction)
- observability: not-applicable - this repository ships a plugin and CLI with no continuously running application service.
- data-operations: not-applicable - this repository has no persistent application database or production data store.
- infrastructure-operations: [repository operations](.agents/skills/agentic-engineering-repository/SKILL.md#infrastructure-operations)
- delivery: [repository operations](.agents/skills/agentic-engineering-repository/SKILL.md#delivery)
- security-and-access: [repository operations](.agents/skills/agentic-engineering-repository/SKILL.md#security-and-access)
- documentation: [repository operations](.agents/skills/agentic-engineering-repository/SKILL.md#documentation)
