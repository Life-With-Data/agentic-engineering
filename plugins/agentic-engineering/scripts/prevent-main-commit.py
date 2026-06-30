#!/usr/bin/env python3
"""
Claude Code hook to block direct commits / pushes to the main branch.

The agentic-engineering workflow is PR-based (plan → work → PR → review →
merge). Never commit or push directly to `main`/`master` — branch off and
open a PR so code review, CI, and the `land-pr` flow apply.
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

    if tool_name != "Bash":
        sys.exit(0)

    stripped = strip_quotes(command)

    is_commit = re.search(r"\bgit\s+commit\b", stripped) is not None
    is_push = re.search(r"\bgit\s+push\b", stripped) is not None

    if not is_commit and not is_push:
        sys.exit(0)

    branch = current_branch()

    if is_commit and branch in PROTECTED_BRANCHES:
        block(
            f"Direct commit to `{branch}` is not allowed.",
            "Branch off and open a PR instead:",
            "  git checkout -b <type>/<description>",
        )

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
        return ""


def pushes_to_protected(stripped: str) -> bool:
    return re.search(r"(?:^|[\s:/])(?:main|master)(?:$|[\s:])", stripped) is not None


def block(*lines: str):
    msg = ["", "❌ BLOCKED: " + lines[0], ""]
    msg.extend(lines[1:])
    msg.append("")
    print("\n".join(msg), file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
