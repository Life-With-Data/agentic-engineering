---
title: "Adopting release-please after a fork-disconnect stranded PR"
category: workflow
tags: [release-please, versioning, github-actions, conventional-commits, fork-disconnect]
created: 2026-07-14
severity: process
component: release-automation
---

# Adopting release-please after a fork-disconnect stranded PR

## Problem

Disconnecting `agentic-engineering` from the upstream fork it originated from
required a force-push of `main` back to the correct, disconnected history.
But `googleapis/release-please-action` had already opened a standing release
PR (`release-please--branches--main` → `main`) against the *old* history
before the reset happened. After the force-push, that PR diffed 826 files
across 100 commits and was permanently unmergeable — its branch tip was
confirmed **not** an ancestor of the new `main` (`git merge-base
--is-ancestor <old-tip> <new-tip>` returned false). Worse, the workflow that
created it (`release-pr.yml`) didn't exist on the new `main` at all, so it
could never regenerate itself.

Investigating further showed release-please had **never actually been part
of this repo's own history** — it only existed in the unrelated upstream
"compound-engineering" project (with its own `cli`/`.agy`/`.kimi-plugin`/
`.grok-plugin` package structure) that briefly leaked in through the
fork-disconnect tangle. The repo's real, current release mechanism was a
much simpler tag-on-push workflow (`release.yml`, added 2026-07-13,
independently of any release-please history) that read the hand-bumped
version out of `plugin.json` and cut a tag + GitHub Release on push to
`main`.

## Decision

Close the stranded PR (unsalvageable) and delete its branch, then adopt
release-please fresh — scoped to the repo's *current* structure, not a
restoration of the old upstream's shape.

## Solution

Two release-please packages, one per releasable component that actually
exists today:

- `plugins/agentic-engineering` — the core plugin. `extra-files` mirror its
  version into `.claude-plugin/marketplace.json` (`plugins[0].version`),
  `.cursor-plugin/plugin.json`, and `.codex-plugin/plugin.json`.
- `plugins/marketing` — independent version, its own `marketplace.json`
  entry (`plugins[1].version`).

Config lives in `.github/release-please-config.json` /
`.github/.release-please-manifest.json` (manifest seeded at the versions in
place when this was adopted: `4.0.0` / `0.1.0`). `bootstrap-sha` is set at
the **top level** of the config (a single Manifest-wide option — it is
**not** a per-package field, see the gotcha below) to the commit tip of
`main` at adoption time, so the first generated release PR's changelog
doesn't dredge up the entire project history — neither package has any
commits tagged in release-please's `<package-name>-v<version>` format yet
(existing tags are flat `vX.Y.Z` from the old `release.yml`).

`.github/workflows/release-pr.yml` runs `googleapis/release-please-action`
on push to `main`, maintaining one standing release PR per package. Merging
a generated release PR is what cuts that package's tag + GitHub Release —
`release.yml` was deleted, since having both would double-tag the same
version bump.

release-please computes bumps from Conventional Commit-typed PR titles, and
**attributes a commit to a package by which directory its changed files live
under** — not by commit scope — so `feat:`/`fix:`/etc. prefixes are required,
but a `(scope)` is not, to route a change to the right package.

Because this repo previously had **no PR-title enforcement at all** (commit
titles were a mix of Conventional-Commit-style and plain imperative titles —
confirmed via `git log`), a new `.github/workflows/pr-title.yml` running
`amannn/action-semantic-pull-request` makes the Conventional Commit
requirement a CI-enforced gate rather than a convention people could
silently drift away from, since an unprefixed title would otherwise
silently produce no release-please changelog entry at all.

Both new third-party actions are SHA-pinned with a trailing version comment,
per `docs/solutions/security-issues/hardening-scaffolded-github-actions-workflows.md`'s
guidance that third-party (non-`actions/*`) actions should be pinned rather
than tracking a moving tag, especially when granted `contents: write` /
`pull-requests: write` (as `release-please-action` is here).

## Gotcha discovered via the first live dry run (do not repeat)

The first version of this config was wrong in two ways, caught by actually
letting `release-pr.yml` run against `main` (PR #157) rather than trusting
the config on paper — read `src/manifest.ts` and
`src/strategies/base.ts`/`simple.ts` in the `release-please` source, not just
the JSON schema, before assuming a field does what its name suggests:

1. **`bootstrap-sha` only exists at the top level of the manifest config**
   (`config['bootstrap-sha']` in `manifest.ts`) — nesting it inside a
   `packages.<path>` object is silently accepted as valid JSON but has no
   effect. The first dry run scanned the *entire* project history and
   proposed a MAJOR bump (`4.0.0` → `5.0.0`) off a years-old "BREAKING
   CHANGE" commit that had nothing to do with the actual PR.
2. **`extra-files` paths are relative to the *package's own directory*, not
   the repo root** — `BaseStrategy.addPath()` prefixes every extra-file path
   with `this.path` (the package path) unless the path starts with a leading
   `/`, and it throws on `../` traversal entirely (`illegal pathing
   characters`). Every extra-file in the first version of this config was
   wrong: paths meant to be root-relative (e.g. `.claude-plugin/marketplace.json`)
   got silently double-prefixed with the package directory and pointed at
   files that don't exist — so PR #157 updated only `CHANGELOG.md` and the
   manifest, and never touched `plugin.json` (the actual version source of
   truth) or any of its mirrors at all. The fix: for a file *inside* the
   package directory, use a plain relative path (e.g. `.claude-plugin/plugin.json`
   for the package's own manifest); for a file *outside* it (like the root
   `marketplace.json`), prefix with a leading `/` (e.g.
   `/.claude-plugin/marketplace.json`) — never `../../`.

PR #157 was closed unmerged (it would have shipped a wrong major bump and a
`plugin.json` that never actually changed); its branch was deleted, the
config above was corrected, and the fix was re-verified with a second live
dry run before being trusted.

## Known limitation, accepted

The `marketplace.json` extra-files patch plugin entries by array index
(`plugins[0]`, `plugins[1]`), not by name, since release-please's generic
JSON updater doesn't reliably support JSONPath name-filters. If the
`plugins` array is ever reordered, this would target the wrong entry — but
`tests/plugin-consistency.test.ts` already asserts each plugin's
`plugin.json` version matches its marketplace entry *by name*, so CI fails
loudly on drift rather than silently accepting it.

## Prevention

- Verify with `git merge-base --is-ancestor <PR-branch-tip> <main-tip>` before assuming any bot-generated automation PR can simply be re-triggered after a history rewrite — if the branch tip isn't an ancestor of the current default branch, the PR cannot be salvaged and the underlying automation should be re-examined, not just the PR.
- Don't assume an artifact (a workflow, a config file, a stray PR) reflects the repo's own history just because it's present on GitHub — check `git merge-base`/`git log --all` to see whether it's reachable from the branch you actually care about.

## Related docs

- `docs/solutions/plugin-versioning-requirements.md` — contributor-facing versioning rules, updated alongside this adoption.
- `docs/solutions/security-issues/hardening-scaffolded-github-actions-workflows.md` — the SHA-pinning / minimal-permissions pattern applied to the two new workflows here.
- `AGENTS.md` — repository-level release guidance and links.
