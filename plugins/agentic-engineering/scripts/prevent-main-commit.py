#!/usr/bin/env python3
"""
Claude Code hook to block direct commits / pushes to the main branch.

Best practice: branch off and open a PR. Never commit or push directly to
`main`/`master`. This hook inspects the Bash command and only acts on
`git commit` (while on main) or an explicit `git push` to main — everything
else is allowed.
"""
import json
import re
import subprocess
import sys

PROTECTED_BRANCHES = {"main", "master"}


def main():
    input_data = json.load(sys.stdin)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    command = tool_input.get("command", "")

    # Only inspect Bash commands.
    if tool_name != "Bash":
        sys.exit(0)

    # Strip quoted strings so commit messages / args can't trigger false
    # positives (e.g. -m "explain the git commit flow").
    stripped = strip_quotes(command)

    is_commit = re.search(r"\bgit\s+commit\b", stripped) is not None
    is_push = re.search(r"\bgit\s+push\b", stripped) is not None

    # Nothing relevant — allow.
    if not is_commit and not is_push:
        sys.exit(0)

    branch = current_branch()

    # Block a `git commit` while sitting on a protected branch.
    if is_commit and branch in PROTECTED_BRANCHES:
        block(
            f"Direct commit to `{branch}` is not allowed.",
            "Branch off and open a PR instead:",
            "  git checkout -b <type>/<description>",
            "  # e.g. git checkout -b fix/auth-redirect",
        )

    # Block an explicit `git push ... main|master` (refspec target), regardless
    # of the current branch — this catches `git push origin main`,
    # `git push origin HEAD:main`, etc.
    if is_push and pushes_to_protected(stripped):
        block(
            "Direct push to `main`/`master` is not allowed.",
            "Push your feature branch and open a PR instead:",
            "  git push -u origin <your-branch>",
        )

    sys.exit(0)


def strip_quotes(command: str) -> str:
    command = re.sub(r"'[^']*'", "", command)
    command = re.sub(r'"[^"]*"', "", command)
    return command


def current_branch() -> str:
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip()
    except Exception:
        # If we can't determine the branch, don't block.
        return ""


def pushes_to_protected(stripped: str) -> bool:
    # main/master as a standalone refspec token (bounded by space, colon,
    # slash, or end-of-string) anywhere after `git push`. Avoids matching
    # branches like `main-feature`.
    return re.search(r"(?:^|[\s:/])(?:main|master)(?:$|[\s:])", stripped) is not None


def block(*lines: str):
    msg = ["", "❌ BLOCKED: " + lines[0], ""]
    msg.extend(lines[1:])
    msg.append("")
    print("\n".join(msg), file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
