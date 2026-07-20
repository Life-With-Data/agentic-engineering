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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hook_payload import emit_allow, normalize

PROTECTED_BRANCHES = {"main", "master"}


def main():
    input_data = normalize(json.load(sys.stdin))

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    command = tool_input.get("command", "")

    if tool_name != "Bash":
        emit_allow()

    stripped = strip_quotes(command)

    is_commit = re.search(r"\bgit\s+commit\b", stripped) is not None
    # Only the actual `git push` segments — NOT the whole compound command — so a
    # `main`/`master` token in a sibling segment (e.g. `gh pr create --base main`,
    # or a chained `git log origin/main`) cannot be attributed to the push.
    push_segs = [s for s in split_segments(stripped) if re.search(r"\bgit\s+push\b", s)]

    if not is_commit and not push_segs:
        emit_allow()

    branch = current_branch()

    if is_commit and branch in PROTECTED_BRANCHES:
        block(
            f"Direct commit to `{branch}` is not allowed.",
            "Branch off and open a PR instead:",
            "  git checkout -b <type>/<description>",
        )

    if any(pushes_to_protected(seg) for seg in push_segs):
        block(
            "Direct push to `main`/`master` is not allowed.",
            "Push your feature branch and open a PR instead:",
            "  git push -u origin <your-branch>",
        )

    emit_allow()


def strip_quotes(command: str) -> str:
    command = re.sub(r"'[^']*'", "", command)
    command = re.sub(r'"[^"]*"', "", command)
    return command


# Shell separators that end one simple command and begin another. Splitting on
# these lets us inspect each command independently, so a `main` token in a
# non-push segment can't be attributed to a `git push` in another segment.
SEGMENT_SPLIT = re.compile(r"&&|\|\||[;\n|&]")


def split_segments(stripped: str) -> list:
    return SEGMENT_SPLIT.split(stripped)


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
