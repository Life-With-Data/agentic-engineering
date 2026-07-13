# Agent Instructions

This repository is a **Claude Code plugin marketplace** that distributes the `agentic-engineering` plugin. It also includes a Bun/TypeScript CLI that converts Claude Code plugins into other agent platform formats (OpenCode, Codex, etc.). For the full picture — repository structure, versioning rules, and testing — see [CLAUDE.md](CLAUDE.md); this file is the lean, tool-agnostic companion and must not contradict it.

## Critical: never target upstream (the "fork trap")

This repository has two git remotes: **`origin`** = the fork we ship from (`Life-With-Data/agentic-engineering`), and **`upstream`** = the parent (`EveryInc/compound-engineering-plugin`). **All PRs, issues, and `gh` writes MUST target `origin`. NEVER target `EveryInc/compound-engineering-plugin`.**

With no gh default set, *flagless* `gh pr` / `gh issue` / `gh repo` commands resolve to the **parent**, so a bare `gh pr create` silently opens a PR against upstream. Guard against it: run `gh repo set-default Life-With-Data/agentic-engineering` once, or pass `--repo Life-With-Data/agentic-engineering` explicitly. Claude Code sessions get this automatically via committed hooks in `.claude/` (see [CLAUDE.md](CLAUDE.md)); **other agents lack those hooks and must apply this discipline manually.**

## Working Agreement

- **Branching:** Create a feature branch for any non-trivial change. If already on the correct branch for the task, keep using it; do not create additional branches or worktrees unless explicitly requested.
- **Safety:** Do not delete or overwrite user data. Avoid destructive commands.
- **Testing:** Run `bun test` after changes that affect parsing, conversion, or output.
- **Output Paths:** Keep OpenCode output at `opencode.json` and `.opencode/{agents,skills,plugins}`. For OpenCode, command go to `~/.config/opencode/commands/<name>.md`; `opencode.json` is deep-merged (never overwritten wholesale).
- **ASCII-first:** Use ASCII unless the file already contains Unicode.

## Adding a New Target Provider (e.g., Codex)

Use this checklist when introducing a new target provider:

1. **Define the target entry**
   - Add a new handler in `src/targets/index.ts` with `implemented: false` until complete.
   - Use a dedicated writer module (e.g., `src/targets/codex.ts`).

2. **Define types and mapping**
   - Add provider-specific types under `src/types/`.
   - Implement conversion logic in `src/converters/` (from Claude → provider).
   - Keep mappings explicit: tools, permissions, hooks/events, model naming.

3. **Wire the CLI**
   - Ensure `convert` and `install` support `--to <provider>` and `--also`.
   - Keep behavior consistent with OpenCode (write to a clean provider root).

4. **Tests (required)**
   - Extend fixtures in `tests/fixtures/sample-plugin`.
   - Add spec coverage for mappings in `tests/converter.test.ts`.
   - Add a writer test for the new provider output tree.
   - Add a CLI test for the provider (similar to `tests/cli.test.ts`).

5. **Docs**
   - Update README with the new `--to` option and output locations.

## When to Add a Provider

Add a new provider when at least one of these is true:

- A real user/workflow needs it now.
- The target format is stable and documented.
- There’s a clear mapping for tools/permissions/hooks.
- You can write fixtures + tests that validate the mapping.

Avoid adding a provider if the target spec is unstable or undocumented.

## Repository Docs Convention

- **Plans** live in `docs/plans/` and track implementation progress.
