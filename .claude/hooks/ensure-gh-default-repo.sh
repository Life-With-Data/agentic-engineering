#!/bin/bash
#
# SessionStart hook — solve the "fork trap" at its root.
#
# This repo has two remotes: origin = the fork we ship from (Life-With-Data/agentic-engineering)
# and upstream = the parent (EveryInc/compound-engineering-plugin). When no gh default repo
# is set, `gh` resolves *flagless* `gh pr ...` / `gh repo ...` commands to the PARENT, so a
# bare `gh pr create` silently tries to open a PR against upstream. CLAUDE.md forbids that.
#
# gh records its default as `remote.<name>.gh-resolved = base` in git config (exactly what
# `gh repo set-default <fork>` writes). We set it directly — purely local, offline-safe, no
# network/API call — pinning the default to origin. Idempotent; no-ops outside a git repo.
#
# Companion backstop: .claude/hooks/block-upstream-pr.sh (PreToolUse) blocks any gh pr
# command that would still target upstream if this hook didn't run (CI, fresh clone, etc).

set -euo pipefail

# Only act inside a work tree that has an origin remote.
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
origin_url=$(git remote get-url origin 2>/dev/null) || exit 0
[ -n "$origin_url" ] || exit 0

# Pin gh's default base repo to origin (the fork). This is what gh itself reads; setting it
# via git config avoids the network round-trip `gh repo set-default` would make.
current=$(git config --get remote.origin.gh-resolved 2>/dev/null || true)
if [ "$current" != "base" ]; then
  git config remote.origin.gh-resolved base 2>/dev/null || true
fi

exit 0
