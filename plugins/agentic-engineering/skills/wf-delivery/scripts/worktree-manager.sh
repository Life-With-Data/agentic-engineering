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

# List all worktrees
list_worktrees() {
  echo -e "${BLUE}Available worktrees:${NC}"
  echo ""

  if [[ ! -d "$WORKTREE_DIR" ]]; then
    echo -e "${YELLOW}No worktrees found${NC}"
    return
  fi

  local count=0
  for worktree_path in "$WORKTREE_DIR"/*; do
    if [[ -d "$worktree_path" && -e "$worktree_path/.git" ]]; then
      count=$((count + 1))
      local worktree_name=$(basename "$worktree_path")
      local branch=$(git -C "$worktree_path" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")

      if [[ "$PWD" == "$worktree_path" ]]; then
        echo -e "${GREEN}✓ $worktree_name${NC} (current) → branch: $branch"
      else
        echo -e "  $worktree_name → branch: $branch"
      fi
    fi
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

# Switch to a worktree
switch_worktree() {
  local worktree_name="$1"

  if [[ -z "$worktree_name" ]]; then
    list_worktrees
    echo -e "${BLUE}Switch to which worktree? (enter name)${NC}"
    read -r worktree_name
  fi

  local worktree_path="$WORKTREE_DIR/$worktree_name"

  if [[ ! -d "$worktree_path" ]]; then
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

  if [[ -z "$worktree_name" ]]; then
    # Check if we're currently in a worktree
    local current_dir=$(pwd)
    if [[ "$current_dir" == "$WORKTREE_DIR"/* ]]; then
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
    worktree_path="$WORKTREE_DIR/$worktree_name"

    if [[ ! -d "$worktree_path" ]]; then
      echo -e "${RED}Error: Worktree not found: $worktree_name${NC}"
      list_worktrees
      return 1
    fi
  fi

  copy_env_files "$worktree_path"
  echo ""
}

# Clean up completed worktrees
cleanup_worktrees() {
  if [[ ! -d "$WORKTREE_DIR" ]]; then
    echo -e "${YELLOW}No worktrees to clean up${NC}"
    return
  fi

  echo -e "${BLUE}Checking for completed worktrees...${NC}"
  echo ""

  local found=0
  local to_remove=()

  for worktree_path in "$WORKTREE_DIR"/*; do
    if [[ -d "$worktree_path" && -e "$worktree_path/.git" ]]; then
      local worktree_name=$(basename "$worktree_path")

      # Skip if current worktree
      if [[ "$PWD" == "$worktree_path" ]]; then
        echo -e "${YELLOW}(skip) $worktree_name - currently active${NC}"
        continue
      fi

      found=$((found + 1))
      to_remove+=("$worktree_path")
      echo -e "${YELLOW}• $worktree_name${NC}"
    fi
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

  # Clean up empty directory if nothing left
  if [[ -z "$(ls -A "$WORKTREE_DIR" 2>/dev/null)" ]]; then
    rmdir "$WORKTREE_DIR" 2>/dev/null || true
  fi

  echo -e "${GREEN}Cleanup complete!${NC}"
}

# Safe, non-interactive garbage collection of MERGED worktrees.
#
# Unlike `cleanup` (interactive, force-removes EVERY inactive worktree regardless of merge
# state — which can destroy unmerged parallel work), `gc` only reaps a worktree when ALL of
# these hold, so it is safe to run unattended from an agentic loop or a git post-merge hook:
#   - lives under .worktrees/ (never the main tree)
#   - is not the worktree gc is running from
#   - has a clean working tree (no uncommitted changes)
#   - is fully merged into the base branch: `git cherry <base> <branch>` shows zero '+'
#     (every commit's patch is already in base — this catches squash/rebase merges where the
#     SHAs differ) and at least one '-' (it had real commits; a brand-new empty branch is left)
#   - is idle: nothing outside node_modules/.git modified in the last GRACE minutes
# It also deletes the now-orphaned local branch. Always returns 0 — never aborts a caller.
#
# Base branch: $1, else $WORKTREE_GC_BASE, else origin/main (falls back to local main).
# WORKTREE_GC_GRACE_MIN overrides the idle window (default 30). WORKTREE_GC=0 skips entirely.
gc_worktrees() {
  [ "${WORKTREE_GC:-1}" = "0" ] && return 0

  if [[ ! -d "$WORKTREE_DIR" ]]; then
    echo -e "${GREEN}No worktrees to gc${NC}"
    return 0
  fi

  local grace="${WORKTREE_GC_GRACE_MIN:-30}"
  local base="${1:-${WORKTREE_GC_BASE:-}}"
  if [[ -z "$base" ]]; then
    if git -C "$GIT_ROOT" rev-parse --verify -q origin/main >/dev/null; then
      base="origin/main"
    else
      base="main"
    fi
  fi

  # Refresh the remote base and prune deleted remotes so merge detection is accurate.
  case "$base" in
    origin/*) git -C "$GIT_ROOT" fetch -q origin "${base#origin/}" 2>/dev/null || true ;;
  esac
  git -C "$GIT_ROOT" remote prune origin 2>/dev/null || true

  echo -e "${BLUE}Reaping merged worktrees (base: $base, grace: ${grace}m)...${NC}"

  local removed=0
  local here="$PWD"
  while IFS= read -r path; do
    path="${path#worktree }"
    case "$path" in "$WORKTREE_DIR"/*) ;; *) continue ;; esac   # only .worktrees/, never main tree
    [ "$path" = "$here" ] && continue                            # never the one we're in

    local name; name=$(basename "$path")
    local br; br=$(git -C "$path" symbolic-ref --quiet --short HEAD 2>/dev/null || true)
    [ -n "$br" ] || continue                                     # detached HEAD → skip

    if [ -n "$(git -C "$path" status --porcelain 2>/dev/null)" ]; then
      echo -e "${YELLOW}(skip) $name — uncommitted changes${NC}"
      continue
    fi

    # merged = had commits, all patch-present in base (all '-'); zero '+' and at least one '-'.
    local cherry; cherry=$(git -C "$GIT_ROOT" cherry "$base" "$br" 2>/dev/null || true)
    if [ "$(printf '%s\n' "$cherry" | grep -c '^+')" -ne 0 ] || \
       [ "$(printf '%s\n' "$cherry" | grep -c '^-')" -lt 1 ]; then
      echo -e "${YELLOW}(skip) $name — not fully merged into $base${NC}"
      continue
    fi

    # active use? recent file activity (node_modules/.git pruned for speed) → skip
    local recent; recent=$(find "$path" -type d \( -name node_modules -o -name .git \) -prune -o \
                           -type f -mmin -"$grace" -print 2>/dev/null | head -1)
    if [ -n "$recent" ]; then
      echo -e "${YELLOW}(skip) $name — active in the last ${grace}m${NC}"
      continue
    fi

    if git -C "$GIT_ROOT" worktree remove "$path" 2>/dev/null; then
      git -C "$GIT_ROOT" branch -D "$br" 2>/dev/null || true
      echo -e "${GREEN}✓ Reaped: $name (branch $br)${NC}"
      removed=$((removed + 1))
    fi
  done < <(git -C "$GIT_ROOT" worktree list --porcelain 2>/dev/null | grep '^worktree ')

  if [ "$removed" -eq 0 ]; then
    echo -e "${GREEN}No merged worktrees to reap${NC}"
  else
    echo -e "${GREEN}Reaped $removed merged worktree(s) + local branch(es)${NC}"
  fi

  # Remove the container dir if nothing is left.
  if [[ -d "$WORKTREE_DIR" && -z "$(ls -A "$WORKTREE_DIR" 2>/dev/null)" ]]; then
    rmdir "$WORKTREE_DIR" 2>/dev/null || true
  fi

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

Commands:
  create <branch-name> [from-branch]  Create new worktree (copies .env files automatically)
                                      (from-branch defaults to main)
  list | ls                           List all worktrees
  switch | go [name]                  Switch to worktree
  copy-env | env [name]               Copy .env files from main repo to worktree
                                      (if name omitted, uses current worktree)
  cleanup | clean                     Interactively remove ALL inactive worktrees (prompts)
  gc [base-branch]                    Non-interactively reap only MERGED, clean, idle worktrees
                                      and their local branches (safe for unattended/loop use;
                                      base defaults to origin/main)
  help                                Show this help message

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
  worktree-manager.sh list

GC vs Cleanup:
  - cleanup: interactive; force-removes every inactive worktree (can drop unmerged work)
  - gc:      non-interactive; only reaps worktrees fully merged into the base, with a clean
             tree, idle for WORKTREE_GC_GRACE_MIN minutes (default 30); also deletes the
             orphaned local branch. Skips with WORKTREE_GC=0. Safe to wire into a git
             post-merge hook or run at the end of a parallel/swarm agentic session.

EOF
}

# Run
main "$@"
