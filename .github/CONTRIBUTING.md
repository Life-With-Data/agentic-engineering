# Contributing

Thanks for your interest in improving **Agentic Engineering** — a Claude Code
plugin marketplace. This guide covers the workflow, the checks your change must
pass, and a couple of repo-specific gotchas that trip people up.

By participating you agree to abide by our
[Code of Conduct](./CODE_OF_CONDUCT.md).

## Prerequisites

- [Bun](https://bun.sh) — used for tests and the docs generator.
- The [GitHub CLI](https://cli.github.com) (`gh`) — used to open pull requests.

```bash
bun install
```

## Development workflow

1. **Branch** off `main`.
2. **Make your change.** Adding an agent, command, or skill? See
   [Component changes](#component-changes) below — counts and descriptions must
   stay in sync across several files, and this is enforced.
3. **Run the checks locally** (see [Required checks](#required-checks)).
4. **Open a PR against `origin`** and describe what changed and why.

## Required checks

CI (`.github/workflows/ci.yml`) runs these on every PR. Run them locally first:

```bash
bun test              # plugin consistency, docs sync, dependency policy, etc.
bun run docs:build    # regenerate docs/pages/*.html + landing-page stats
bun run docs:check    # verify the docs site is in sync (also run by bun test)
```

`bun test` is the source of truth. If it fails, the message names the exact
file or component that is out of sync — fix that and re-run. Don't hand-edit
generated output to make a check pass; fix the source and regenerate.

## Component changes

When you **add or remove** an agent, command, or skill, several description
strings and counts must match the filesystem. `tests/plugin-consistency.test.ts`
enforces all of this:

- **Update the component counts and descriptions** named by a failing
  `bun test` run.
- **Do not hand-bump versions or write release changelog entries.** Release
  Please owns both; see
  [plugin versioning](../docs/solutions/plugin-versioning-requirements.md).
- **Regenerate the docs**: `bun run docs:build`.

Changes that **don't** touch anything under `plugins/` (for example, these
community-health files, or repo tooling) do **not** require a version bump or
changelog entry.

The repository's high-level conventions live in [`AGENTS.md`](../AGENTS.md),
which points to the detailed operational guidance and automated checks.

## Pull request titles

Use a Conventional Commit prefix such as `feat:`, `fix:`, `docs:`, `refactor:`,
`chore:`, `perf:`, `test:`, or `ci:`. Release Please uses the squash-merged PR
title to determine releases and changelog sections.

## Reporting bugs and getting help

See [SUPPORT.md](./SUPPORT.md). For security issues, **do not** open a public
issue — follow [SECURITY.md](./SECURITY.md).
