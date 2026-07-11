#!/bin/bash
#
# PreToolUse(Bash) backstop for the "fork trap" — block any gh command that would target
# upstream (EveryInc/compound-engineering-plugin) instead of origin
# (Life-With-Data/agentic-engineering).
#
# The primary fix is .claude/hooks/ensure-gh-default-repo.sh (SessionStart), which pins gh's
# default repo to origin. This guard catches the cases that hook can't cover: an explicit
# upstream target, or a flagless `gh pr`/`gh issue`/`gh project` command running before/without
# the SessionStart fix (CI, a fresh clone mid-session) while gh's default would still resolve
# to the parent. `gh issue` writes matter too: /upstream-scan and issue-tracker workflows write
# issues, and leaking those to the upstream org is the same trap.
#
# The unified-lifecycle work (docs/plans/2026-07-05-feat-unified-lifecycle-github-projects-plan.md)
# adds three new write surfaces the hook must also guard:
#   - `gh project` WRITE subcommands (board mutations; owner-scoped via --owner);
#   - `gh api graphql` calls carrying a ProjectV2 mutation;
#   - `GH_REPO=<upstream>` env-prefix on any gh write, and `gh api` REST writes to a
#     repos/<upstream>/... path.
# Node IDs in GraphQL are opaque, so the ProjectV2 leg is a text backstop only — the real
# discipline is in-script (lifecycle_board.py self-enforces explicit --owner; Security
# invariant 7). Read-only commands (pr view, issue list, project item-list, api reads) are
# never touched.
#
# HONEST LIMITS: text matching here is a backstop, not the real control — the gh-default pin
# (ensure-gh-default-repo.sh) plus in-script explicit --owner/--repo discipline are what
# actually prevent upstream writes. Arbitrary shell obfuscation (variable expansion,
# `$(printf ...)`, base64, here-docs) is uncatchable by text matching and remains out of
# scope; this hook only defeats the cheap, common bypasses (surrounding/interior quotes and
# the -R short flag).

set -euo pipefail

UPSTREAM_OWNER='EveryInc'
UPSTREAM_SLUG='EveryInc/compound-engineering-plugin'
ORIGIN_DEFAULT='Life-With-Data/agentic-engineering'

COMMAND=$(jq -r '.tool_input.command // empty')
[ -n "$COMMAND" ] || exit 0

# Normalized copy with single/double quotes stripped, so interior-quote bypasses
# (Every""Inc, Every''Inc, "EveryInc"/repo) collapse back to the literal slug. The
# upstream owner/slug is matched against BOTH $COMMAND (raw) and $COMMAND_NQ (normalized).
COMMAND_NQ=${COMMAND//\"/}
COMMAND_NQ=${COMMAND_NQ//\'/}

# grep the upstream token against raw AND quote-stripped text. `-e` guards patterns
# that begin with `-` (e.g. `--owner …`) from being read as grep options.
matches_upstream() {
  local pattern="$1"
  echo "$COMMAND" | grep -Eq -e "$pattern" && return 0
  echo "$COMMAND_NQ" | grep -Eq -e "$pattern" && return 0
  return 1
}

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

# Resolve the origin slug once (git@host:owner/repo(.git) or https://host/owner/repo(.git)).
origin_slug=$(git remote get-url origin 2>/dev/null \
  | sed -E 's#^git@[^:]+:##; s#^https?://[^/]+/##; s#\.git$##' || true)
origin_display=${origin_slug:-$ORIGIN_DEFAULT}
resolved=$(git config --get remote.origin.gh-resolved 2>/dev/null || true)

# is_flagless_unpinned: true when the command names no explicit target flag AND gh's default
# repo is not pinned to origin, so gh would silently resolve to the parent. Mirrors the
# original flagless-PR check (b). $1 = the flag regex that would make the target explicit
# (callers pass an alternation covering both the long flag and its -R/-owner short form).
is_flagless_unpinned() {
  local flag_re="$1"
  echo "$COMMAND" | grep -Eq -- "$flag_re" && return 1
  [ -n "$origin_slug" ] && [ "$resolved" != "base" ]
}

# ---------------------------------------------------------------------------
# GH_REPO=<upstream> env-prefix on any gh write → always block. GH_REPO overrides the
# resolved repo for the whole invocation, so it silently redirects issue/pr writes to
# whatever it names — the fork trap by another door.
# ---------------------------------------------------------------------------
if matches_upstream "(^|[; &(])GH_REPO=[\"']?${UPSTREAM_OWNER}/" \
  && echo "$COMMAND" | grep -Eq 'gh +(pr|issue|project|api) '; then
  deny "BLOCKED (fork trap): GH_REPO=${UPSTREAM_OWNER}/… redirects this gh write to upstream. Drop the GH_REPO override (or set GH_REPO=${origin_display}) so writes land on origin."
fi

# ---------------------------------------------------------------------------
# GH_HOST=<host> env-prefix on any gh write → always block (mirror the bootstrap's
# refusal). GH_HOST redirects gh at a different GitHub host entirely, which silently
# bypasses the origin/upstream reasoning — reject it on any gh write regardless of value.
# ---------------------------------------------------------------------------
if echo "$COMMAND" | grep -Eq "(^|[; &(])GH_HOST=" \
  && echo "$COMMAND" | grep -Eq 'gh +(pr|issue|project|api) '; then
  deny "BLOCKED (fork trap): a GH_HOST= prefix redirects this gh write to a different GitHub host, bypassing the origin pin. Drop the GH_HOST override so writes resolve against origin (${origin_display})."
fi

# ---------------------------------------------------------------------------
# gh api REST writes (-X/--method POST|PATCH|PUT|DELETE) to a repos/<upstream>/... path →
# block. gh api graphql is handled separately below (it has no repos/ path).
# ---------------------------------------------------------------------------
if echo "$COMMAND" | grep -Eq 'gh +api ' && ! echo "$COMMAND" | grep -Eq 'gh +api +graphql'; then
  if echo "$COMMAND" | grep -Eq -- '(-X|--method) +(POST|PATCH|PUT|DELETE)'; then
    if matches_upstream "repos/${UPSTREAM_OWNER}/"; then
      deny "BLOCKED (fork trap): this is a gh api REST write to repos/${UPSTREAM_OWNER}/… — it would mutate upstream. Point the path at repos/${origin_display}/… instead."
    fi
  fi
fi

# ---------------------------------------------------------------------------
# gh api graphql carrying a ProjectV2 mutation → block when the command text references the
# upstream owner anywhere (node IDs are opaque; this is a text backstop, the in-script
# --owner discipline is the real guard).
# ---------------------------------------------------------------------------
if echo "$COMMAND" | grep -Eq 'gh +api +graphql'; then
  if echo "$COMMAND" | grep -Eq 'updateProjectV2ItemFieldValue|updateProjectV2Field|addProjectV2ItemById|createProjectV2|deleteProjectV2Item|deleteProjectV2Workflow|addProjectV2DraftIssue'; then
    if matches_upstream "${UPSTREAM_OWNER}([/\"' ]|\$)"; then
      deny "BLOCKED (fork trap): this gh api graphql ProjectV2 mutation references ${UPSTREAM_OWNER}. Board mutations must target origin (${origin_display}); remove the upstream reference and pass origin-owned project/field/item node IDs."
    fi
  fi
fi

# ---------------------------------------------------------------------------
# gh project WRITE subcommands → owner-scoped. Block explicit upstream --owner, and block
# flagless (no --owner) invocations while gh's default is not pinned to origin.
# Read subcommands (field-list, item-list, list, view) are intentionally not matched.
# ---------------------------------------------------------------------------
if echo "$COMMAND" | grep -Eq 'gh +project +(item-add|item-edit|item-create|item-delete|item-archive|field-create|field-delete|edit|create|delete|close|copy|link|unlink|mark-template)( |$)'; then
  if matches_upstream "--owner +[\"']?${UPSTREAM_OWNER}([\"' ]|\$)"; then
    deny "BLOCKED (fork trap): this gh project write names --owner ${UPSTREAM_OWNER} — it would mutate an upstream-owned board. Use --owner ${origin_display%%/*}."
  fi
  if is_flagless_unpinned '--owner'; then
    deny "BLOCKED (fork trap): this gh project write has no --owner and gh's default repo is not pinned to origin, so it could target upstream. Fix once with: gh repo set-default ${origin_display} (or: git config remote.origin.gh-resolved base) — or add --owner ${origin_display%%/*} to the command."
  fi
fi

# ---------------------------------------------------------------------------
# gh pr / gh issue subcommands that act against a base repo (the original checks a+b).
# ---------------------------------------------------------------------------
if echo "$COMMAND" | grep -Eq 'gh +(pr +(create|merge|edit|ready)|issue +(create|edit|close|reopen|comment))'; then
  # (a) Explicit upstream reference → always block. Matched against raw AND quote-stripped
  # text so Every""Inc / "EveryInc"/repo bypasses collapse back to the slug.
  if matches_upstream "${UPSTREAM_SLUG}"; then
    deny "BLOCKED (fork trap): never target ${UPSTREAM_SLUG}. PRs and issues must go to origin (${origin_display}). Drop the upstream repo / use --repo ${origin_display}."
  fi

  # (b) Flagless command (no --repo AND no -R) while gh's default repo does not resolve to
  # origin → it would silently target upstream. Block with the exact fix.
  if is_flagless_unpinned '(--repo|-R)([ =]|$)'; then
    deny "BLOCKED (fork trap): this gh command has no --repo/-R and gh's default repo is not pinned to origin, so it would target upstream. Fix once with: gh repo set-default ${origin_display} (or: git config remote.origin.gh-resolved base) — or add --repo ${origin_display} to the command."
  fi
fi

exit 0
