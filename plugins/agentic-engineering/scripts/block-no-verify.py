#!/usr/bin/env python3
"""
Claude Code hook to block git commits/pushes that bypass verification hooks
via `--no-verify` (or its short form `-n`).

Pre-commit / pre-push hooks exist to catch issues before they reach CI. If
checks fail, fix the root cause — don't bypass them.

Design notes:
- Only fires when `git commit` or `git push` is the actual command verb, so
  analysis commands that merely *mention* the flag (e.g. `grep -- --no-verify`)
  are NOT blocked.
- Segment-aware: the flag must appear in the same simple command segment as the
  git verb (not after a later `&&`/`;`/`|`).
- Covers `git push --no-verify`, which has its own pre-push hook bypass.
"""
import json
import re
import sys

COMMIT_BYPASS = re.compile(r"\bgit\s+commit\b[^&|;]*?(?:^|\s)(?:-n|--no-verify)\b")
PUSH_BYPASS = re.compile(r"\bgit\s+push\b[^&|;]*?(?:^|\s)--no-verify\b")

ERROR_MSG = """
❌ BLOCKED: Using --no-verify bypasses pre-commit / pre-push hooks!

Verification hooks exist to catch issues before they reach CI. If hooks fail:
1. Fix the failing tests/checks — don't bypass them
2. If the hooks themselves are broken, fix the hooks
3. Use --no-verify only as an absolute last resort after consulting the team

The agentic-engineering workflow relies on quality gates compounding over time.
Bypassing hooks breaks that chain.
""".strip()


def main():
    input_data = json.load(sys.stdin)

    if input_data.get("tool_name") != "Bash":
        sys.exit(0)

    command = input_data.get("tool_input", {}).get("command", "")

    if uses_no_verify_bypass(command):
        print(ERROR_MSG, file=sys.stderr)
        sys.exit(2)

    sys.exit(0)


def uses_no_verify_bypass(command: str) -> bool:
    cleaned = sanitize(command)
    return bool(COMMIT_BYPASS.search(cleaned) or PUSH_BYPASS.search(cleaned))


def sanitize(command: str) -> str:
    command = re.sub(r"'[^']*'", "", command)
    command = re.sub(r'"[^"]*"', "", command)
    command = re.sub(r"#.*", "", command)
    return command


if __name__ == "__main__":
    main()
