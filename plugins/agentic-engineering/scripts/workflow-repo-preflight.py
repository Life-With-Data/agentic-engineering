#!/usr/bin/env python3
"""
Deterministic repository preflight for the `wf-development` work route.

Outputs a JSON object with repository state, branch context, optional PR metadata,
issue-tracker availability, and a recommended next action so agents can branch on
explicit state instead of re-deriving it from prose instructions.

Issue-tracker resolution order (first match wins):
  1. issue_tracker: field in agentic-engineering.local.md frontmatter (explicit
     override; a git-tracked copy is ignored — a PR must never carry it)
  2. committed board config (agentic-engineering.md with
     github_project_owner + github_project_number)              -> "github-project"
  3. `gh auth status` returns 0                                 -> "github"
  4. otherwise                                                  -> "none"

Lifecycle predicates and board verbs live in lifecycle_board.py (imported
below); this script stays a READ-ONLY reporter — repairs run only when a
command explicitly invokes `lifecycle_board.py --reconcile`.
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
from typing import Any, Optional

_LB_SPEC = importlib.util.spec_from_file_location("lifecycle_board", pathlib.Path(__file__).resolve().with_name("lifecycle_board.py"))
assert _LB_SPEC is not None and _LB_SPEC.loader is not None
lifecycle_board = importlib.util.module_from_spec(_LB_SPEC)
sys.modules["lifecycle_board"] = lifecycle_board
_LB_SPEC.loader.exec_module(lifecycle_board)


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True)


def git(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return run(["git", *cmd])


def git_ok(cmd: list[str], default: str = "") -> str:
    result = git(cmd)
    if result.returncode != 0:
        return default
    return result.stdout.strip()


def bool_from_exit(cmd: list[str]) -> bool:
    return git(cmd).returncode == 0


def parse_int(value: str) -> int:
    try:
        return int(value.strip())
    except Exception:
        return 0


def find_default_branch() -> str:
    remote_head = git_ok(["symbolic-ref", "refs/remotes/origin/HEAD"])
    if remote_head.startswith("refs/remotes/origin/"):
        return remote_head.removeprefix("refs/remotes/origin/")

    for candidate in ("main", "master"):
        if bool_from_exit(["show-ref", "--verify", f"refs/remotes/origin/{candidate}"]):
            return candidate
        if bool_from_exit(["show-ref", "--verify", f"refs/heads/{candidate}"]):
            return candidate

    return ""


def get_upstream_branch() -> str:
    return git_ok(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])


def get_ahead_behind() -> tuple[int, int]:
    upstream = get_upstream_branch()
    if not upstream:
        return (0, 0)

    result = git(["rev-list", "--left-right", "--count", f"{upstream}...HEAD"])
    if result.returncode != 0:
        return (0, 0)

    parts = result.stdout.strip().split()
    if len(parts) != 2:
        return (0, 0)

    behind = parse_int(parts[0])
    ahead = parse_int(parts[1])
    return (ahead, behind)


def line_count(output: str) -> int:
    text = output.strip()
    if not text:
        return 0
    return len(text.splitlines())


def get_changed_counts() -> dict[str, int]:
    staged_out = git_ok(["diff", "--cached", "--name-only"])
    unstaged_out = git_ok(["diff", "--name-only"])
    untracked_out = git_ok(["ls-files", "--others", "--exclude-standard"])
    return {
        "staged_files": line_count(staged_out),
        "unstaged_files": line_count(unstaged_out),
        "untracked_files": line_count(untracked_out),
    }


def get_pr_context(origin_slug: str = "") -> dict[str, Any]:
    gh_path = shutil.which("gh")
    if not gh_path:
        return {
            "gh_available": False,
            "gh_authenticated": False,
            "current_branch_pr": None,
        }

    auth_status = run(["gh", "auth", "status"])
    gh_authenticated = auth_status.returncode == 0

    pr_data: Any = None
    # Explicit --repo (fork-trap discipline): a flagless `gh pr view` resolves
    # via gh's default repo, which can be the upstream parent. Skip the PR read
    # entirely when origin is unresolved rather than risk the wrong repo.
    if gh_authenticated and origin_slug:
        pr_result = run(
            [
                "gh",
                "pr",
                "view",
                "--repo",
                origin_slug,
                "--json",
                "number,title,url,headRefName,baseRefName",
            ]
        )
        if pr_result.returncode == 0 and pr_result.stdout.strip():
            try:
                pr_data = json.loads(pr_result.stdout)
            except json.JSONDecodeError:
                pr_data = {"raw": pr_result.stdout.strip()}

    return {
        "gh_available": True,
        "gh_authenticated": gh_authenticated,
        "current_branch_pr": pr_data,
    }


VALID_TRACKERS = {"github-project", "github", "none"}


def read_local_config_tracker(repo_root: str) -> tuple[Optional[str], Optional[str]]:
    """Read issue_tracker: from agentic-engineering.local.md frontmatter.

    Returns (valid_value, invalid_raw_value). An unrecognized value (e.g. a
    stale ``linear`` override from before 3.0.0) is surfaced as the second
    element instead of being silently ignored, so callers can tell the user
    their pinned tracker no longer resolves.

    Security invariant (same gate as lifecycle_board.read_board_config): a
    .local.md that is *tracked* in git would ride a PR, letting the PR pin
    ``issue_tracker: none`` and downgrade the workflow out of board gating.
    A tracked copy is ignored with a warning; resolution falls back to
    auto-detect.
    """
    config_path = pathlib.Path(repo_root) / "agentic-engineering.local.md"
    if not config_path.is_file():
        return (None, None)
    tracked = subprocess.run(["git", "-C", repo_root, "ls-files", "--error-unmatch", config_path.name], text=True, capture_output=True)
    if tracked.returncode == 0:
        print(
            f"warning: {config_path.name} is tracked in git — a PR must not carry it; " "ignoring its issue_tracker override and falling back to auto-detect",
            file=sys.stderr,
        )
        return (None, None)
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError:
        return (None, None)
    if not text.startswith("---"):
        return (None, None)
    # Extract frontmatter block between leading --- and the next ---.
    match = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
    if not match:
        return (None, None)
    for line in match.group(1).splitlines():
        m = re.match(r"^\s*issue_tracker\s*:\s*([A-Za-z][A-Za-z-]*)\s*$", line)
        if m:
            value = m.group(1).lower()
            if value in VALID_TRACKERS:
                return (value, None)
            return (None, value)
    return (None, None)


def resolve_issue_tracker(
    repo_root: str,
    board_configured: bool,
    gh_authenticated: bool,
) -> dict[str, Any]:
    """Apply the resolution chain and return both the decision and provenance."""
    local_override, invalid_override = read_local_config_tracker(repo_root)
    if local_override is not None:
        return {
            "resolved": local_override,
            "source": "agentic-engineering.local.md",
            "local_override": local_override,
            "local_override_invalid": None,
        }

    signals = []
    if board_configured:
        signals.append("github-project")
    if gh_authenticated:
        signals.append("github")

    if not signals:
        resolved = "none"
    else:
        resolved = signals[0]

    return {
        "resolved": resolved,
        "source": "auto-detect" if signals else "default",
        "local_override": None,
        "local_override_invalid": invalid_override,
    }


def build_recommendation(current_branch: str, default_branch: str, dirty: bool) -> dict[str, Any]:
    on_default = bool(default_branch) and current_branch == default_branch

    if on_default and dirty:
        return {
            "action": "ask_user_branch_or_worktree_before_proceeding",
            "reason": "Working tree has changes on the default branch.",
            "safe_to_commit_on_current_branch": False,
            "prompt": (f"You are on `{default_branch}` with local changes. Continue on this branch, " "create a feature branch, or use a worktree?"),
        }

    if on_default and not dirty:
        return {
            "action": "create_branch_or_worktree_before_implementation",
            "reason": "Current branch is the default branch.",
            "safe_to_commit_on_current_branch": False,
            "prompt": (f"You are on the default branch `{default_branch}`. Create a feature branch " "or use a worktree before making changes."),
        }

    if current_branch == "HEAD":
        return {
            "action": "resolve_detached_head",
            "reason": "Repository is in detached HEAD state.",
            "safe_to_commit_on_current_branch": False,
            "prompt": "Detached HEAD detected. Checkout a branch or create a worktree before continuing.",
        }

    return {
        "action": "continue_on_current_branch_or_confirm_new_branch",
        "reason": "Already on a non-default branch.",
        "safe_to_commit_on_current_branch": True,
        "prompt": (f"Already on feature branch `{current_branch}`. Continue here or create a new branch/worktree?"),
    }


def main() -> int:
    inside = git(["rev-parse", "--is-inside-work-tree"])
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "Not inside a git repository",
                },
                indent=2,
            )
        )
        return 1

    repo_root = git_ok(["rev-parse", "--show-toplevel"])
    current_branch = git_ok(["branch", "--show-current"]) or "HEAD"
    default_branch = find_default_branch()
    upstream_branch = get_upstream_branch()
    ahead, behind = get_ahead_behind()

    staged_clean = bool_from_exit(["diff", "--cached", "--quiet"])
    unstaged_clean = bool_from_exit(["diff", "--quiet"])
    counts = get_changed_counts()
    dirty = not (staged_clean and unstaged_clean and counts["untracked_files"] == 0)

    # Origin slug for the explicit-repo `gh pr view` (fork-trap discipline).
    origin_owner, origin_repo = lifecycle_board.parse_origin(git_ok(["remote", "get-url", "origin"]))
    origin_slug = f"{origin_owner}/{origin_repo}" if origin_owner and origin_repo else ""

    data = {
        "ok": True,
        "repo": {
            "root": repo_root,
            "current_branch": current_branch,
            "default_branch": default_branch or None,
            "on_default_branch": bool(default_branch) and current_branch == default_branch,
            "detached_head": current_branch == "HEAD",
            "upstream_branch": upstream_branch or None,
            "ahead_by": ahead,
            "behind_by": behind,
            "working_tree_dirty": dirty,
            **counts,
        },
        "integrations": {},
        "github": get_pr_context(origin_slug),
    }

    beads_installed = shutil.which("bd") is not None
    beads_initialized = os.path.isdir(os.path.join(repo_root, ".beads"))
    gh_authenticated = bool(data["github"].get("gh_authenticated"))

    # Board identity is committed config; owner-mismatch and malformed config
    # are hard errors with a named fix (never a silent mode fallback).
    board = None
    try:
        board_ctx = lifecycle_board.repo_context()
        board = lifecycle_board.read_board_config(board_ctx)
    except lifecycle_board.BoardError as exc:
        print(
            json.dumps(
                {"ok": False, "error_code": exc.code, "error": str(exc), "fix": exc.fix},
                indent=2,
            )
        )
        return 1

    tracker_info = resolve_issue_tracker(
        repo_root=repo_root,
        board_configured=board is not None,
        gh_authenticated=gh_authenticated,
    )

    data["integrations"] = {
        "beads_installed": beads_installed,
        "beads_initialized": beads_initialized,
        "beads_remember_available": beads_installed,
        "github_cli_authed": gh_authenticated,
        "board_owner": board.owner if board else None,
        "board_number": board.number if board else None,
        "issue_tracker_local_config": tracker_info["local_override"],
        "issue_tracker_local_config_invalid": tracker_info["local_override_invalid"],
        "issue_tracker_resolved": tracker_info["resolved"],
        "issue_tracker_source": tracker_info["source"],
    }
    if tracker_info["local_override_invalid"]:
        print(
            "warning: agentic-engineering.local.md pins issue_tracker: "
            f"'{tracker_info['local_override_invalid']}', which is not a valid tracker "
            f"({' | '.join(sorted(VALID_TRACKERS))}); falling back to auto-detect",
            file=sys.stderr,
        )

    data["recommendation"] = build_recommendation(
        current_branch=current_branch,
        default_branch=default_branch,
        dirty=dirty,
    )

    print(json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
