---
title: Plugin Versioning and Documentation Requirements
category: workflow
tags: [versioning, changelog, readme, plugin, documentation]
created: 2025-11-24
severity: process
component: plugin-development
---

# Plugin Versioning and Documentation Requirements

## Problem

When making changes to the agentic-engineering plugin, documentation can get out of sync with the actual components (agents, commands, skills). This leads to confusion about what's included in each version and makes it difficult to track changes over time.

## Solution (2026-07-14: version/changelog now automated by release-please)

Version bumps and CHANGELOG.md entries are **no longer hand-authored per PR** —
see `docs/solutions/adopt-release-please.md` for the full adoption.
`.claude-plugin/plugin.json` (and its mirrors: `.claude-plugin/marketplace.json`,
`.cursor-plugin/plugin.json`, `.codex-plugin/plugin.json`) are bumped by
release-please based on the Conventional Commit type in each merged PR title,
and CHANGELOG.md entries are generated from those same titles when
release-please composes its standing release PR. Contributors must:

1. **Use a Conventional Commit type prefix in the PR title** (`feat:`, `fix:`,
   `docs:`, `refactor:`, `chore:`, `perf:`) — enforced in CI by
   `.github/workflows/pr-title.yml`. This is what drives MINOR (`feat`) vs.
   PATCH (`fix`, `perf`) vs. no-release (`docs`, `chore`, `test`, `ci`).
2. **NOT hand-edit** `plugin.json`'s version, any of its mirrors, or
   `CHANGELOG.md` — those are release-please's outputs. A manual edit causes
   version drift: `.github/.release-please-manifest.json` (the last-released
   baseline release-please trusts) disagrees with what's actually on disk. If
   that happens, compare the manifest against the extra-files it should have
   written, and forward-sync the manifest to whatever's higher (safer than
   reverting the extra-files, in case anyone already installed the drifted
   version).
3. **README.md verification still applies, unchanged**: component counts and
   tables must match the filesystem — `tests/plugin-consistency.test.ts`
   enforces this regardless of how the version itself gets bumped.

## Checklist for Plugin Changes

```markdown
Before opening a PR that changes the agentic-engineering plugin:

- [ ] PR title uses a Conventional Commit type (feat:/fix:/docs:/refactor:/chore:/perf:)
- [ ] README.md component counts verified
- [ ] README.md tables updated (if adding/removing/renaming)
- [ ] plugin.json description updated (if component counts changed)
- [ ] Did NOT hand-edit plugin.json's version, its mirrors, or CHANGELOG.md
```

## File Locations

- Version (release-please-owned): `plugins/agentic-engineering/.claude-plugin/plugin.json` → `"version": "X.Y.Z"`, mirrored into `.claude-plugin/marketplace.json`, `.cursor-plugin/plugin.json`, `.codex-plugin/plugin.json`
- Changelog (release-please-owned): `plugins/agentic-engineering/CHANGELOG.md`
- Readme (still hand-maintained): `plugins/agentic-engineering/README.md`
- Release-please config: `.github/release-please-config.json`, `.github/.release-please-manifest.json`

## Example Workflow

When adding a new agent:

1. Create the agent file in `agents/[category]/`
2. Open the PR with a `feat:` title (e.g. `feat: add new-agent-name agent`)
3. Add row to README agent table
4. Update README component count
5. Update plugin.json description with new counts
6. Merge — release-please's standing release PR picks up the change; merging
   *that* PR is what actually bumps the version and writes the changelog

## Prevention

This documentation serves as a reminder. When Claude Code works on this plugin, it should:

1. Check this doc before committing changes
2. Follow the checklist above
3. Never commit partial updates (README counts/tables must land in the same PR as the component change; version/changelog are release-please's job, not the contributor's)

## Related Files

- `plugins/agentic-engineering/.claude-plugin/plugin.json`
- `plugins/agentic-engineering/CHANGELOG.md`
- `plugins/agentic-engineering/README.md`
- `docs/solutions/adopt-release-please.md`
