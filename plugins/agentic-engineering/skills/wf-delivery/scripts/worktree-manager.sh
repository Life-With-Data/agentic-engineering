#!/bin/bash

# Git Worktree Manager
# Handles creating, listing, switching, and cleaning up Git worktrees
# KISS principle: Simple, interactive, opinionated

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get repo root
GIT_ROOT=$(git rev-parse --show-toplevel)
WORKTREE_DIR="$GIT_ROOT/.worktrees"

# Harness-created session worktrees (parallel/web sessions, isolation:"worktree"
# subagents) live under this subdir of the PRIMARY checkout, not .worktrees/.
# Every subcommand manages BOTH roots; only `create` still targets .worktrees/
# (.claude/worktrees/ is the harness's creation domain).
HARNESS_WORKTREE_SUBDIR=".claude/worktrees"

# The two managed worktree roots, resolved against the PRIMARY checkout (the
# manager may be invoked from inside a linked worktree). Lazily computed once:
#   ROOT_PRIMARY - the primary checkout itself
#   ROOT_LOCAL   - $ROOT_PRIMARY/.worktrees        (this manager's creation domain)
#   ROOT_HARNESS - $ROOT_PRIMARY/.claude/worktrees (the harness's creation domain)
# Iterate the pair as: for root in "$ROOT_LOCAL" "$ROOT_HARNESS"; do ...
init_roots() {
  [ -n "${ROOT_PRIMARY:-}" ] && return 0
  ROOT_PRIMARY=$(primary_root)
  ROOT_LOCAL="$ROOT_PRIMARY/.worktrees"
  ROOT_HARNESS="$ROOT_PRIMARY/$HARNESS_WORKTREE_SUBDIR"
}

# Short display label for a managed root: ".worktrees" or ".claude/worktrees".
root_label() {
  printf '%s\n' "${1#"$ROOT_PRIMARY"/}"
}

# Resolve a worktree NAME across both managed roots. Prints the single match's
# path on stdout. Returns 0 on exactly one match, 1 on none; when the name
# exists in BOTH roots it prints the candidates to stderr and returns 2 —
# callers must fail rather than guess.
resolve_worktree_name() {
  local name="$1"
  init_roots
  local root candidates=()
  for root in "$ROOT_LOCAL" "$ROOT_HARNESS"; do
    if [[ -d "$root/$name" && -e "$root/$name/.git" ]]; then
      candidates+=("$root/$name")
    fi
  done
  if [[ ${#candidates[@]} -eq 0 ]]; then
    return 1
  fi
  if [[ ${#candidates[@]} -gt 1 ]]; then
    echo -e "${RED}Error: ambiguous worktree name: $name — exists in both managed roots:${NC}" >&2
    local c
    for c in "${candidates[@]}"; do
      echo "  $c" >&2
    done
    echo "Disambiguate with an explicit path, or remove one of them." >&2
    return 2
  fi
  printf '%s\n' "${candidates[0]}"
  return 0
}

# Ensure .worktrees is ignored (any ignore source or pattern form counts).
# --no-index: a tracked path is never reported ignored, which would re-append on every run.
ensure_gitignore() {
  if ! git -C "$GIT_ROOT" check-ignore -q --no-index .worktrees; then
    # Repair a missing final newline so the append can't merge into the last pattern.
    [ -s "$GIT_ROOT/.gitignore" ] && [ -n "$(tail -c1 "$GIT_ROOT/.gitignore")" ] && printf '\n' >> "$GIT_ROOT/.gitignore"
    printf '.worktrees\n' >> "$GIT_ROOT/.gitignore"
  fi
}

# Copy .env files from main repo to worktree
copy_env_files() {
  local worktree_path="$1"

  echo -e "${BLUE}Copying environment files...${NC}"

  # Find all .env* files in root (excluding .env.example which should be in git)
  local env_files=()
  for f in "$GIT_ROOT"/.env*; do
    if [[ -f "$f" ]]; then
      local basename=$(basename "$f")
      # Skip .env.example (that's typically committed to git)
      if [[ "$basename" != ".env.example" ]]; then
        env_files+=("$basename")
      fi
    fi
  done

  if [[ ${#env_files[@]} -eq 0 ]]; then
    echo -e "  ${YELLOW}ℹ️  No .env files found in main repository${NC}"
    return
  fi

  local copied=0
  for env_file in "${env_files[@]}"; do
    local source="$GIT_ROOT/$env_file"
    local dest="$worktree_path/$env_file"

    if [[ -f "$dest" ]]; then
      echo -e "  ${YELLOW}⚠️  $env_file already exists, backing up to ${env_file}.backup${NC}"
      cp "$dest" "${dest}.backup"
    fi

    cp "$source" "$dest"
    echo -e "  ${GREEN}✓ Copied $env_file${NC}"
    copied=$((copied + 1))
  done

  echo -e "  ${GREEN}✓ Copied $copied environment file(s)${NC}"
}

# Create a new worktree
create_worktree() {
  local branch_name="$1"
  local from_branch="${2:-main}"

  if [[ -z "$branch_name" ]]; then
    echo -e "${RED}Error: Branch name required${NC}"
    exit 1
  fi

  local worktree_path="$WORKTREE_DIR/$branch_name"

  # Check if worktree already exists
  if [[ -d "$worktree_path" ]]; then
    echo -e "${YELLOW}Worktree already exists at: $worktree_path${NC}"
    echo -e "Switch to it instead? (y/n)"
    read -r response
    if [[ "$response" == "y" ]]; then
      switch_worktree "$branch_name"
    fi
    return
  fi

  # Refuse a name already used by a harness-created worktree — a duplicate
  # name across roots would make every by-name subcommand ambiguous.
  init_roots
  if [[ -d "$ROOT_HARNESS/$branch_name" ]]; then
    echo -e "${RED}Error: '$branch_name' already exists under $HARNESS_WORKTREE_SUBDIR/: $ROOT_HARNESS/$branch_name${NC}"
    echo "Pick a different name — creating it under .worktrees/ too would make the name ambiguous."
    exit 1
  fi

  echo -e "${BLUE}Creating worktree: $branch_name${NC}"
  echo "  From: $from_branch"
  echo "  Path: $worktree_path"

  # Update main branch
  echo -e "${BLUE}Updating $from_branch...${NC}"
  git checkout "$from_branch"
  git pull origin "$from_branch" || true

  # Create worktree
  mkdir -p "$WORKTREE_DIR"
  ensure_gitignore

  echo -e "${BLUE}Creating worktree...${NC}"
  git worktree add -b "$branch_name" "$worktree_path" "$from_branch"

  # Copy environment files
  copy_env_files "$worktree_path"

  echo -e "${GREEN}✓ Worktree created successfully!${NC}"
  echo ""
  echo "To switch to this worktree:"
  echo -e "${BLUE}cd $worktree_path${NC}"
  echo ""
}

# List all worktrees in both managed roots
list_worktrees() {
  init_roots
  echo -e "${BLUE}Available worktrees:${NC}"
  echo ""

  local count=0 root label
  for root in "$ROOT_LOCAL" "$ROOT_HARNESS"; do
    [[ -d "$root" ]] || continue
    label=$(root_label "$root")
    for worktree_path in "$root"/*; do
      if [[ -d "$worktree_path" && -e "$worktree_path/.git" ]]; then
        count=$((count + 1))
        local worktree_name=$(basename "$worktree_path")
        local branch=$(git -C "$worktree_path" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")

        if [[ "$PWD" == "$worktree_path" ]]; then
          echo -e "${GREEN}✓ $worktree_name${NC} (current) [$label] → branch: $branch"
        else
          echo -e "  $worktree_name [$label] → branch: $branch"
        fi
      fi
    done
  done

  if [[ $count -eq 0 ]]; then
    echo -e "${YELLOW}No worktrees found${NC}"
  else
    echo ""
    echo -e "${BLUE}Total: $count worktree(s)${NC}"
  fi

  echo ""
  echo -e "${BLUE}Main repository:${NC}"
  local main_branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
  echo "  Branch: $main_branch"
  echo "  Path: $GIT_ROOT"
}

# Switch to a worktree (name resolved across both managed roots)
switch_worktree() {
  local worktree_name="$1"

  if [[ -z "$worktree_name" ]]; then
    list_worktrees
    echo -e "${BLUE}Switch to which worktree? (enter name)${NC}"
    read -r worktree_name
  fi

  local worktree_path rc=0
  worktree_path=$(resolve_worktree_name "$worktree_name") || rc=$?

  if [[ $rc -eq 2 ]]; then
    exit 1
  elif [[ $rc -ne 0 ]]; then
    echo -e "${RED}Error: Worktree not found: $worktree_name${NC}"
    echo ""
    list_worktrees
    exit 1
  fi

  echo -e "${GREEN}Switching to worktree: $worktree_name${NC}"
  cd "$worktree_path"
  echo -e "${BLUE}Now in: $(pwd)${NC}"
}

# Copy env files to an existing worktree (or current directory if in a worktree)
copy_env_to_worktree() {
  local worktree_name="$1"
  local worktree_path
  init_roots

  if [[ -z "$worktree_name" ]]; then
    # Check if we're currently in a worktree (either managed root).
    # pwd -P: the roots are physical paths (primary_root resolves symlinks).
    local current_dir=$(pwd -P)
    if [[ "$current_dir" == "$ROOT_LOCAL"/* || "$current_dir" == "$ROOT_HARNESS"/* ]]; then
      worktree_path="$current_dir"
      worktree_name=$(basename "$worktree_path")
      echo -e "${BLUE}Detected current worktree: $worktree_name${NC}"
    else
      echo -e "${YELLOW}Usage: worktree-manager.sh copy-env [worktree-name]${NC}"
      echo "Or run from within a worktree to copy to current directory"
      list_worktrees
      return 1
    fi
  else
    local rc=0
    worktree_path=$(resolve_worktree_name "$worktree_name") || rc=$?

    if [[ $rc -eq 2 ]]; then
      return 1
    elif [[ $rc -ne 0 ]]; then
      echo -e "${RED}Error: Worktree not found: $worktree_name${NC}"
      list_worktrees
      return 1
    fi
  fi

  copy_env_files "$worktree_path"
  echo ""
}

# Clean up completed worktrees (both managed roots)
cleanup_worktrees() {
  init_roots
  if [[ ! -d "$ROOT_LOCAL" && ! -d "$ROOT_HARNESS" ]]; then
    echo -e "${YELLOW}No worktrees to clean up${NC}"
    return
  fi

  echo -e "${BLUE}Checking for completed worktrees...${NC}"
  echo ""

  local found=0
  local to_remove=()
  local root label

  for root in "$ROOT_LOCAL" "$ROOT_HARNESS"; do
    [[ -d "$root" ]] || continue
    label=$(root_label "$root")
    for worktree_path in "$root"/*; do
      if [[ -d "$worktree_path" && -e "$worktree_path/.git" ]]; then
        local worktree_name=$(basename "$worktree_path")

        # Skip if current worktree
        if [[ "$PWD" == "$worktree_path" ]]; then
          echo -e "${YELLOW}(skip) $worktree_name [$label] - currently active${NC}"
          continue
        fi

        found=$((found + 1))
        to_remove+=("$worktree_path")
        echo -e "${YELLOW}• $worktree_name [$label]${NC}"
      fi
    done
  done

  if [[ $found -eq 0 ]]; then
    echo -e "${GREEN}No inactive worktrees to clean up${NC}"
    return
  fi

  echo ""
  echo -e "Remove $found worktree(s)? (y/n)"
  read -r response

  if [[ "$response" != "y" ]]; then
    echo -e "${YELLOW}Cleanup cancelled${NC}"
    return
  fi

  echo -e "${BLUE}Cleaning up worktrees...${NC}"
  for worktree_path in "${to_remove[@]}"; do
    local worktree_name=$(basename "$worktree_path")
    git worktree remove "$worktree_path" --force 2>/dev/null || true
    echo -e "${GREEN}✓ Removed: $worktree_name${NC}"
  done

  # Clean up empty container directories if nothing left
  for root in "$ROOT_LOCAL" "$ROOT_HARNESS"; do
    if [[ -d "$root" && -z "$(ls -A "$root" 2>/dev/null)" ]]; then
      rmdir "$root" 2>/dev/null || true
    fi
  done

  echo -e "${GREEN}Cleanup complete!${NC}"
}

# Absolute path of the PRIMARY checkout. The manager may be invoked from inside
# a linked worktree, where $GIT_ROOT is the worktree root; destructive teardown
# must always run against the primary tree.
primary_root() {
  local common
  common=$(git -C "$GIT_ROOT" rev-parse --git-common-dir)
  case "$common" in
    /*) ;;
    *) common="$GIT_ROOT/$common" ;;
  esac
  common=$(cd "$common" && pwd -P)
  dirname "$common"
}

# Base branch resolution shared by gc/finish/sync:
# $1, else $WORKTREE_GC_BASE, else origin/main (falls back to local main).
resolve_base() {
  local base="${1:-${WORKTREE_GC_BASE:-}}"
  if [[ -z "$base" ]]; then
    if git -C "$GIT_ROOT" rev-parse --verify -q origin/main >/dev/null; then
      base="origin/main"
    else
      base="main"
    fi
  fi
  printf '%s\n' "$base"
}

# Refresh the remote base and prune deleted remotes so merge detection is accurate.
refresh_base() {
  local base="$1"
  case "$base" in
    origin/*) git -C "$GIT_ROOT" fetch -q origin "${base#origin/}" 2>/dev/null || true ;;
  esac
  git -C "$GIT_ROOT" remote prune origin 2>/dev/null || true
}

# Merge-evidence tiers. A fresh (commit-less) branch and a fast-forward-merged
# branch are genuinely indistinguishable in git — both have a tip that is an
# ancestor of the base, no unique commits, and no merge record — so merged
# detection is graded by the STRENGTH of the evidence instead of a yes/no:
#
#   patch          `git cherry <base> <branch>` lists >=1 commit and none is
#                  marked '+': every branch commit's patch is present in the
#                  base under a different sha. Squash/rebase merges. Unambiguous.
#   merge-commit   the branch tip is a NON-first parent of a merge commit
#                  reachable from the base (bounded scan of the base's last 500
#                  merges). GitHub's default "Merge pull request" button, where
#                  `base..branch` is empty and `git cherry` says nothing.
#                  Unambiguous.
#   ancestor-only  `git merge-base --is-ancestor <branch> <base>` holds but
#                  neither of the above matched: EITHER a fast-forward merge OR
#                  a brand-new branch with no commits yet. Ambiguous — callers
#                  must apply a minimum-age (grace) gate before destroying
#                  anything on this tier alone.
#   none           anything else (unique unmerged commits, bad refs, git
#                  errors). Conservative: not merged.
#
# Prints the tier on stdout; always returns 0 (callers dispatch on the string).
branch_merge_tier() {
  local base="$1" br="$2"
  local cherry; cherry=$(git -C "$GIT_ROOT" cherry "$base" "$br" 2>/dev/null || true)
  if [ -n "$cherry" ] && [ "$(printf '%s\n' "$cherry" | grep -c '^+')" -eq 0 ]; then
    printf 'patch\n'
    return 0
  fi
  if ! git -C "$GIT_ROOT" merge-base --is-ancestor "$br" "$base" 2>/dev/null; then
    printf 'none\n'
    return 0
  fi
  local tip; tip=$(git -C "$GIT_ROOT" rev-parse --verify -q "$br^{commit}" 2>/dev/null || true)
  if [ -n "$tip" ]; then
    # Bounded merge-record scan: for each of the base's most recent 500 merge
    # commits, `%P` prints the parent shas space-separated with the mainline
    # first; the tip being among the NON-first parents means this branch is the
    # merged-in side of a real merge commit.
    local parents rest
    while IFS= read -r parents; do
      rest="${parents#* }"                     # drop the first (mainline) parent
      case " $rest " in
        *" $tip "*) printf 'merge-commit\n'; return 0 ;;
      esac
    done < <(git -C "$GIT_ROOT" log --merges -n 500 --format='%P' "$base" 2>/dev/null)
  fi
  printf 'ancestor-only\n'
  return 0
}

# True when there is ANY merge evidence (patch, merge-commit, or ancestor-only).
# On its own, ancestor-only also matches a fresh branch — so only gate
# destruction on this when paired with independent evidence (e.g. sync's
# [gone]-upstream pruning) or an age gate.
branch_is_merged() {
  [ "$(branch_merge_tier "$1" "$2")" != "none" ]
}

# Shared reap loop behind `gc` and `sync`. Reaps a worktree only when ALL safety
# gates hold:
#   - lives under one of the given root dirs (never the main tree)
#   - is not the worktree this runs from
#   - has a clean working tree (no uncommitted changes)
#   - has merge evidence (branch_merge_tier above is not "none")
#   - is idle past the applicable grace: tiers patch/merge-commit use
#     <grace-minutes>; tier ancestor-only — indistinguishable from a fresh
#     branch — uses <ancestor-grace-minutes>, so a pristine worktree another
#     session just created survives until it has been idle past that window
#     (grace 0 disables the respective idle gate)
# It also deletes the now-orphaned local branch. Sets REAPED_COUNT; returns 0.
# Args: <base> <grace-minutes> <ancestor-grace-minutes> <root-dir>...
REAPED_COUNT=0
reap_merged_worktrees() {
  local base="$1" grace="$2" ancestor_grace="$3"
  shift 3
  REAPED_COUNT=0
  local here; here=$(pwd -P)
  local path
  while IFS= read -r path; do
    path="${path#worktree }"
    local in_root="" root
    for root in "$@"; do
      case "$path" in "$root"/*) in_root=1 ;; esac
    done
    [ -n "$in_root" ] || continue                                # only managed roots, never main tree
    [ "$path" = "$here" ] && continue                            # never the one we're in

    local name; name=$(basename "$path")
    local br; br=$(git -C "$path" symbolic-ref --quiet --short HEAD 2>/dev/null || true)
    [ -n "$br" ] || continue                                     # detached HEAD → skip

    if [ -n "$(git -C "$path" status --porcelain 2>/dev/null)" ]; then
      echo -e "${YELLOW}(skip) $name — uncommitted changes${NC}"
      continue
    fi

    local tier; tier=$(branch_merge_tier "$base" "$br")
    if [ "$tier" = "none" ]; then
      echo -e "${YELLOW}(skip) $name — not fully merged into $base${NC}"
      continue
    fi

    # Effective idle window: unambiguous merge evidence (patch/merge-commit)
    # uses <grace>; ancestor-only cannot be told apart from a freshly created
    # worktree, so it must wait out <ancestor_grace> of inactivity first.
    local eff_grace="$grace"
    [ "$tier" = "ancestor-only" ] && eff_grace="$ancestor_grace"

    # active use? recent file activity (node_modules/.git pruned for speed) → skip
    if [ "$eff_grace" -gt 0 ]; then
      local recent; recent=$(find "$path" -type d \( -name node_modules -o -name .git \) -prune -o \
                             -type f -mmin -"$eff_grace" -print 2>/dev/null | head -1)
      if [ -n "$recent" ]; then
        if [ "$tier" = "ancestor-only" ]; then
          echo -e "${YELLOW}(keep) $name — no merge evidence (fast-forward or fresh); younger than ${eff_grace}m grace — kept${NC}"
        else
          echo -e "${YELLOW}(skip) $name — active in the last ${eff_grace}m${NC}"
        fi
        continue
      fi
    fi

    if git -C "$GIT_ROOT" worktree remove "$path" 2>/dev/null; then
      git -C "$GIT_ROOT" branch -D "$br" 2>/dev/null || true
      echo -e "${GREEN}✓ Reaped: $name (branch $br)${NC}"
      REAPED_COUNT=$((REAPED_COUNT + 1))
    fi
  done < <(git -C "$GIT_ROOT" worktree list --porcelain 2>/dev/null | grep '^worktree ')
  return 0
}

# Safe, non-interactive garbage collection of MERGED worktrees.
#
# Unlike `cleanup` (interactive, force-removes EVERY inactive worktree regardless of merge
# state — which can destroy unmerged parallel work), `gc` only reaps a worktree when ALL of
# the reap_merged_worktrees gates hold, so it is safe to run unattended from an agentic loop
# or a git post-merge hook. Scope: BOTH managed roots (.worktrees/ and .claude/worktrees/).
# Always returns 0 — never aborts a caller.
#
# Base branch: $1, else $WORKTREE_GC_BASE, else origin/main (falls back to local main).
# WORKTREE_GC_GRACE_MIN overrides the idle window (default 30). WORKTREE_GC=0 skips entirely.
gc_worktrees() {
  [ "${WORKTREE_GC:-1}" = "0" ] && return 0
  init_roots

  if [[ ! -d "$ROOT_LOCAL" && ! -d "$ROOT_HARNESS" ]]; then
    echo -e "${GREEN}No worktrees to gc${NC}"
    return 0
  fi

  local grace="${WORKTREE_GC_GRACE_MIN:-30}"
  local base; base=$(resolve_base "$1")
  refresh_base "$base"

  echo -e "${BLUE}Reaping merged worktrees (base: $base, grace: ${grace}m)...${NC}"

  # gc applies the same grace to EVERY tier — no fast path here; only sync
  # skips the idle gate for unambiguous (patch/merge-commit) merges.
  reap_merged_worktrees "$base" "$grace" "$grace" "$ROOT_LOCAL" "$ROOT_HARNESS"

  if [ "$REAPED_COUNT" -eq 0 ]; then
    echo -e "${GREEN}No merged worktrees to reap${NC}"
  else
    echo -e "${GREEN}Reaped $REAPED_COUNT merged worktree(s) + local branch(es)${NC}"
  fi

  # Remove the container dirs if nothing is left.
  local d
  for d in "$ROOT_LOCAL" "$ROOT_HARNESS"; do
    if [[ -d "$d" && -z "$(ls -A "$d" 2>/dev/null)" ]]; then
      rmdir "$d" 2>/dev/null || true
    fi
  done

  return 0
}

# Finish ONE worktree you are done with: verify its branch landed in the base,
# then tear down the worktree and its local branch and leave the primary tree on
# an updated base. The explicit single-target counterpart to `gc`/`sync`.
#
# Resolves <name-or-path> against a literal path, then .worktrees/<name>, then
# .claude/worktrees/<name> (both under the PRIMARY checkout). Refuses a dirty
# tree or an unmerged branch unless --force. May be invoked from inside the
# target worktree: teardown runs from the primary tree (the caller's shell cwd
# is gone afterwards). Never touches the primary checkout itself.
finish_worktree() {
  local force=0 target="" base_arg=""
  local arg
  for arg in "$@"; do
    case "$arg" in
      --force) force=1 ;;
      --*)
        echo -e "${RED}Error: unknown option: $arg${NC}"
        echo "Usage: worktree-manager.sh finish <name-or-path> [base-branch] [--force]"
        exit 1
        ;;
      *)
        if [[ -z "$target" ]]; then
          target="$arg"
        elif [[ -z "$base_arg" ]]; then
          base_arg="$arg"
        fi
        ;;
    esac
  done

  if [[ -z "$target" ]]; then
    echo -e "${RED}Error: worktree name or path required${NC}"
    echo "Usage: worktree-manager.sh finish <name-or-path> [base-branch] [--force]"
    exit 1
  fi

  init_roots
  local primary="$ROOT_PRIMARY"

  # Resolve the target: explicit path first, then by name across both roots
  # (a name present in BOTH roots is ambiguous and refused).
  local path=""
  if [[ -e "$target/.git" ]]; then
    path=$(cd "$target" && pwd -P)
  else
    local rc=0
    path=$(resolve_worktree_name "$target") || rc=$?
    if [[ $rc -eq 2 ]]; then
      exit 1
    elif [[ $rc -ne 0 ]]; then
      echo -e "${RED}Error: worktree not found: $target${NC}"
      echo "Looked for a path, $ROOT_LOCAL/$target, and $ROOT_HARNESS/$target"
      exit 1
    fi
  fi

  if [[ "$path" == "$primary" ]]; then
    echo -e "${RED}Error: refusing to finish the primary checkout${NC}"
    exit 1
  fi

  if ! git -C "$GIT_ROOT" worktree list --porcelain 2>/dev/null | grep -qxF "worktree $path"; then
    echo -e "${RED}Error: not a linked worktree of this repository: $path${NC}"
    exit 1
  fi

  local name; name=$(basename "$path")
  local br; br=$(git -C "$path" symbolic-ref --quiet --short HEAD 2>/dev/null || true)
  if [[ -z "$br" ]]; then
    echo -e "${RED}Error: $name is on a detached HEAD — resolve it manually${NC}"
    exit 1
  fi

  local base; base=$(resolve_base "$base_arg")
  refresh_base "$base"

  if [[ -n "$(git -C "$path" status --porcelain 2>/dev/null)" && "$force" -eq 0 ]]; then
    echo -e "${RED}Error: $name has uncommitted changes — commit/stash them or pass --force to discard${NC}"
    exit 1
  fi

  # Tiered merge check (see branch_merge_tier): unambiguous evidence
  # (patch/merge-commit) proceeds; ancestor-only is indistinguishable from a
  # brand-new branch, so it is refused without --force rather than silently
  # destroying what may be someone's freshly created worktree.
  if [[ "$force" -eq 0 ]]; then
    local tier; tier=$(branch_merge_tier "$base" "$br")
    case "$tier" in
      patch|merge-commit) ;;
      ancestor-only)
        echo -e "${RED}Error: branch $br has no unique commits and no merge record in $base — indistinguishable from a fresh branch. If it truly landed via fast-forward, re-run with --force.${NC}"
        exit 1
        ;;
      *)
        echo -e "${RED}Error: branch $br is not fully merged into $base — merge it first or pass --force to discard${NC}"
        exit 1
        ;;
    esac
  fi

  case "$(pwd -P)" in
    "$path"|"$path"/*)
      echo -e "${YELLOW}⚠️  Running from inside the target worktree — teardown continues from the primary tree, and this shell's cwd is about to be deleted: ANY further command in this shell/session will fail. Make finish the last command you run here.${NC}"
      ;;
  esac
  cd "$primary"

  local local_base="${base#origin/}"
  echo -e "${BLUE}Updating $local_base in the primary tree...${NC}"
  git checkout "$local_base"
  git pull --ff-only 2>/dev/null || true    # tolerate offline / no upstream

  echo -e "${BLUE}Removing worktree: $name${NC}"
  if [[ "$force" -eq 1 ]]; then
    git worktree remove --force "$path"
  else
    git worktree remove "$path"
  fi
  git branch -D "$br" 2>/dev/null || true

  # Remove the container dir if nothing is left.
  local parent; parent=$(dirname "$path")
  if [[ -d "$parent" && -z "$(ls -A "$parent" 2>/dev/null)" ]]; then
    rmdir "$parent" 2>/dev/null || true
  fi

  echo -e "${GREEN}✓ Finished: removed worktree $name, deleted branch $br; primary tree on $local_base${NC}"
}

# Post-merge sweep — the one-liner to run after a PR merges in the browser.
# Fetches with --prune (tolerates offline), then reaps merged worktrees in BOTH
# managed roots (.worktrees/ AND .claude/worktrees/):
#   - tiers patch/merge-commit (unambiguous merge evidence): ZERO grace — an
#     explicit invocation is explicit intent, so the idle gate is skipped while
#     every other safety gate (clean tree, not the current worktree) still holds
#   - tier ancestor-only (fast-forward OR fresh — git cannot tell): reaped only
#     after WORKTREE_GC_GRACE_MIN minutes (default 30) of inactivity, so a
#     pristine worktree another session just created is never deleted by a
#     concurrent sync
# Finally deletes leftover local branches whose worktree is already gone, whose
# upstream is gone ([gone]), and which show merge evidence. Safe to run from the
# primary tree at any time; idempotent.
sync_worktrees() {
  local base; base=$(resolve_base "$1")
  init_roots
  local grace="${WORKTREE_GC_GRACE_MIN:-30}"

  if ! git -C "$GIT_ROOT" fetch --prune -q origin 2>/dev/null; then
    echo -e "${YELLOW}⚠️  Could not fetch origin (offline?) — syncing against local refs${NC}"
  fi

  echo -e "${BLUE}Syncing worktrees (base: $base)...${NC}"

  reap_merged_worktrees "$base" 0 "$grace" "$ROOT_LOCAL" "$ROOT_HARNESS"
  local reaped="$REAPED_COUNT"

  # Branches left behind by earlier manual cleanups: worktree already gone,
  # upstream gone, and fully merged into the base.
  local pruned=0
  local br
  while IFS= read -r br; do
    [ -n "$br" ] || continue
    # still checked out somewhere (including the primary tree) → keep
    if git -C "$GIT_ROOT" worktree list --porcelain 2>/dev/null | grep -qxF "branch refs/heads/$br"; then
      continue
    fi
    # A [gone] upstream is itself merge evidence for the ancestor-only tier:
    # the branch HAD an upstream and the remote deleted it — the standard
    # landed-PR shape. A fresh local-only branch has NO upstream configured, so
    # it can never appear in this [gone] list; ancestor-only + [gone] therefore
    # deletes safely, while unique unmerged commits (tier "none") are kept.
    if branch_is_merged "$base" "$br"; then
      if git -C "$GIT_ROOT" branch -D "$br" >/dev/null 2>&1; then
        echo -e "${GREEN}✓ Deleted merged local branch: $br (upstream gone)${NC}"
        pruned=$((pruned + 1))
      fi
    else
      echo -e "${YELLOW}(keep) branch $br — upstream gone but not fully merged into $base${NC}"
    fi
  done < <(git -C "$GIT_ROOT" for-each-ref --format='%(refname:short) %(upstream:track)' refs/heads 2>/dev/null | awk '$2 == "[gone]" {print $1}')

  # Remove empty container dirs.
  local d
  for d in "$ROOT_LOCAL" "$ROOT_HARNESS"; do
    if [[ -d "$d" && -z "$(ls -A "$d" 2>/dev/null)" ]]; then
      rmdir "$d" 2>/dev/null || true
    fi
  done

  echo -e "${GREEN}Sync complete: reaped $reaped worktree(s), deleted $pruned stale branch(es)${NC}"
  return 0
}

# Main command handler
main() {
  local command="${1:-list}"

  case "$command" in
    create)
      create_worktree "$2" "$3"
      ;;
    list|ls)
      list_worktrees
      ;;
    switch|go)
      switch_worktree "$2"
      ;;
    copy-env|env)
      copy_env_to_worktree "$2"
      ;;
    cleanup|clean)
      cleanup_worktrees
      ;;
    gc)
      gc_worktrees "$2"
      ;;
    finish)
      shift
      finish_worktree "$@"
      ;;
    sync)
      sync_worktrees "$2"
      ;;
    help)
      show_help
      ;;
    *)
      echo -e "${RED}Unknown command: $command${NC}"
      echo ""
      show_help
      exit 1
      ;;
  esac
}

show_help() {
  cat << EOF
Git Worktree Manager

Usage: worktree-manager.sh <command> [options]

Every subcommand operates on BOTH managed roots — .worktrees/ and
.claude/worktrees/ (harness-created session worktrees) — except create, which
only ever creates under .worktrees/ (.claude/worktrees/ is the harness's
creation domain). Names are resolved across both roots; a name present in both
is an error listing the candidates.

Commands:
  create <branch-name> [from-branch]  Create new worktree under .worktrees/ (copies .env files
                                      automatically; from-branch defaults to main). Refuses a
                                      name already present under .claude/worktrees/.
  list | ls                           List all worktrees in both roots (labeled per root)
  switch | go [name]                  Switch to worktree (name resolved across both roots)
  copy-env | env [name]               Copy .env files from main repo to worktree
                                      (if name omitted, uses current worktree)
  cleanup | clean                     Interactively remove ALL inactive worktrees in both
                                      roots (prompts)
  gc [base-branch]                    Non-interactively reap only MERGED, clean, idle worktrees
                                      in both roots and their local branches (safe for
                                      unattended/loop use; base defaults to origin/main).
                                      Merge evidence is tiered (see below); every tier waits
                                      out the idle grace.
  finish <name-or-path> [base] [--force]
                                      Tear down ONE worktree you are done with: verify its
                                      branch landed in base with unambiguous evidence (git
                                      cherry patch-equivalence for squash/rebase merges, or a
                                      merge-commit record for GitHub's default merge button),
                                      remove the worktree, delete the local branch, and leave
                                      the primary tree on an updated base. A branch with no
                                      unique commits and no merge record (fast-forwarded OR
                                      brand new — git cannot tell) is refused without --force.
                                      Resolves names under .worktrees/ and .claude/worktrees/;
                                      may be run from inside the target (then it MUST be the
                                      last command in that shell — the cwd is deleted).
                                      --force discards uncommitted/unmerged work.
  sync [base-branch]                  Post-merge sweep: fetch --prune, then reap merged
                                      worktrees in .worktrees/ AND .claude/worktrees/ —
                                      squash/rebase- and merge-commit-merged trees immediately
                                      (zero grace); trees indistinguishable from fresh
                                      (fast-forward or no commits) only after
                                      WORKTREE_GC_GRACE_MIN minutes (default 30) of
                                      inactivity — and delete leftover merged local branches
                                      whose upstream is gone. Idempotent; run after merging a
                                      PR in the browser.
  help                                Show this help message

Merge-evidence tiers (used by gc/finish/sync):
  patch          git cherry shows every branch commit's patch already in base
                 (squash/rebase merges) — unambiguous
  merge-commit   the branch tip is recorded as the merged-in parent of a merge
                 commit reachable from base — unambiguous
  ancestor-only  the tip is an ancestor of base with no unique commits and no
                 merge record: a fast-forward merge OR a brand-new branch (git
                 cannot distinguish them) — protected by the
                 WORKTREE_GC_GRACE_MIN idle window (default 30m)

Environment Files:
  - Automatically copies .env, .env.local, .env.test, etc. on create
  - Skips .env.example (should be in git)
  - Creates .backup files if destination already exists
  - Use 'copy-env' to refresh env files after main repo changes

Examples:
  worktree-manager.sh create feature-login
  worktree-manager.sh create feature-auth develop
  worktree-manager.sh switch feature-login
  worktree-manager.sh copy-env feature-login
  worktree-manager.sh copy-env                   # copies to current worktree
  worktree-manager.sh cleanup
  worktree-manager.sh gc                         # reap merged worktrees (unattended-safe)
  worktree-manager.sh gc develop                 # reap worktrees merged into develop
  worktree-manager.sh finish feature-login       # done with the branch: worktree + branch gone
  worktree-manager.sh sync                       # after a browser merge: reap everything merged
  worktree-manager.sh list

Cleanup commands compared (all cover BOTH roots — .worktrees/ and .claude/worktrees/):
  - cleanup: interactive; force-removes every inactive worktree (can drop unmerged work)
  - gc:      non-interactive; only reaps trees fully merged into the base, with a clean
             tree, idle for WORKTREE_GC_GRACE_MIN minutes (default 30); also deletes the
             orphaned local branch. Skips with WORKTREE_GC=0. Safe to wire into a git
             post-merge hook or run at the end of a parallel/swarm agentic session.
  - finish:  explicit single-target teardown requiring unambiguous merge evidence
             (patch or merge-commit tier; ancestor-only refuses without --force); runs
             teardown from the primary tree and leaves the primary tree on an updated base.
  - sync:    gc with zero grace for unambiguously merged trees, WORKTREE_GC_GRACE_MIN grace
             for ancestor-only (fast-forward-or-fresh) trees — plus deletion of leftover
             merged local branches whose upstream is gone. The post-merge one-liner.

EOF
}

# Run
main "$@"
