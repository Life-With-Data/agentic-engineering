#!/usr/bin/env python3
"""
Claude Code hook — block direct commits or pushes to the default branch.

The agentic-engineering workflow is built on branch-based development: work
branches, open a PR, review, merge. Direct commits to main/master short-circuit
that flow and bypass code review. This hook enforces the invariant.

Blocks:
  - `git commit` while the current branch IS main/master
  - `git push ... main` / `git push ... master` (explicit refspec to a protected branch)

Does NOT block:
  - Any other git commands
  - Pushes to feature branches
  - Commit messages or prose that mention "main" (quoted strings are stripped)
"""
import json
import re
import subprocess
import sys

PROTECTED = {"main", "master"}


def main():
    data = json.load(sys.stdin)
    if data.get("tool_name") != "Bash":
        sys.exit(0)

    command = data.get("tool_input", {}).get("command", "")
    stripped = _strip_quotes(command)

    is_commit = bool(re.search(r"\bgit\s+commit\b", stripped))
    is_push   = bool(re.search(r"\bgit\s+push\b",   stripped))

    if not is_commit and not is_push:
        sys.exit(0)

    branch = _current_branch()

    if is_commit and branch in PROTECTED:
        _block(
            f"Direct commit to `{branch}` is not allowed.",
            "Create a feature branch instead:",
            "  git checkout -b <type>/<short-description>",
        )

    if is_push and _pushes_to_protected(stripped):
        _block(
            "Direct push to `main`/`master` is not allowed.",
            "Push your feature branch and open a PR:",
            "  git push -u origin <your-branch>",
        )

    sys.exit(0)


def _strip_quotes(command: str) -> str:
    command = re.sub(r"'[^']*'", "", command)
    command = re.sub(r'"[^"]*"', "", command)
    return command


def _current_branch() -> str:
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _pushes_to_protected(stripped: str) -> bool:
    return bool(
        re.search(r"(?:^|[\s:/])(?:main|master)(?:$|[\s:])", stripped)
    )


def _block(*lines: str) -> None:
    msg = ["", "❌ BLOCKED: " + lines[0], ""]
    msg.extend(lines[1:])
    msg.append("")
    print("\n".join(msg), file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
