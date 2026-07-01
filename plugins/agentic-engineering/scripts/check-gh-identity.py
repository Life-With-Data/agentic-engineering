#!/usr/bin/env python3
"""
Claude Code hook to guard against running write-permission `gh` commands under the wrong
authenticated GitHub account.

Problem: `gh` CLI supports multiple logged-in accounts, and the active one is global CLI state,
not scoped to a repo or session. On a machine with more than one account logged in (e.g. a
personal account and a client/employer account), a write command (`gh pr create`, `gh issue
close`, ...) silently runs as whichever account `gh` currently has active — which can be the
wrong one for the repo at hand.

This is deliberately opt-in and does not guess: it only activates when the user has set
`AGENTIC_ENGINEERING_GH_USER` to the account expected for this project. Without that, a repo's
owner/org login is not a reliable proxy for "the right account" (most repos are org-owned, and
contributors don't share a login with the org), so the hook stays out of the way by default.

On a mismatch, it blocks with the exact fix rather than switching accounts itself — silently
mutating the machine's active `gh` identity is a bigger side effect than a single repo's PR
command warrants.
"""
import json
import os
import re
import subprocess
import sys

WRITE_VERBS = (
    "merge|close|create|delete|edit|comment|review|approve|request-changes"
    "|ready|reopen|lock|unlock|transfer|archive"
)
WRITE_COMMAND = re.compile(rf"\bgh\s+(?:pr|issue|repo|release)\s+(?:{WRITE_VERBS})\b")


def main():
    input_data = json.load(sys.stdin)

    if input_data.get("tool_name") != "Bash":
        sys.exit(0)

    expected_user = os.environ.get("AGENTIC_ENGINEERING_GH_USER", "").strip()
    if not expected_user:
        sys.exit(0)  # not configured for this project — stay out of the way

    command = input_data.get("tool_input", {}).get("command", "")
    if not WRITE_COMMAND.search(sanitize(command)):
        sys.exit(0)

    current_user = get_current_gh_user()
    if current_user is None or current_user == expected_user:
        sys.exit(0)

    print(
        f"""
❌ BLOCKED: gh CLI is authenticated as `{current_user}`, but this project expects `{expected_user}`
(set via AGENTIC_ENGINEERING_GH_USER).

Running a write command under the wrong account can open PRs, comments, or issues as the
wrong identity. Switch accounts first:
    gh auth switch --user {expected_user}

Then retry the command.
""".strip(),
        file=sys.stderr,
    )
    sys.exit(2)


def get_current_gh_user():
    try:
        result = subprocess.run(
            ["gh", "api", "user", "--jq", ".login"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    login = result.stdout.strip()
    return login or None


def sanitize(command: str) -> str:
    command = re.sub(r"'[^']*'", "", command)
    command = re.sub(r'"[^"]*"', "", command)
    command = re.sub(r"#.*", "", command)
    return command


if __name__ == "__main__":
    main()
