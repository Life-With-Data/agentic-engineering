#!/bin/bash
#
# PreToolUse(Bash) backstop for the "fork trap" — block any gh PR command that would target
# upstream (EveryInc/compound-engineering-plugin) instead of origin (aagnone3/agentic-engineering).
#
# The primary fix is .claude/hooks/ensure-gh-default-repo.sh (SessionStart), which pins gh's
# default repo to origin. This guard catches the cases that hook can't cover: an explicit
# upstream target, or a flagless `gh pr` command running before/without the SessionStart fix
# (CI, a fresh clone mid-session) while gh's default would still resolve to the parent.

set -euo pipefail

COMMAND=$(jq -r '.tool_input.command // empty')
[ -n "$COMMAND" ] || exit 0

# Only inspect gh pr subcommands that act against a base repo.
echo "$COMMAND" | grep -Eq 'gh +pr +(create|merge|edit|ready)' || exit 0

deny() {
  jq -n --arg reason "$1" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: $reason
    }
  }'
  exit 0
}

# (a) Explicit upstream reference → always block.
if echo "$COMMAND" | grep -q 'EveryInc/compound-engineering-plugin'; then
  deny "BLOCKED (fork trap): never target EveryInc/compound-engineering-plugin. PRs must go to origin (aagnone3/agentic-engineering). Drop the upstream repo / use --repo aagnone3/agentic-engineering."
fi

# (b) Flagless command (no --repo) while gh's default repo does not resolve to origin → it
# would silently target upstream. Block with the exact fix.
if ! echo "$COMMAND" | grep -q -- '--repo'; then
  origin_slug=$(git remote get-url origin 2>/dev/null \
    | sed -E 's#^git@[^:]+:##; s#^https?://[^/]+/##; s#\.git$##' || true)
  resolved=$(git config --get remote.origin.gh-resolved 2>/dev/null || true)
  if [ -n "$origin_slug" ] && [ "$resolved" != "base" ]; then
    deny "BLOCKED (fork trap): this gh pr command has no --repo and gh's default repo is not pinned to origin, so it would target upstream. Fix once with: gh repo set-default ${origin_slug} (or: git config remote.origin.gh-resolved base) — or add --repo ${origin_slug} to the command."
  fi
fi

exit 0
