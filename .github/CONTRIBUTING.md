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
   [Component changes](#component-changes) below — counts and versions must stay
   in sync across several files, and this is enforced.
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
enforces all of this — but to save a round-trip:

- **Update the counts** everywhere they appear:
  - `plugins/agentic-engineering/.claude-plugin/plugin.json`
  - `.claude-plugin/marketplace.json`
  - `plugins/agentic-engineering/README.md`
- **Bump the version** in both manifests (keep them equal):
  - `plugins/agentic-engineering/.claude-plugin/plugin.json` → `version`
  - `.claude-plugin/marketplace.json` → plugin `version`
- **Add a changelog entry** to
  `plugins/agentic-engineering/CHANGELOG.md` (Keep a Changelog format). The
  changelog page on the docs site is generated from this file —
  **never hand-edit `docs/pages/changelog.html`**.
- **Regenerate the docs**: `bun run docs:build`.

> Concurrent PRs sometimes claim the same next version. If you hit a merge
> conflict, re-fetch `main` and re-slot your change to the next free patch
> version in all three files.

Changes that **don't** touch anything under `plugins/` (for example, these
community-health files, or repo tooling) do **not** require a version bump or
changelog entry.

The repo's full conventions live in [`CLAUDE.md`](../CLAUDE.md) — the checklist
there is the human-readable companion to the automated tests.

## Commit messages

Follow the existing style:

- `Add [component]` / `Remove [component]` — new or removed functionality
- `Update [file] to [what changed]` — updates
- `Fix [issue]` — bug fixes
- `Simplify [component] to [improvement]` — refactors

## Reporting bugs and getting help

See [SUPPORT.md](./SUPPORT.md). For security issues, **do not** open a public
issue — follow [SECURITY.md](./SECURITY.md).
