#!/usr/bin/env bash
#
# Claude Code hook (SessionStart / PreCompact) that primes beads tracker context.
#
# When a project uses beads as its issue tracker (see workflow-repo-preflight.py's tracker
# detection: `.beads/` present + `bd` on PATH), `bd prime` surfaces ready work, conventions, and
# session-close protocol that would otherwise only surface if an agent thought to ask for it.
# Running it at SessionStart gives every session that context up front; running it again at
# PreCompact restores it after context is summarized away.
#
# No-ops entirely for projects that don't use beads, so it is safe to ship broadly.

set -euo pipefail

command -v bd >/dev/null 2>&1 || exit 0
[ -d .beads ] || exit 0

bd prime
